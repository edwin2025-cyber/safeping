# Copy this file to config.py and fill it in. config.py is ignored by git so the
# secret key never goes to GitHub. In Wokwi, make a file called config.py in the project.

# --- who this Fob is (from: python add_device.py FOB-001 "Student Name") ---
DEVICE_ID = "FOB-001"
SECRET_KEY = "paste-the-key-from-add_device.py"

# --- WiFi ---
WIFI_SSID = "Wokwi-GUEST"        # Wokwi's built-in network. Use the school network on the real Fob.
WIFI_PASSWORD = ""

# --- MQTT broker ---
# On the real Fob this is the server's address.
# In Wokwi it cannot reach your laptop, so use a public test broker and a topic
# nobody else will pick (add random letters). Then check the output with
# server/replay_serial.py.
MQTT_HOST = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_USER = None                 # set both when your own Mosquitto needs a login
MQTT_PASS = None
MQTT_TOPIC = "safeping/alerts"   # Wokwi: "safeping-test-x7k2/alerts"

# --- pins (these are for the ESP32 board in Wokwi, change them for the real board) ---
# BUTTON_PIN = 0                 # button to GND
# LED_TYPE = "rgb"               # "rgb" for the Wokwi RGB LED, "neopixel" for the real build
# RGB_PINS = (2, 4, 5)           # red, green, blue
# NEOPIXEL_PIN = 8
# MOTOR_PIN = 18                 # to the PN2222 base. In Wokwi, an LED here stands in for the motor.

# --- timing in milliseconds (the defaults match the design, change only to experiment) ---
# MULTI_WINDOW_MS = 600
# HOLD_MS = 5000
# CANCEL_MS = 2000
# COOLDOWN_MS = 3000
