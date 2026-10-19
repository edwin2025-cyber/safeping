# Copy this file to config.py and fill in the real values.
# config.py is ignored by git. Never put real values in this example file.

WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"

MQTT_HOST = "192.168.0.10"
MQTT_PORT = 1883
MQTT_USER = "your-mqtt-user"
MQTT_PASSWORD = "your-mqtt-password"

DEVICE_ID = "RELAY-01"  # up to 32 characters
# The Relay republishes Fob packets unchanged and does not sign them.
# Kept here in case the Relay needs its own key later.
SECRET_KEY = "paste-the-key-if-one-is-needed"
