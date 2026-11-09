"""SQLite storage. One short-lived connection per call, WAL mode so the MQTT
listener and the Flask API can use the database at the same time."""
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id     TEXT PRIMARY KEY,
    role          TEXT NOT NULL DEFAULT 'FOB',     -- FOB or REF
    student_name  TEXT,
    secret_key    TEXT NOT NULL,
    last_counter  INTEGER NOT NULL DEFAULT -1
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL,
    alert_type      TEXT NOT NULL,
    timestamp       REAL NOT NULL,      -- when the server received it (Unix seconds)
    device_ts       INTEGER,            -- the Fob's own clock, may be wrong
    latitude        REAL,
    longitude       REAL,
    accuracy        REAL,
    floor           INTEGER,
    pressure        INTEGER,
    battery         INTEGER,
    acknowledged    INTEGER NOT NULL DEFAULT 0,
    acknowledged_at REAL,
    sms_sent        INTEGER NOT NULL DEFAULT 0
    -- More columns are added by MIGRATIONS below, so old databases get them too.
);

CREATE TABLE IF NOT EXISTS reference_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL NOT NULL,
    pressure    INTEGER NOT NULL,
    temperature INTEGER
);

CREATE TABLE IF NOT EXISTS rejected (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    device_id TEXT,
    reason    TEXT NOT NULL,
    payload   TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts (timestamp);
CREATE INDEX IF NOT EXISTS idx_ref_time ON reference_readings (timestamp);
"""

# Columns added after the first version. Each one is added only if it is missing,
# so existing rows stay as they are and get the default.
MIGRATIONS = [
    ("alerts", "resolved", "INTEGER NOT NULL DEFAULT 0"),
    ("alerts", "resolved_at", "REAL"),
    ("alerts", "link", "TEXT NOT NULL DEFAULT 'unknown'"),   # lora, wifi or unknown
    ("alerts", "temperature", "INTEGER"),                    # hundredths of a degree C, like "t"
    ("alerts", "counter", "INTEGER"),                        # the message's "ctr"
]


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        for table, column, definition in MIGRATIONS:
            existing = {row["name"] for row in c.execute("PRAGMA table_info({})".format(table))}
            if column not in existing:
                c.execute("ALTER TABLE {} ADD COLUMN {} {}".format(table, column, definition))


# ---------- devices ----------

def add_device(device_id, role, student_name, secret_key):
    with connect() as c:
        c.execute(
            "INSERT INTO devices (device_id, role, student_name, secret_key) VALUES (?, ?, ?, ?)",
            (device_id, role, student_name, secret_key),
        )


def get_device(device_id):
    with connect() as c:
        return c.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()


def list_devices():
    """One row per device for the dashboard. Never includes the secret key.
    Reference readings do not store a device id, so a REF device's last seen
    time is the newest reference reading."""
    with connect() as c:
        rows = c.execute(
            """SELECT d.device_id, d.role, d.student_name, d.last_counter,
                   CASE WHEN d.role = 'REF'
                        THEN (SELECT MAX(r.timestamp) FROM reference_readings r)
                        ELSE (SELECT MAX(a.timestamp) FROM alerts a WHERE a.device_id = d.device_id)
                   END AS last_seen,
                   (SELECT a.battery FROM alerts a
                     WHERE a.device_id = d.device_id AND a.battery IS NOT NULL
                     ORDER BY a.id DESC LIMIT 1) AS battery,
                   (SELECT a.link FROM alerts a
                     WHERE a.device_id = d.device_id ORDER BY a.id DESC LIMIT 1) AS link,
                   (SELECT COUNT(*) FROM alerts a
                     WHERE a.device_id = d.device_id AND a.acknowledged = 0
                       AND a.resolved = 0 AND a.alert_type != 'STATUS') AS open_alerts
               FROM devices d
               ORDER BY d.role, d.device_id"""
        ).fetchall()
    return [dict(r) for r in rows]


def advance_counter(device_id, counter):
    """Save a new counter only if it is higher than the last one. Returns True if it was.
    This is one UPDATE, so two messages arriving at the same moment cannot both pass."""
    with connect() as c:
        cur = c.execute(
            "UPDATE devices SET last_counter = ? WHERE device_id = ? AND last_counter < ?",
            (counter, device_id, counter),
        )
        return cur.rowcount == 1


# ---------- alerts ----------

def insert_alert(device_id, alert_type, received_at, device_ts, loc, pressure, battery,
                 temperature=None, counter=None, link="unknown"):
    with connect() as c:
        cur = c.execute(
            """INSERT INTO alerts
               (device_id, alert_type, timestamp, device_ts, latitude, longitude,
                accuracy, floor, pressure, battery, temperature, counter, link)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (device_id, alert_type, received_at, device_ts,
             loc.get("latitude"), loc.get("longitude"), loc.get("accuracy"),
             loc.get("floor"), pressure, battery, temperature, counter, link),
        )
        return cur.lastrowid


def mark_sms(alert_id, sent):
    with connect() as c:
        c.execute("UPDATE alerts SET sms_sent = ? WHERE id = ?", (1 if sent else 0, alert_id))


def list_alerts(limit=100, include_status=False, include_resolved=False):
    with connect() as c:
        rows = c.execute(
            """SELECT a.*, d.student_name
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE (? = 1 OR a.alert_type != 'STATUS')
                 AND (? = 1 OR a.resolved = 0)
               ORDER BY a.id DESC LIMIT ?""",
            (1 if include_status else 0, 1 if include_resolved else 0, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def ack_alert(alert_id, now):
    with connect() as c:
        cur = c.execute(
            "UPDATE alerts SET acknowledged = 1, acknowledged_at = ? WHERE id = ? AND acknowledged = 0",
            (now, alert_id),
        )
        return cur.rowcount == 1


def resolve_alert(alert_id, now):
    """Resolving also acknowledges, if nobody did yet, so it leaves the open count."""
    with connect() as c:
        cur = c.execute(
            """UPDATE alerts SET resolved = 1, resolved_at = ?,
                   acknowledged = 1, acknowledged_at = COALESCE(acknowledged_at, ?)
               WHERE id = ? AND resolved = 0""",
            (now, now, alert_id),
        )
        return cur.rowcount == 1


def last_alert_time(link):
    """When the newest alert that came in over this link was received, or None."""
    with connect() as c:
        return c.execute("SELECT MAX(timestamp) FROM alerts WHERE link = ?", (link,)).fetchone()[0]


def count_unacknowledged():
    with connect() as c:
        return c.execute(
            "SELECT COUNT(*) FROM alerts WHERE acknowledged = 0 AND alert_type != 'STATUS'"
        ).fetchone()[0]


# ---------- reference readings ----------

def insert_reference(received_at, pressure, temperature):
    with connect() as c:
        c.execute(
            "INSERT INTO reference_readings (timestamp, pressure, temperature) VALUES (?, ?, ?)",
            (received_at, pressure, temperature),
        )


def latest_reference():
    with connect() as c:
        row = c.execute(
            "SELECT * FROM reference_readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---------- rejected messages ----------

def log_rejected(received_at, device_id, reason, payload_text):
    with connect() as c:
        c.execute(
            "INSERT INTO rejected (timestamp, device_id, reason, payload) VALUES (?, ?, ?, ?)",
            (received_at, device_id, reason, payload_text),
        )


def count_rejected():
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM rejected").fetchone()[0]
