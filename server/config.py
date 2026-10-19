"""SafePing server settings. Override any of these with environment variables."""
import os

_here = os.path.dirname(os.path.abspath(__file__))


def _get(name, default=None):
    return os.environ.get(name, default)


# Database
DB_PATH = _get("SAFEPING_DB", os.path.join(_here, "safeping.db"))

# MQTT broker (Mosquitto)
MQTT_HOST = _get("MQTT_HOST", "localhost")
MQTT_PORT = int(_get("MQTT_PORT", "1883"))
MQTT_USER = _get("MQTT_USER")
MQTT_PASS = _get("MQTT_PASS")
TOPIC_ALERTS = "safeping/alerts"
TOPIC_REFERENCE = "safeping/reference"

# Message rules (see message-format.md)
MAX_PAYLOAD_BYTES = 512

# Location
PA_PER_FLOOR = float(_get("PA_PER_FLOOR", "42"))   # calibrate with the walk-the-building test
MAX_FLOOR = int(_get("MAX_FLOOR", "4"))
REF_MAX_AGE_S = int(_get("REF_MAX_AGE_S", "120"))   # ignore a Reference reading older than this

# Texts. If the Twilio values are missing the server prints the text instead (dry run).
TWILIO_SID = _get("TWILIO_SID")
TWILIO_TOKEN = _get("TWILIO_TOKEN")
TWILIO_FROM = _get("TWILIO_FROM")
DUTY_PHONES = [p.strip() for p in _get("DUTY_PHONES", "").split(",") if p.strip()]

# Dashboard
DASHBOARD_PASSWORD = _get("DASHBOARD_PASSWORD")      # leave unset for no login
HOST = _get("HOST", "0.0.0.0")
PORT = int(_get("PORT", "5000"))
