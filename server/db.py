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

-- Every counter the server has accepted from a Fob, with its signature: the record of
-- seen counters for the replay and duplicate rule in message-format.md. One row per
-- (device, counter), enforced by idx_seen_counter. Pruned after SEEN_KEEP_DAYS.
CREATE TABLE IF NOT EXISTS accepted_sigs (
    device_id TEXT NOT NULL,
    counter   INTEGER NOT NULL,
    sig       TEXT NOT NULL,
    timestamp REAL NOT NULL
);

-- Boot reports (BOOT messages). Never alerts. The newest BOOT_REPORTS_KEPT per device are kept.
CREATE TABLE IF NOT EXISTS boot_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    timestamp   REAL NOT NULL,      -- when the server received it
    device_ts   INTEGER,            -- the Fob's clock, if set
    counter     INTEGER NOT NULL,
    failed      INTEGER NOT NULL,   -- bit mask of failed required checks, 0 = all passed
    wifi        INTEGER,            -- 1 = WiFi joined at boot, 0 = not (information only)
    firmware    TEXT,
    link        TEXT NOT NULL DEFAULT 'unknown'
);

-- Help messages sent to a Fob when staff press Acknowledge ("help is coming").
CREATE TABLE IF NOT EXISTS help_sent (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id  INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    path      TEXT NOT NULL          -- wifi (MQTT). lora is Part E.
);

-- Last send and last error of each notification channel (pushover), for Settings > Health.
-- One row per channel. Kept here, not in memory, because serial_bridge.py runs as its
-- own program and sends too.
CREATE TABLE IF NOT EXISTS notify_status (
    channel          TEXT PRIMARY KEY,
    last_send_at     REAL,
    last_send_alert  INTEGER,
    last_error_at    REAL,
    last_error_alert INTEGER,
    last_error       TEXT
);

-- Survey points from a Fob in survey mode (SURVEY messages). Never alerts. One row per
-- (device, counter), so a copy sent twice is stored once. Kept until deleted by hand.
CREATE TABLE IF NOT EXISTS survey_points (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id    TEXT NOT NULL,
    counter      INTEGER NOT NULL,
    timestamp    REAL NOT NULL,      -- when the server received it
    device_ts    INTEGER,            -- the Fob's clock, the middle of the 3 s pressure window
    pressure_dpa INTEGER,            -- tenths of a pascal, averaged
    temperature  INTEGER,            -- hundredths of a degree C
    samples      INTEGER NOT NULL,
    battery      INTEGER,
    gps_fix      INTEGER NOT NULL,
    satellites   INTEGER NOT NULL,
    latitude     REAL,
    longitude    REAL,
    accuracy     REAL,
    aps          TEXT NOT NULL,      -- the "aps" list as JSON
    ref_pressure REAL,               -- the Reference at device_ts (or arrival), pascals
    ref_time     REAL,               -- the time the reference was taken for
    link         TEXT NOT NULL DEFAULT 'unknown'
);

-- Texts sent through Textbelt (textbelt.py): one row per alert and number, so an alert is
-- texted to a number at most once. The number itself is never stored: only a hash (to
-- match it) and its last 2 digits (to show it). Rows also count toward the hourly cap.
CREATE TABLE IF NOT EXISTS sms_sent (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    INTEGER NOT NULL,
    phone_hash  TEXT NOT NULL,
    phone_last2 TEXT NOT NULL,
    timestamp   REAL NOT NULL,
    ok          INTEGER NOT NULL DEFAULT 0,
    text_id     TEXT,               -- Textbelt's textId
    error       TEXT,
    quota       INTEGER             -- quotaRemaining from the reply
);
-- Numbers that have had a text, so "Reply STOP to opt out" goes only on the first one.
CREATE TABLE IF NOT EXISTS sms_numbers (
    phone_hash TEXT PRIMARY KEY,
    first_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts (timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sms_alert_phone ON sms_sent (alert_id, phone_hash);
CREATE INDEX IF NOT EXISTS idx_sms_time ON sms_sent (timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS idx_survey_counter ON survey_points (device_id, counter);
CREATE INDEX IF NOT EXISTS idx_accepted_sigs ON accepted_sigs (device_id, counter);
CREATE INDEX IF NOT EXISTS idx_accepted_sigs_time ON accepted_sigs (timestamp);
CREATE INDEX IF NOT EXISTS idx_boot_device ON boot_reports (device_id, id);
CREATE INDEX IF NOT EXISTS idx_help_alert ON help_sent (alert_id);
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
    ("boot_reports", "reset_cause", "INTEGER"),              # BOOT "rst", machine.reset_cause()
    ("alerts", "cut_off", "INTEGER NOT NULL DEFAULT 0"),     # 1 = "cut": 1, press cut off by a restart
    # Reference board (firmware/ref): which board, its clock, pressure to one decimal
    ("reference_readings", "device_id", "TEXT"),
    ("reference_readings", "device_ts", "INTEGER"),          # middle of the 30 s window
    ("reference_readings", "pressure_dpa", "INTEGER"),       # tenths of a pascal
    ("reference_readings", "samples", "INTEGER"),
    ("reference_readings", "firmware", "TEXT"),
    ("reference_readings", "ref_time", "REAL"),              # device_ts, or arrival without one
    # The Reference at the alert's press time (message-format.md, "Reference readings")
    ("alerts", "ref_pressure", "REAL"),                      # pascals, one decimal
    ("alerts", "ref_diff", "REAL"),                          # alert pressure minus ref_pressure
    ("alerts", "ref_offset", "REAL"),                        # the Fob's sensor offset, if calibrated
    ("notify_status", "quota", "INTEGER"),                   # Textbelt quotaRemaining from the last reply
    ("boot_reports", "sensor", "TEXT"),                      # Reference board BOOT: "BME280@0x77"
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
        # One row per (device, counter), so two copies arriving at the same moment cannot
        # both claim a counter. The old rule only ever accepted rising counters, so an
        # existing database has no two rows with the same pair.
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_seen_counter ON accepted_sigs (device_id, counter)")
        # After the migrations, so ref_time exists. Old rows get the time they arrived.
        c.execute("UPDATE reference_readings SET ref_time = timestamp WHERE ref_time IS NULL")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ref_reftime ON reference_readings (ref_time)")


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
    A REF device's last seen time is its newest reading (old readings with no device id
    count for every REF device)."""
    with connect() as c:
        rows = c.execute(
            """SELECT d.device_id, d.role, d.student_name, d.last_counter,
                   CASE WHEN d.role = 'REF'
                        THEN (SELECT MAX(r.timestamp) FROM reference_readings r
                               WHERE r.device_id = d.device_id OR r.device_id IS NULL)
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


def raise_counter(device_id, counter):
    """last_counter becomes the highest counter seen. Never goes down."""
    with connect() as c:
        c.execute("UPDATE devices SET last_counter = MAX(last_counter, ?) WHERE device_id = ?",
                  (counter, device_id))


def seen_sig(device_id, counter):
    """The signature saved for this device and counter, or None if the counter is unseen
    (or was pruned)."""
    with connect() as c:
        row = c.execute("SELECT sig FROM accepted_sigs WHERE device_id = ? AND counter = ?",
                        (device_id, counter)).fetchone()
    return row[0] if row else None


def claim_counter(device_id, counter, sig, received_at):
    """Mark a counter as seen with this signature. Returns False if it was already taken
    (by this message or another one). One INSERT, so two copies cannot both win."""
    with connect() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO accepted_sigs (device_id, counter, sig, timestamp)
               VALUES (?, ?, ?, ?)""",
            (device_id, counter, sig.lower(), received_at),
        )
        return cur.rowcount == 1


def release_counter(device_id, counter, sig):
    """Undo claim_counter, when the message could not be saved after all."""
    with connect() as c:
        c.execute("DELETE FROM accepted_sigs WHERE device_id = ? AND counter = ? AND sig = ?",
                  (device_id, counter, sig.lower()))


def prune_seen(before, window=None):
    """Forget seen counters received before this time, but never one inside the counter
    window (no more than window below the device's highest counter): those must stay, or
    an old copy could be accepted again. Returns how many were removed."""
    window = config.COUNTER_WINDOW if window is None else window
    with connect() as c:
        return c.execute(
            """DELETE FROM accepted_sigs WHERE timestamp < ? AND counter <
                   (SELECT d.last_counter - ? FROM devices d WHERE d.device_id = accepted_sigs.device_id)""",
            (before, window),
        ).rowcount


def count_late(start, end, over_s):
    """Alerts received in the range that arrived more than over_s after the press (ts)."""
    with connect() as c:
        return c.execute(
            """SELECT COUNT(*) FROM alerts WHERE timestamp >= ? AND timestamp < ?
                   AND device_ts IS NOT NULL AND timestamp - device_ts > ?""",
            (start, end, over_s),
        ).fetchone()[0]


# ---------- alerts ----------

def insert_alert(device_id, alert_type, received_at, device_ts, loc, pressure, battery,
                 temperature=None, counter=None, link="unknown", cut_off=False, ref=None):
    """ref: refmatch.for_pressure() output (ref_pressure, ref_diff, ref_offset) or None."""
    ref = ref or {}
    with connect() as c:
        cur = c.execute(
            """INSERT INTO alerts
               (device_id, alert_type, timestamp, device_ts, latitude, longitude,
                accuracy, floor, pressure, battery, temperature, counter, link, cut_off,
                ref_pressure, ref_diff, ref_offset)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (device_id, alert_type, received_at, device_ts,
             loc.get("latitude"), loc.get("longitude"), loc.get("accuracy"),
             loc.get("floor"), pressure, battery, temperature, counter, link,
             1 if cut_off else 0,
             ref.get("ref_pressure"), ref.get("ref_diff"), ref.get("ref_offset")),
        )
        return cur.lastrowid


def mark_sms(alert_id, sent):
    with connect() as c:
        c.execute("UPDATE alerts SET sms_sent = ? WHERE id = ?", (1 if sent else 0, alert_id))


# ---------- notification channels ----------

def record_notify(channel, at, alert_id, error=None):
    """A send that worked (error None) or failed (error is the reason)."""
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO notify_status (channel) VALUES (?)", (channel,))
        if error is None:
            c.execute("UPDATE notify_status SET last_send_at = ?, last_send_alert = ? WHERE channel = ?",
                      (at, alert_id, channel))
        else:
            c.execute("UPDATE notify_status SET last_error_at = ?, last_error_alert = ?, last_error = ?"
                      " WHERE channel = ?", (at, alert_id, error, channel))


def set_notify_quota(channel, quota):
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO notify_status (channel) VALUES (?)", (channel,))
        c.execute("UPDATE notify_status SET quota = ? WHERE channel = ?", (quota, channel))


# ---------- texts (textbelt.py) ----------

def sms_claim(alert_id, phone_hash, last2, at):
    """Claim (alert, number) before the request goes out. False if it was already texted
    or tried: one INSERT, so two programs (listener and serial bridge) cannot both send."""
    with connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO sms_sent (alert_id, phone_hash, phone_last2, timestamp) VALUES (?, ?, ?, ?)",
            (alert_id, phone_hash, last2, at))
        return cur.rowcount == 1


def sms_result(alert_id, phone_hash, ok, text_id, error, quota):
    with connect() as c:
        c.execute("UPDATE sms_sent SET ok = ?, text_id = ?, error = ?, quota = ? WHERE alert_id = ? AND phone_hash = ?",
                  (1 if ok else 0, text_id, error, quota, alert_id, phone_hash))


def sms_count_since(since):
    """Texts tried since this time (they use credits when they go through)."""
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM sms_sent WHERE timestamp >= ?", (since,)).fetchone()[0]


def sms_number_known(phone_hash):
    with connect() as c:
        return c.execute("SELECT 1 FROM sms_numbers WHERE phone_hash = ?", (phone_hash,)).fetchone() is not None


def sms_number_seen(phone_hash, at):
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO sms_numbers (phone_hash, first_at) VALUES (?, ?)", (phone_hash, at))


def notify_status(channel):
    """The channel's row as a dict, or None if it never sent or failed."""
    with connect() as c:
        row = c.execute("SELECT * FROM notify_status WHERE channel = ?", (channel,)).fetchone()
    return dict(row) if row else None


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


# ---------- boot reports ----------

def insert_boot(device_id, received_at, device_ts, counter, failed, wifi, firmware, link="unknown",
                reset_cause=None, sensor=None):
    """Save one boot report, then keep only the newest BOOT_REPORTS_KEPT for this device.
    sensor: the Reference board's pressure sensor, like "BME280@0x77" (None for a Fob)."""
    with connect() as c:
        cur = c.execute(
            """INSERT INTO boot_reports
               (device_id, timestamp, device_ts, counter, failed, wifi, firmware, link, reset_cause, sensor)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (device_id, received_at, device_ts, counter, failed, wifi, firmware, link, reset_cause, sensor),
        )
        c.execute(
            """DELETE FROM boot_reports WHERE device_id = ? AND id NOT IN
               (SELECT id FROM boot_reports WHERE device_id = ? ORDER BY id DESC LIMIT ?)""",
            (device_id, device_id, config.BOOT_REPORTS_KEPT),
        )
        return cur.lastrowid


def list_boots(device_id, limit=None):
    """One device's boot reports, newest first."""
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM boot_reports WHERE device_id = ? ORDER BY id DESC LIMIT ?",
            (device_id, limit or config.BOOT_REPORTS_KEPT),
        ).fetchall()
    return [dict(r) for r in rows]


def latest_boots():
    """{device_id: newest boot report} for every device that has one."""
    with connect() as c:
        rows = c.execute(
            """SELECT b.* FROM boot_reports b
               WHERE b.id = (SELECT MAX(id) FROM boot_reports WHERE device_id = b.device_id)"""
        ).fetchall()
    return {r["device_id"]: dict(r) for r in rows}


# ---------- help messages ("help is coming") ----------

def record_help(alert_id, sent_at, path="wifi"):
    with connect() as c:
        c.execute("INSERT INTO help_sent (alert_id, timestamp, path) VALUES (?, ?, ?)",
                  (alert_id, sent_at, path))


def help_times(alert_ids):
    """{alert_id: time of the first help message sent} for the given alerts."""
    ids = [int(i) for i in alert_ids]
    if not ids:
        return {}
    with connect() as c:
        rows = c.execute(
            "SELECT alert_id, MIN(timestamp) FROM help_sent WHERE alert_id IN ({}) GROUP BY alert_id"
            .format(",".join("?" * len(ids))), ids,
        ).fetchall()
    return {r[0]: r[1] for r in rows}


# ---------- reference readings ----------

def insert_reference(received_at, pressure, temperature, device_id=None, device_ts=None,
                     pressure_dpa=None, samples=None, firmware=None):
    """ref_time is the time the reading stands for: the board's ts (the middle of its
    window), or the arrival time when it has no ts."""
    ref_time = device_ts if device_ts is not None else received_at
    with connect() as c:
        c.execute(
            """INSERT INTO reference_readings
               (timestamp, pressure, temperature, device_id, device_ts, pressure_dpa, samples,
                firmware, ref_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (received_at, pressure, temperature, device_id, device_ts, pressure_dpa, samples,
             firmware, ref_time),
        )


def latest_reference(device_id=None):
    """The newest reading (of one board, when device_id is given), or None."""
    with connect() as c:
        if device_id is None:
            row = c.execute("SELECT * FROM reference_readings ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = c.execute(
                """SELECT * FROM reference_readings WHERE device_id = ? OR device_id IS NULL
                   ORDER BY id DESC LIMIT 1""", (device_id,)).fetchone()
    return dict(row) if row else None


def reference_around(t, window_s):
    """(the reading at or before t, the reading at or after t), each within window_s of t
    by ref_time, or None."""
    with connect() as c:
        before = c.execute(
            """SELECT * FROM reference_readings WHERE ref_time <= ? AND ref_time >= ?
               ORDER BY ref_time DESC, id DESC LIMIT 1""", (t, t - window_s)).fetchone()
        after = c.execute(
            """SELECT * FROM reference_readings WHERE ref_time >= ? AND ref_time <= ?
               ORDER BY ref_time ASC, id ASC LIMIT 1""", (t, t + window_s)).fetchone()
    return (dict(before) if before else None), (dict(after) if after else None)


def list_reference(start, end, limit=50000):
    """Readings received in the range, oldest first."""
    with connect() as c:
        rows = c.execute(
            """SELECT * FROM reference_readings WHERE timestamp >= ? AND timestamp < ?
               ORDER BY ref_time, id LIMIT ?""", (start, end, limit)).fetchall()
    return [dict(r) for r in rows]


def prune_reference(before):
    """Delete readings received before this time. Returns how many."""
    with connect() as c:
        return c.execute("DELETE FROM reference_readings WHERE timestamp < ?", (before,)).rowcount


# ---------- survey points ----------

def insert_survey(device_id, counter, received_at, msg, aps_json, ref_pressure, ref_time, link="unknown"):
    """Save one survey point. Returns its id, or None when this (device, counter) is
    already stored (a copy that came back after its counter was pruned)."""
    with connect() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO survey_points
               (device_id, counter, timestamp, device_ts, pressure_dpa, temperature, samples,
                battery, gps_fix, satellites, latitude, longitude, accuracy, aps, ref_pressure,
                ref_time, link)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (device_id, counter, received_at, msg.get("ts"), msg.get("pd"), msg.get("t"),
             msg["n"], msg.get("bat"), msg["fix"], msg["sats"],
             None if msg.get("lat") is None else msg["lat"] / 1_000_000,
             None if msg.get("lon") is None else msg["lon"] / 1_000_000,
             msg.get("acc"), aps_json, ref_pressure, ref_time, link),
        )
        return cur.lastrowid if cur.rowcount == 1 else None


def list_survey(start, end, device_id=None):
    """Survey points received in the range, oldest first by the Fob's time."""
    with connect() as c:
        rows = c.execute(
            """SELECT * FROM survey_points WHERE timestamp >= ? AND timestamp < ?
                   AND (? IS NULL OR device_id = ?)
               ORDER BY COALESCE(device_ts, timestamp), id""",
            (start, end, device_id, device_id)).fetchall()
    return [dict(r) for r in rows]


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
