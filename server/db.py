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

-- The signature of every accepted alert, so an identical resend can be told apart
-- from a replay (the "duplicate" rule in message-format.md).
CREATE TABLE IF NOT EXISTS accepted_sigs (
    device_id TEXT NOT NULL,
    counter   INTEGER NOT NULL,
    sig       TEXT NOT NULL,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts (timestamp);
CREATE INDEX IF NOT EXISTS idx_accepted_sigs ON accepted_sigs (device_id, counter);
CREATE INDEX IF NOT EXISTS idx_ref_time ON reference_readings (timestamp);
CREATE INDEX IF NOT EXISTS idx_rejected_time ON rejected (timestamp);
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


def record_accepted(device_id, counter, sig, received_at):
    """Remember an accepted alert's signature for the duplicate check."""
    with connect() as c:
        c.execute(
            "INSERT INTO accepted_sigs (device_id, counter, sig, timestamp) VALUES (?, ?, ?, ?)",
            (device_id, counter, sig.lower(), received_at),
        )


def is_recent_duplicate(device_id, counter, sig, since):
    """True if this exact alert (same id, counter and signature) was accepted at or after since."""
    with connect() as c:
        row = c.execute(
            """SELECT 1 FROM accepted_sigs
               WHERE device_id = ? AND counter = ? AND sig = ? AND timestamp >= ? LIMIT 1""",
            (device_id, counter, sig.lower(), since),
        ).fetchone()
    return row is not None


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


def list_device_alerts(device_id, limit=200):
    """One device's alert history: every type and state, newest first."""
    with connect() as c:
        rows = c.execute(
            """SELECT a.*, d.student_name
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE a.device_id = ?
               ORDER BY a.id DESC LIMIT ?""",
            (device_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_alert(alert_id):
    """One alert with its student name, or None. For the alert panel (/api/alerts/<id>)."""
    with connect() as c:
        row = c.execute(
            """SELECT a.*, d.student_name
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE a.id = ?""",
            (alert_id,),
        ).fetchone()
    return dict(row) if row else None


def _contains(text):
    """A LIKE pattern for 'contains text'. % and _ typed by the user match themselves."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_alerts(query, include_status, limit):
    """Newest alerts whose student name or Fob ID contains the query (ASCII letters in any case).
    An empty query matches every alert."""
    pattern = _contains(query)
    with connect() as c:
        rows = c.execute(
            """SELECT a.*, d.student_name
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE (? = 1 OR a.alert_type != 'STATUS')
                 AND (? = '' OR COALESCE(d.student_name, '') LIKE ? ESCAPE '\\'
                      OR a.device_id LIKE ? ESCAPE '\\')
               ORDER BY a.timestamp DESC, a.id DESC LIMIT ?""",
            (1 if include_status else 0, query, pattern, pattern, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def last_alert_of(device_id, include_status):
    """The newest alert from one device as {id, alert_type, timestamp}, or None."""
    with connect() as c:
        row = c.execute(
            """SELECT id, alert_type, timestamp FROM alerts
               WHERE device_id = ? AND (? = 1 OR alert_type != 'STATUS')
               ORDER BY timestamp DESC, id DESC LIMIT 1""",
            (device_id, 1 if include_status else 0),
        ).fetchone()
    return dict(row) if row else None


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


# ---------- Overview numbers ----------
# Days and hours use 'localtime': the time zone of the machine the server runs on.
# start and end are Unix seconds. An alert counts when start <= timestamp < end.

def count_by_day_and_type(start, end):
    """{("2026-11-02", "MEDICAL"): 3, ...} for alerts received in the range."""
    with connect() as c:
        rows = c.execute(
            """SELECT date(timestamp, 'unixepoch', 'localtime') AS day, alert_type, COUNT(*) AS n
               FROM alerts WHERE timestamp >= ? AND timestamp < ?
               GROUP BY day, alert_type""",
            (start, end),
        ).fetchall()
    return {(r["day"], r["alert_type"]): r["n"] for r in rows}


def count_by_hour_and_type(start, end):
    """{(14, "MEDICAL"): 2, ...}: local hour of the day (0 to 23) and type."""
    with connect() as c:
        rows = c.execute(
            """SELECT CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER) AS hour,
                      alert_type, COUNT(*) AS n
               FROM alerts WHERE timestamp >= ? AND timestamp < ?
               GROUP BY hour, alert_type""",
            (start, end),
        ).fetchall()
    return {(r["hour"], r["alert_type"]): r["n"] for r in rows}


def count_by_weekday_hour(start, end):
    """[(weekday, hour, count)] for alerts other than STATUS. Weekday 0 is Sunday."""
    with connect() as c:
        rows = c.execute(
            """SELECT CAST(strftime('%w', timestamp, 'unixepoch', 'localtime') AS INTEGER) AS weekday,
                      CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER) AS hour,
                      COUNT(*) AS n
               FROM alerts
               WHERE timestamp >= ? AND timestamp < ? AND alert_type != 'STATUS'
               GROUP BY weekday, hour""",
            (start, end),
        ).fetchall()
    return [(r["weekday"], r["hour"], r["n"]) for r in rows]


def flow_counts(start, end):
    """(received, acknowledged, resolved) for alerts other than STATUS received in the range."""
    with connect() as c:
        row = c.execute(
            """SELECT COUNT(*), COALESCE(SUM(acknowledged), 0), COALESCE(SUM(resolved), 0)
               FROM alerts
               WHERE timestamp >= ? AND timestamp < ? AND alert_type != 'STATUS'""",
            (start, end),
        ).fetchone()
    return row[0], row[1], row[2]


def ack_seconds(start, end):
    """Seconds from received to acknowledged, for alerts that have an acknowledge time."""
    with connect() as c:
        rows = c.execute(
            """SELECT acknowledged_at - timestamp FROM alerts
               WHERE timestamp >= ? AND timestamp < ? AND alert_type != 'STATUS'
                 AND acknowledged = 1 AND acknowledged_at IS NOT NULL""",
            (start, end),
        ).fetchall()
    return [max(0.0, r[0]) for r in rows]


def resolve_seconds(start, end):
    """Seconds from acknowledged to resolved, for resolved alerts that have both times."""
    with connect() as c:
        rows = c.execute(
            """SELECT resolved_at - acknowledged_at FROM alerts
               WHERE timestamp >= ? AND timestamp < ? AND alert_type != 'STATUS'
                 AND resolved = 1 AND resolved_at IS NOT NULL AND acknowledged_at IS NOT NULL""",
            (start, end),
        ).fetchall()
    return [max(0.0, r[0]) for r in rows]


def ack_seconds_by_type(start, end):
    """{"MEDICAL": [seconds, ...], ...}: received to acknowledged, per type, STATUS left out."""
    with connect() as c:
        rows = c.execute(
            """SELECT alert_type, acknowledged_at - timestamp FROM alerts
               WHERE timestamp >= ? AND timestamp < ? AND alert_type != 'STATUS'
                 AND acknowledged = 1 AND acknowledged_at IS NOT NULL""",
            (start, end),
        ).fetchall()
    out = {}
    for alert_type, seconds in rows:
        out.setdefault(alert_type, []).append(max(0.0, seconds))
    return out


def alert_locations(start, end):
    """(latitude, longitude, floor) of every alert other than STATUS received in the range."""
    with connect() as c:
        rows = c.execute(
            """SELECT latitude, longitude, floor FROM alerts
               WHERE timestamp >= ? AND timestamp < ? AND alert_type != 'STATUS'""",
            (start, end),
        ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def count_by_link(start, end):
    """{"lora": 12, "wifi": 5, "unknown": 2} for every alert received in the range, STATUS included."""
    with connect() as c:
        rows = c.execute(
            """SELECT link, COUNT(*) FROM alerts
               WHERE timestamp >= ? AND timestamp < ? GROUP BY link""",
            (start, end),
        ).fetchall()
    out = {"lora": 0, "wifi": 0, "unknown": 0}
    for link, n in rows:
        key = link if link in ("lora", "wifi") else "unknown"
        out[key] += n
    return out


def count_open():
    """(open alerts, open MEDICAL alerts) right now. STATUS is never counted, like the Live page."""
    with connect() as c:
        row = c.execute(
            """SELECT COUNT(*), COALESCE(SUM(alert_type = 'MEDICAL'), 0) FROM alerts
               WHERE acknowledged = 0 AND resolved = 0 AND alert_type != 'STATUS'"""
        ).fetchone()
    return row[0], row[1]


def open_alerts():
    """Open alerts right now (not acknowledged, not resolved), STATUS left out, newest first."""
    with connect() as c:
        rows = c.execute(
            """SELECT a.id, a.alert_type, a.device_id, d.student_name
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE a.acknowledged = 0 AND a.resolved = 0 AND a.alert_type != 'STATUS'
               ORDER BY a.timestamp DESC, a.id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def latest_alert():
    """The newest alert other than STATUS, with its student name, or None."""
    with connect() as c:
        row = c.execute(
            """SELECT a.*, d.student_name
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE a.alert_type != 'STATUS'
               ORDER BY a.timestamp DESC, a.id DESC LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def alert_events(start, end):
    """Alerts other than STATUS that were received, acknowledged or resolved in the range,
    with their student names. For the Overview map and Recent activity."""
    with connect() as c:
        rows = c.execute(
            """SELECT a.id, a.alert_type, a.device_id, d.student_name, a.timestamp,
                      a.acknowledged_at, a.resolved_at, a.latitude, a.longitude, a.floor
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE a.alert_type != 'STATUS'
                 AND ((a.timestamp >= ? AND a.timestamp < ?)
                      OR (a.acknowledged_at >= ? AND a.acknowledged_at < ?)
                      OR (a.resolved_at >= ? AND a.resolved_at < ?))""",
            (start, end, start, end, start, end),
        ).fetchall()
    return [dict(r) for r in rows]


def alerts_between(start, end):
    """Every alert received in the range, all types and states, oldest first. For the CSV export."""
    with connect() as c:
        rows = c.execute(
            """SELECT a.*, d.student_name
               FROM alerts a LEFT JOIN devices d ON d.device_id = a.device_id
               WHERE a.timestamp >= ? AND a.timestamp < ?
               ORDER BY a.timestamp, a.id""",
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]


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


def rejected_by_reason(start, end):
    """{"bad_signature": 2, "replay": 1, ...} for messages rejected in the range."""
    with connect() as c:
        rows = c.execute(
            """SELECT reason, COUNT(*) FROM rejected
               WHERE timestamp >= ? AND timestamp < ? GROUP BY reason""",
            (start, end),
        ).fetchall()
    return {reason: n for reason, n in rows}
