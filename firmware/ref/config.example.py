# Reference board settings. Copy this to the Reference board as config.py (Thonny,
# Save as, MicroPython device) and fill in the real values there. The real config.py
# never goes in git. Anything left out uses the default in main.py.

DEVICE_ID = "REF-001"
SECRET_KEY = "paste-the-key-from-add_device.py"   # python server/add_device.py REF-001 --role REF

# School WiFi
WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"

# Cloud MQTT broker (EMQX Cloud Serverless). TLS only, port 8883.
# Its own broker user, which may only publish to safeping/ref/#.
MQTT_HOST = "your-deployment-address"
MQTT_PORT = 8883
MQTT_USER = "safeping-ref"
MQTT_PASSWORD = "the-ref-broker-password"
MQTT_TLS = True                          # never turn off for the cloud broker
MQTT_CA_FILE = "/certs/broker-ca.pem"    # the same CA file as the Fob

# Watchdog: resets the board if the program freezes. On by default, because the board
# runs unattended for days. Once on it cannot be stopped: after Ctrl+C in Thonny the
# board resets 60 s later. Set it to False while you copy files, then back to True.
WATCHDOG_ENABLED = True

# Other settings you can add here (defaults in main.py):
# SAMPLE_MS = 2000 (one reading), PUBLISH_MS = 30000 (one REF message),
# BME280_ADDR = None (None tries 0x77, then 0x76), I2C_SDA = 23, I2C_SCL = 24,
# NEOPIXEL_PIN = 27, WATCHDOG_MS = 60000, COUNTER_BLOCK = 20 (counters per flash write),
# RECONNECT_MIN_S = 5, RECONNECT_MAX_S = 120, NTP_EVERY_S = 21600, WIFI_JOIN_MS = 15000,
# PING_EVERY_S = 60, MQTT_KEEPALIVE_S = 120
