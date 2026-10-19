"""SafePing Fob firmware (MicroPython).

Runs in Wokwi or on the real board. Follows message-format.md (version 1).

Button patterns
  1 press         STATUS      white blink, sent right away, never texts anyone
  2 presses       SUSPICIOUS  yellow slow blink, 2 s cancel window, then sent
  3 or more       MEDICAL     red fast blink + steady buzz, 2 s cancel window, then sent
  hold 5 s        SILENT      no light at all, buzz only, sent right away

Cancel window
  The alert is held for 2 s before it is sent. A quick tap cancels it and nothing
  is sent (message-format.md has no cancel message). Holding 5 s during the window
  turns it into a SILENT alert instead. For MEDICAL, extra presses in the first
  0.6 s count as part of the pattern and do not cancel.

Sending
  WiFi + MQTT. The counter is saved to flash BEFORE the message is sent, so a
  crash or power loss can never reuse a counter. Whatever happens, one line
  starting with SAFEPING_MSG is printed to the serial console with the full
  signed message, so you can check it against the server (server/replay_serial.py).

Settings come from config.py (see config.example.py). Anything missing uses the
default below. Pin numbers are for the ESP32 board in Wokwi. Change them for the
real board.
"""
import binascii
import hashlib
import json
import network
import time
from machine import Pin, PWM

try:
    from umqtt.simple import MQTTClient
except ImportError:
    MQTTClient = None
try:
    import config
except ImportError:
    config = None


def _cfg(name, default):
    return getattr(config, name, default) if config else default


# ---------- settings ----------
WIFI_SSID = _cfg("WIFI_SSID", "Wokwi-GUEST")
WIFI_PASSWORD = _cfg("WIFI_PASSWORD", "")
MQTT_HOST = _cfg("MQTT_HOST", "localhost")
MQTT_PORT = _cfg("MQTT_PORT", 1883)
MQTT_USER = _cfg("MQTT_USER", None)
MQTT_PASS = _cfg("MQTT_PASS", None)
MQTT_TOPIC = _cfg("MQTT_TOPIC", "safeping/alerts")
DEVICE_ID = _cfg("DEVICE_ID", "FOB-001")
SECRET_KEY = _cfg("SECRET_KEY", "paste-the-key-from-add_device.py")
COUNTER_FILE = _cfg("COUNTER_FILE", "counter.txt")

# Pins
BUTTON_PIN = _cfg("BUTTON_PIN", 0)            # button to GND, internal pull-up
LED_TYPE = _cfg("LED_TYPE", "rgb")            # "rgb" (Wokwi RGB LED) or "neopixel" (real build)
RGB_PINS = _cfg("RGB_PINS", (2, 4, 5))        # red, green, blue
RGB_COMMON_ANODE = _cfg("RGB_COMMON_ANODE", False)
NEOPIXEL_PIN = _cfg("NEOPIXEL_PIN", 8)
MOTOR_PIN = _cfg("MOTOR_PIN", 18)             # drives the PN2222 base (or a stand-in LED in Wokwi)

# Timing, in milliseconds
DEBOUNCE_MS = _cfg("DEBOUNCE_MS", 30)
MULTI_WINDOW_MS = _cfg("MULTI_WINDOW_MS", 600)   # gap that ends a press pattern
HOLD_MS = _cfg("HOLD_MS", 5000)                  # hold this long for SILENT
CANCEL_MS = _cfg("CANCEL_MS", 2000)              # cancel window for SUSPICIOUS and MEDICAL
COOLDOWN_MS = _cfg("COOLDOWN_MS", 3000)          # presses ignored this long after an alert
CONFIRM_MS = _cfg("CONFIRM_MS", 3000)            # solid color shown after the alert is sent
PRESS_TICK_MS = _cfg("PRESS_TICK_MS", 40)        # tiny buzz on each press (0 turns it off)
WIFI_TIMEOUT_MS = _cfg("WIFI_TIMEOUT_MS", 10000)
SEND_ATTEMPTS = _cfg("SEND_ATTEMPTS", 3)
LOOP_MS = 10

# Colors (red, green, blue 0-255)
WHITE = (255, 255, 255)
YELLOW = (255, 180, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
ORANGE = (255, 90, 0)
OFF = (0, 0, 0)

# Buzz patterns: list of (motor on? 1/0, milliseconds)
PATTERNS = {
    "tick": [(1, PRESS_TICK_MS)],
    "short": [(1, 150)],
    "one": [(1, 300)],
    "ok": [(1, 100), (0, 100), (1, 100)],
    "fail": [(1, 100), (0, 100), (1, 100), (0, 100), (1, 100)],
}

# States
IDLE, DOWN, COUNT, PENDING, LOCKOUT = "IDLE", "DOWN", "COUNT", "PENDING", "LOCKOUT"


# ---------- signing (message-format.md) ----------
SIGNED_FIELDS = ("v", "id", "type", "ctr", "ts", "lat", "lon", "acc", "p", "t", "bat")


def hmac_sha256(key, message):
    """HMAC-SHA256. MicroPython has no hmac module, so it is written out here."""
    block = 64
    if len(key) > block:
        key = hashlib.sha256(key).digest()
    key = key + b"\x00" * (block - len(key))
    inner = hashlib.sha256(bytes(b ^ 0x36 for b in key) + message).digest()
    return hashlib.sha256(bytes(b ^ 0x5C for b in key) + inner).digest()


def signing_string(msg):
    parts = []
    for name in SIGNED_FIELDS:
        value = msg.get(name)
        parts.append("" if value is None else str(value))
    return "|".join(parts)


def sign(msg):
    digest = hmac_sha256(SECRET_KEY.encode(), signing_string(msg).encode())
    return binascii.hexlify(digest).decode()


# ---------- clock ----------
# MicroPython counts seconds from 2000, the server wants Unix seconds (from 1970).
UNIX_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0


def unix_time():
    """Unix seconds, or None while the clock has obviously not been set."""
    now = int(time.time()) + UNIX_OFFSET
    return now if now > 1700000000 else None


# ---------- counter, saved in flash ----------
def next_counter():
    """Add 1, save it, then return it. Saved first so a crash never reuses a number."""
    try:
        with open(COUNTER_FILE) as f:
            last = int(f.read().strip())
    except OSError:
        last = -1                       # first boot, no file yet
    except ValueError:
        # File damaged. Jump ahead using the clock so the server does not see a replay.
        now = unix_time()
        last = now if now else 0
        print("counter file damaged, restarting from", last)
    counter = last + 1
    with open(COUNTER_FILE, "w") as f:
        f.write(str(counter))
    return counter


# ---------- sensors (stubs until the hardware is on the bench) ----------
def read_gps():
    """Return (lat_microdeg, lon_microdeg, accuracy_m) or None. Written when the GPS arrives."""
    return None


def read_sensors():
    """Return a dict that may hold p (pascals), t (hundredths of C), bat (percent)."""
    return {}


def lora_send(payload):
    """Fallback when WiFi fails. Written when the LoRa radio arrives. Return True if sent."""
    return False


# ---------- the message ----------
def build_message(kind):
    msg = {"v": 1, "id": DEVICE_ID, "type": kind, "ctr": next_counter()}
    ts = unix_time()
    if ts is not None:
        msg["ts"] = ts
    gps = read_gps()
    if gps:
        msg["lat"], msg["lon"], msg["acc"] = int(gps[0]), int(gps[1]), int(gps[2])
    for name, value in read_sensors().items():
        if name in ("p", "t", "bat") and value is not None:
            msg[name] = int(value)
    msg["sig"] = sign(msg)
    return msg


# ---------- network ----------
def wifi_connect(service=None):
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if not sta.isconnected():
        sta.connect(WIFI_SSID, WIFI_PASSWORD)
    start = time.ticks_ms()
    while not sta.isconnected() and time.ticks_diff(time.ticks_ms(), start) < WIFI_TIMEOUT_MS:
        if service:
            service(time.ticks_ms())
        time.sleep_ms(50)
    return sta.isconnected()


def mqtt_publish(payload):
    client = MQTTClient(DEVICE_ID, MQTT_HOST, port=MQTT_PORT, user=MQTT_USER or None,
                        password=MQTT_PASS or None, keepalive=30)
    client.connect()
    try:
        client.publish(MQTT_TOPIC, payload, qos=1)    # waits for the broker to say it has it
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


# ---------- LED ----------
class Led:
    def __init__(self):
        self.scale = 100                  # percent, lowered when the battery is low
        self.color = OFF
        self.on_ms = 0
        self.off_ms = 0
        self.start = 0
        self.end = None
        self.shown = None
        if LED_TYPE == "neopixel":
            import neopixel
            self.pixel = neopixel.NeoPixel(Pin(NEOPIXEL_PIN), 1)
            self.pwm = None
        else:
            self.pixel = None
            self.pwm = [PWM(Pin(p), freq=1000) for p in RGB_PINS]
        self._write(OFF)

    def _write(self, rgb):
        if rgb == self.shown:
            return
        self.shown = rgb
        r, g, b = [c * self.scale // 100 for c in rgb]
        if self.pixel is not None:
            self.pixel[0] = (r, g, b)
            self.pixel.write()
            return
        for pwm, value in zip(self.pwm, (r, g, b)):
            if RGB_COMMON_ANODE:
                value = 255 - value
            if hasattr(pwm, "duty_u16"):
                pwm.duty_u16(value * 257)
            else:
                pwm.duty(value * 4)

    def show(self, color, on_ms=0, off_ms=0, duration_ms=0):
        """on_ms = 0 means solid. duration_ms = 0 means until changed."""
        now = time.ticks_ms()
        self.color, self.on_ms, self.off_ms, self.start = color, on_ms, off_ms, now
        self.end = time.ticks_add(now, duration_ms) if duration_ms else None
        self.update(now)

    def off(self):
        self.color, self.end = OFF, None
        self._write(OFF)

    def update(self, now):
        if self.end is not None and time.ticks_diff(now, self.end) >= 0:
            self.off()
            return
        if self.on_ms and self.off_ms:
            phase = time.ticks_diff(now, self.start) % (self.on_ms + self.off_ms)
            self._write(self.color if phase < self.on_ms else OFF)
        else:
            self._write(self.color)


# ---------- vibration motor ----------
class Motor:
    def __init__(self):
        self.pin = Pin(MOTOR_PIN, Pin.OUT, value=0)
        self.queue = []
        self.level = 0
        self.until = None
        self.hold = False                 # True = buzz steadily until told otherwise

    def play(self, name):
        if name == "tick" and PRESS_TICK_MS <= 0:
            return
        self.queue = list(PATTERNS[name])
        self.until = None
        if name != "tick":
            print(">>> [VIBRATE: {}]".format(name))
        self.update(time.ticks_ms())

    def stop(self):
        self.queue = []
        self.level = 0
        self.until = None
        self.hold = False
        self.pin.value(0)

    def busy(self):
        return bool(self.queue) or (self.until is not None and time.ticks_diff(time.ticks_ms(), self.until) < 0)

    def update(self, now):
        if self.until is None or time.ticks_diff(now, self.until) >= 0:
            if self.queue:
                self.level, ms = self.queue.pop(0)
                self.until = time.ticks_add(now, ms)
            else:
                self.level, self.until = 0, None
        self.pin.value(1 if (self.hold or self.level) else 0)

    def run(self, name):
        """Play a pattern and wait for it to finish (used right before a slow network call)."""
        self.play(name)
        while self.busy():
            time.sleep_ms(5)
            self.update(time.ticks_ms())


# ---------- button ----------
class Button:
    def __init__(self):
        self.pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.raw = False
        self.state = False
        self.changed = 0

    def update(self, now):
        raw = self.pin.value() == 0
        if raw != self.raw:
            self.raw, self.changed = raw, now
        elif raw != self.state and time.ticks_diff(now, self.changed) >= DEBOUNCE_MS:
            self.state = raw
        return self.state


# ---------- the Fob ----------
class Fob:
    def __init__(self):
        self.led = Led()
        self.motor = Motor()
        self.btn = Button()
        self.state = IDLE
        self.count = 0
        self.press_start = 0
        self.last_release = 0
        self.pending = None
        self.pending_start = 0
        self.press_can_cancel = False
        self.in_press = False
        self.lockout_until = 0

    # --- start up ---
    def service(self, now):
        self.led.update(now)
        self.motor.update(now)

    def boot(self):
        print("SafePing Fob", DEVICE_ID)
        if SECRET_KEY.startswith("paste-the-key"):
            print("WARNING: SECRET_KEY is the placeholder. The server will reject every message.")
        self.led.show(WHITE, duration_ms=200)
        self.motor.run("tick")
        time.sleep_ms(250)
        self.led.show(ORANGE, 300, 300)
        if wifi_connect(self.service):
            print("WiFi connected")
            try:
                import ntptime
                ntptime.settime()
            except Exception:
                print("no NTP, timestamps may be missing or wrong")
        else:
            print("WiFi not connected yet, will retry when an alert is sent")
        self.led.off()
        self.refresh_battery()

    def refresh_battery(self):
        bat = read_sensors().get("bat")
        self.led.scale = 40 if (bat is not None and bat < 20) else 100

    # --- sending ---
    def send(self, kind):
        """Build, sign and send one message. Returns True if the broker accepted it."""
        self.motor.hold = self.motor.hold and kind == "MEDICAL"
        msg = build_message(kind)
        payload = json.dumps(msg)
        print("SAFEPING_MSG " + payload)
        for attempt in range(SEND_ATTEMPTS):
            try:
                if not wifi_connect(None):
                    raise OSError("no WiFi")
                mqtt_publish(payload)
                print("sent", kind, "ctr", msg["ctr"])
                return True
            except Exception as err:
                print("send attempt", attempt + 1, "failed:", err)
        if lora_send(payload):
            print("sent over LoRa", kind)
            return True
        print("NOT SENT", kind)
        return False

    def finish(self, kind, ok):
        """Show the result, then ignore presses for a short while."""
        self.motor.hold = False
        self.motor.stop()
        color = {"SUSPICIOUS": YELLOW, "MEDICAL": RED}.get(kind, WHITE)
        if kind == "SILENT":
            self.motor.play("ok" if ok else "fail")     # no light, ever
        elif kind == "STATUS":
            if ok:
                self.led.show(WHITE, 150, 150, 300)
                self.motor.play("short")
            else:
                self.led.show(ORANGE, duration_ms=CONFIRM_MS)
                self.motor.play("fail")
        elif ok:
            self.led.show(color, duration_ms=CONFIRM_MS)    # solid = confirmed
            self.motor.play("ok")
        else:
            self.led.show(ORANGE, duration_ms=CONFIRM_MS)   # orange = connection problem
            self.motor.play("fail")
        self.refresh_battery()
        self.pending = None
        if kind == "STATUS":
            self.state = IDLE            # low stakes, stay responsive
        else:
            self.state = LOCKOUT
            self.lockout_until = time.ticks_add(time.ticks_ms(), COOLDOWN_MS)

    # --- the three ways an alert starts ---
    def fire_now(self, kind):
        """STATUS and SILENT are sent immediately."""
        self.count = 0
        if kind == "SILENT":
            self.led.off()
            self.motor.run("short")      # tells the wearer the hold registered
        else:
            self.led.off()
        self.finish(kind, self.send(kind))

    def start_pending(self, kind, now):
        self.count = 0
        self.pending = kind
        self.pending_start = now
        self.press_can_cancel = False
        self.state = PENDING
        if kind == "MEDICAL":
            self.led.show(RED, 150, 150)
            self.motor.hold = True
        else:
            self.led.show(YELLOW, 500, 500)
            self.motor.play("one")

    def send_pending(self):
        kind = self.pending
        self.led.show(RED if kind == "MEDICAL" else YELLOW)     # solid while the slow part runs
        self.finish(kind, self.send(kind))

    def cancel_pending(self):
        print("CANCELLED", self.pending)
        self.pending = None
        self.motor.stop()
        self.led.show(GREEN, 150, 150, 600)
        self.motor.play("short")
        self.state = LOCKOUT
        self.lockout_until = time.ticks_add(time.ticks_ms(), COOLDOWN_MS)

    # --- the main step, called every few milliseconds ---
    def step(self, now):
        before = self.btn.state
        down = self.btn.update(now)
        pressed = down and not before
        released = before and not down
        self.service(now)

        if self.state == IDLE:
            if pressed:
                self.press_down(now)

        elif self.state == DOWN:
            if released:
                self.count += 1
                self.last_release = now
                if self.count >= 3:
                    self.start_pending("MEDICAL", now)
                else:
                    self.state = COUNT
            elif time.ticks_diff(now, self.press_start) >= HOLD_MS:
                self.fire_now("SILENT")

        elif self.state == COUNT:
            if pressed:
                self.press_down(now)
            elif time.ticks_diff(now, self.last_release) >= MULTI_WINDOW_MS:
                taps = self.count
                self.count = 0
                if taps == 1:
                    self.fire_now("STATUS")
                else:
                    self.start_pending("SUSPICIOUS", now)

        elif self.state == PENDING:
            self.step_pending(now, pressed, released, down)

        elif self.state == LOCKOUT:
            if not down and time.ticks_diff(now, self.lockout_until) >= 0:
                self.state = IDLE

    def press_down(self, now):
        self.state = DOWN
        self.press_start = now
        self.motor.play("tick")

    def step_pending(self, now, pressed, released, down):
        age = time.ticks_diff(now, self.pending_start)
        if pressed:
            self.press_start = now
            self.in_press = True
            # extra presses right after the 3rd MEDICAL press are part of the pattern
            self.press_can_cancel = age >= (MULTI_WINDOW_MS if self.pending == "MEDICAL" else 0)
            return
        if down and self.in_press:
            if time.ticks_diff(now, self.press_start) >= HOLD_MS:
                self.in_press = False
                self.pending = None
                self.motor.stop()
                self.fire_now("SILENT")     # situation got worse, go straight to SILENT
            return
        if released and self.in_press:
            self.in_press = False
            if self.press_can_cancel:
                self.cancel_pending()
            return
        if not down and age >= CANCEL_MS:
            self.send_pending()


def main():
    fob = Fob()
    fob.boot()
    while True:
        fob.step(time.ticks_ms())
        time.sleep_ms(LOOP_MS)


if __name__ == "__main__":
    main()
