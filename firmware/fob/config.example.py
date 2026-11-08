# Fob settings. Copy this to the Fob as config.py (Thonny, Save as, MicroPython device)
# and fill in the real values there. The real config.py never goes in git.
# Anything left out uses the default in main.py.

DEVICE_ID = "FOB-001"
SECRET_KEY = "paste-the-key-from-add_device.py"   # python server/add_device.py FOB-001 "Name"

# WiFi. "none" skips WiFi completely and sends over LoRa only (bench mode).
WIFI_SSID = "none"
WIFI_PASSWORD = ""
WIFI_TIMEOUT_MS = 1500
SEND_ATTEMPTS = 1

# MQTT broker (the server computer's address on the same network)
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_USER = None
MQTT_PASS = None

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
# GPS_MAX_AGE_S = 60, LOW_BATTERY_PCT = 20
