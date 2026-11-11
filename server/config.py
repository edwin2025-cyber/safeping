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
# Fixed id for the server's persistent MQTT session (the broker holds alerts while it is down).
MQTT_CLIENT_ID = _get("SAFEPING_MQTT_CLIENT_ID", "safeping-server")
TOPIC_ALERTS = "safeping/alerts"            # old shared topic (fake_fob.py), still read
TOPIC_ALERT_PREFIX = "safeping/alert/"      # + device id: the Fob publishes here
TOPIC_ACK_PREFIX = "safeping/ack/"          # + device id: the server's signed ack
TOPIC_REFERENCE = "safeping/reference"

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

# Location
PA_PER_FLOOR = float(_get("PA_PER_FLOOR", "42"))   # calibrate with the walk-the-building test
MAX_FLOOR = int(_get("MAX_FLOOR", "4"))
REF_MAX_AGE_S = int(_get("REF_MAX_AGE_S", "120"))   # ignore a Reference reading older than this
PLACES_PATH = _get("SAFEPING_PLACES", os.path.join(_here, "places.json"))   # named campus places

# Texts. If the Twilio values are missing the server prints the text instead (dry run).
TWILIO_SID = _get("TWILIO_SID")
TWILIO_TOKEN = _get("TWILIO_TOKEN")
TWILIO_FROM = _get("TWILIO_FROM")
DUTY_PHONES = [p.strip() for p in _get("DUTY_PHONES", "").split(",") if p.strip()]

# Dashboard
DASHBOARD_PASSWORD = _get("DASHBOARD_PASSWORD")      # leave unset for no login
CARTO_KEY = _get("CARTO_KEY")                        # map tiles key, never commit it
HOST = _get("HOST", "0.0.0.0")
PORT = int(_get("PORT", "5000"))
