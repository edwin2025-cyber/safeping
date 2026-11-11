# Fob settings. Copy this to the Fob as config.py (Thonny, Save as, MicroPython device)
# and fill in the real values there. The real config.py never goes in git.
# Anything left out uses the default in main.py.

DEVICE_ID = "FOB-001"
SECRET_KEY = "paste-the-key-from-add_device.py"   # python server/add_device.py FOB-001 "Name"

# WiFi. "none" skips WiFi completely and sends over LoRa only (bench mode).
WIFI_SSID = "none"
WIFI_PASSWORD = ""

# Cloud MQTT broker (EMQX Cloud Serverless). TLS only, port 8883.
MQTT_HOST = "your-deployment-address"
MQTT_PORT = 8883
MQTT_USER = "safeping-fob"
MQTT_PASSWORD = "the-fob-broker-password"
MQTT_TLS = True                          # never turn off for the cloud broker
MQTT_CA_FILE = "/certs/broker-ca.pem"    # copy the CA file here on the board

# WiFi time limits (milliseconds). After WIFI_BUDGET_MS the alert goes over LoRa.
WIFI_BUDGET_MS = 5000      # the whole WiFi attempt: join, DNS, TLS, connect, publish, ack
WIFI_JOIN_MS = 3000        # one WiFi join at press time, inside the budget
MQTT_ACK_WAIT_MS = 2000    # wait this long for the server's signed ack, inside the budget

# Watchdog: resets the board if the program freezes. Once on, it cannot be stopped,
# so the board resets WATCHDOG_MS after you press Ctrl+C in Thonny. Keep it off on the bench.
WATCHDOG_ENABLED = False

# Feedback
STATUS_SUCCESS_PATTERN = "ok"   # "ok" = two pulses like the other types, "short" = the old buzz

# Pins on the bench Fob
BUTTON_PIN = 1
LED_TYPE = "neopixel"
NEOPIXEL_PIN = 27
MOTOR_PIN = 3

# Timing
HOLD_MS = 2000      # hold this long for SILENT (the PDR said 5000)
CANCEL_MS = 2000    # cancel window for SUSPICIOUS and MEDICAL

# Other settings you can add here (defaults in main.py):
# LORA_CS = 26, LORA_RST = 6, I2C_SDA = 23, I2C_SCL = 24, BME280_ADDR = 0x77,
# MOTOR_STRENGTH = 100, LORA_ACK = True, ACK_WAIT_MS = 1000, LORA_TRIES = 3,
# GPS_MAX_AGE_S = 60, LOW_BATTERY_PCT = 20,
# WIFI_BOOT_MS = 8000 (join wait at power on), WIFI_RECONNECTS = 1, WIFI_RETRY_S = 30,
# NTP_RETRY_S = 1800, DNS_REFRESH_S = 3600, WATCHDOG_MS = 30000, SENDING_DIM_PCT = 15,
# WIFI_OFF_FOR_LORA = True (WiFi radio off during a LoRa fallback),
# WIFI_SETTLE_MS = 150 (pause after WiFi goes quiet, before the LoRa send)
