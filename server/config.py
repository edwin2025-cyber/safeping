"""SafePing server settings. Override any of these with environment variables."""
import os

_here = os.path.dirname(os.path.abspath(__file__))


def _get(name, default=None):
    return os.environ.get(name, default)


# Database
DB_PATH = _get("SAFEPING_DB", os.path.join(_here, "safeping.db"))

# MQTT broker. The SAFEPING_MQTT_* names are the ones tests/broker_check.py uses.
# The old names (MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS) still work as a fallback.
# With a CA file set, the connection uses TLS (the cloud broker, port 8883).
MQTT_HOST = _get("SAFEPING_MQTT_HOST") or _get("MQTT_HOST", "localhost")
MQTT_CA = _get("SAFEPING_MQTT_CA") or _get("MQTT_CA")
MQTT_PORT = int(_get("SAFEPING_MQTT_PORT") or _get("MQTT_PORT") or ("8883" if MQTT_CA else "1883"))
MQTT_USER = _get("SAFEPING_MQTT_USER") or _get("MQTT_USER")
MQTT_PASS = _get("SAFEPING_MQTT_PASS") or _get("MQTT_PASS")
# fake_fob.py's own broker login (point it at the Fob user, safeping-fob). The server's
# user may not publish alerts on the locked-down broker.
FAKEFOB_MQTT_USER = _get("SAFEPING_FAKEFOB_MQTT_USER")
FAKEFOB_MQTT_PASS = _get("SAFEPING_FAKEFOB_MQTT_PASS")
# Fixed id for the server's persistent MQTT session (the broker holds alerts while it is down).
MQTT_CLIENT_ID = _get("SAFEPING_MQTT_CLIENT_ID", "safeping-server")
TOPIC_ALERTS = "safeping/alerts"            # old shared topic, still read. Nothing sends here now
TOPIC_ALERT_PREFIX = "safeping/alert/"      # + device id: the Fob publishes here
TOPIC_ACK_PREFIX = "safeping/ack/"          # + device id: the server's signed ack
TOPIC_REFERENCE = "safeping/reference"      # old Reference topic, still read. Nothing sends here now
TOPIC_REF_PREFIX = "safeping/ref/"          # + device id: the Reference board publishes here (QoS 0)
TOPIC_SURVEY_PREFIX = "safeping/survey/"    # + device id: a Fob in survey mode publishes here

# Replay and duplicate rule (message-format.md, "Counters, duplicates and replays").
# A counter the server has not seen is accepted if it is no more than this many below
# the highest counter seen for that Fob. Further below: "replay".
COUNTER_WINDOW = int(_get("COUNTER_WINDOW", "32"))
# An alert whose own time (ts) is older than this is still accepted, but tagged
# "Sent late (over 15 min)" and counted as a yellow warning on Settings > Health.
MAX_ALERT_AGE_S = int(_get("MAX_ALERT_AGE_S", "900"))
# Seen counters are kept at least this many days. Counters inside COUNTER_WINDOW of the
# highest are never pruned, so an exact copy inside the window is always a duplicate.
SEEN_KEEP_DAYS = float(_get("SEEN_KEEP_DAYS", "7"))
# Boot reports kept per device (the Devices page shows the newest).
BOOT_REPORTS_KEPT = 10
# "Sent late" tag: the alert reached the server more than this many seconds after the press.
LATE_AFTER_S = 60

# "Help is coming": the server publishes a signed help message here when staff press
# Acknowledge. + device id.
TOPIC_HELP_PREFIX = "safeping/help/"

# Message rules (see message-format.md)
MAX_PAYLOAD_BYTES = 512
SURVEY_MAX_BYTES = 2048          # a SURVEY carries up to 15 WiFi access points (WiFi only)
SURVEY_MAX_APS = 15

# Reference board (message-format.md, "Reference readings")
REF_KEEP_DAYS = float(_get("REF_KEEP_DAYS", "14"))   # readings older than this are deleted
REF_MATCH_S = int(_get("REF_MATCH_S", "60"))         # a reading this close to the press time counts
# Fixed sensor offsets (Fob minus Reference), written by tests/ref_calibrate.py
SENSOR_OFFSETS_PATH = _get("SAFEPING_SENSOR_OFFSETS", os.path.join(_here, "sensor_offsets.json"))

# Location
PA_PER_FLOOR = float(_get("PA_PER_FLOOR", "42"))   # calibrate with the walk-the-building test
MAX_FLOOR = int(_get("MAX_FLOOR", "4"))
REF_MAX_AGE_S = int(_get("REF_MAX_AGE_S", "120"))   # ignore a Reference reading older than this
PLACES_PATH = _get("SAFEPING_PLACES", os.path.join(_here, "places.json"))   # named campus places

# Texts through Textbelt (server/textbelt.py). SAFEPING_SMS: off, dry (print the text,
# send nothing, the default) or live. Numbers are 10 digits, comma separated.
TEXTBELT_KEY = _get("TEXTBELT_KEY")


def _sms_mode():
    mode = (_get("SAFEPING_SMS") or "dry").strip().lower()
    return mode if mode in ("off", "dry", "live") else "dry"


def _sms_numbers():
    """10-digit numbers. A leading 1 (11 digits) is dropped. Anything else is skipped."""
    out = []
    for part in (_get("SAFEPING_SMS_TO") or "").split(","):
        digits = "".join(ch for ch in part if ch.isdigit())
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) == 10 and digits not in out:
            out.append(digits)
    return out


SMS_MODE = _sms_mode()
SMS_MODE_GIVEN = (_get("SAFEPING_SMS") or "").strip()      # for a warning when it is not a known word
SMS_TO = _sms_numbers()
SMS_TO_SKIPPED = len([p for p in (_get("SAFEPING_SMS_TO") or "").split(",") if p.strip()]) - len(SMS_TO)
SMS_MAX_PER_HOUR = int(_get("SAFEPING_SMS_MAX_PER_HOUR") or "20")
SMS_QUOTA_LOW = 25          # Settings > Health turns orange below this many credits
# Not read from the environment, so the key can only ever go to Textbelt.
# The tests point it at a fake endpoint on 127.0.0.1.
TEXTBELT_URL = "https://textbelt.com/text"
TEXTBELT_TIMEOUT_S = 10

# Pushover phone notifications (server/pushover.py). If either is missing: "Pushover off".
PUSHOVER_USER = _get("SAFEPING_PUSHOVER_USER")
PUSHOVER_TOKEN = _get("SAFEPING_PUSHOVER_TOKEN")
# Not read from the environment, so the token can only ever go to Pushover.
# The tests point it at a fake endpoint on 127.0.0.1.
PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_TIMEOUT_S = 5

# The dashboard's own address as staff open it, for example "http://192.168.1.20:5000".
# When set, each notification links to its alert. Unset: no link.
PUBLIC_URL = (_get("SAFEPING_PUBLIC_URL") or "").strip().rstrip("/") or None

# Dashboard
DASHBOARD_PASSWORD = _get("DASHBOARD_PASSWORD")      # leave unset for no login
CARTO_KEY = _get("CARTO_KEY")                        # map tiles key, never commit it
HOST = _get("HOST", "0.0.0.0")
PORT = int(_get("PORT", "5000"))
