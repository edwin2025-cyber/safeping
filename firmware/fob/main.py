"""SafePing Fob firmware (MicroPython).

Runs in Wokwi or on the real board. Follows message-format.md (version 1).

Button patterns
  1 press         STATUS      white blink, sent right away, never texts anyone
  2 presses       SUSPICIOUS  yellow slow blink, 2 s cancel window, then sent
  3 or more       MEDICAL     red fast blink + pulsed buzz, 2 s cancel window, then sent
  hold            SILENT      no light at all, buzz only, sent right away
                              (hold time is HOLD_MS, 2 s on the bench in config.py)

Cancel window
  The alert is held for 2 s before it is sent. A quick tap cancels it and nothing
  is sent (message-format.md has no cancel message). Holding during the window
  turns it into a SILENT alert instead. For MEDICAL, extra presses in the first
  0.6 s count as part of the pattern and do not cancel.

Sending
  WiFi + MQTT over TLS first, LoRa second. One WiFi attempt per press, inside a hard
  time budget (WIFI_BUDGET_MS). A WiFi send counts only when the SERVER sends back a
  signed ack on safeping/ack/<id>. Otherwise the SAME message (same counter and
  signature) goes over LoRa. The counter is saved to flash BEFORE the message is sent,
  so a crash or power loss can never reuse a counter. Whatever happens, one line
  starting with SAFEPING_MSG is printed to the serial console with the full signed
  message, so you can check it against the server (server/replay_serial.py), and one
  SEND_RESULT line says which path was used, the result, the time and why.

Boot self-check
  At power on the Fob checks its key, counter file, LoRa radio, GPS, battery gauge and
  pressure sensor (WiFi too, as information only). Green 1 s = all passed. Steady red
  3 s = something failed, and the Fob keeps running with what works. It prints one
  SELF_CHECK line and sends a signed BOOT report to the server (selfcheck.py).

Retry queue
  An alert that is NOT confirmed on both paths is kept (retryq.py, saved in QUEUE_FILE)
  and the exact same signed message is sent again every RETRY_EVERY_MS for RETRY_FOR_MS.
  A button press always wins: it stops a retry at once.

Help is coming
  After an alert is confirmed over WiFi, the Fob listens for HELP_LISTEN_MS for the
  server's signed help message (sent when staff press Acknowledge): three slow pulses.
  SILENT never buzzes or lights (helplisten.py).

Button
  Every edge of the button is recorded by an interrupt (presslog.py), so a press during
  a slow network call is never lost, and its timing is the real one.

Settings come from config.py (see config.example.py). Anything missing uses the
default below. Pin numbers are for the ESP32 board in Wokwi. Change them for the
real board.
"""
import binascii
import hashlib
import json
import network
import os
import socket
import time
import machine
from machine import Pin, PWM

# Every import is here, at the top, so it happens once at boot. An import inside a
# function looks on the file system first (select, ssl, os and time can be replaced by a
# file of the same name), and that is a flash read. On 2026-11-11 the Fob crashed with
# a cache error while helplisten.py ran "import select" every 10 ms during HELP_LISTEN.
# tests/test_imports.py fails if any firmware module imports inside a function.
import sendpath                      # the send rules (sendpath.py must be on the board)
import presslog                      # button edges by interrupt (presslog.py)
import retryq                        # the retry queue (retryq.py)
import selfcheck                     # the boot self-check (selfcheck.py)
import helplisten                    # "help is coming" over WiFi (helplisten.py)

FW_VERSION = "2026.11.11c"           # sent in the BOOT report. Change it when main.py changes.

try:
    from umqtt_safe import MQTTClient, step_parts     # our MQTT client with timeouts
except ImportError:
    MQTTClient = None
    step_parts = None
try:
    import config
except ImportError:
    config = None
try:
    import ackcheck                  # signed acks (ackcheck.py must be on the board)
except ImportError:
    ackcheck = None
# Parts the Fob can run without. A missing one is reported at boot, as before.
try:
    import gps as gps_module         # GPS wing (gps.py)
except ImportError as _err:
    gps_module, GPS_IMPORT_ERROR = None, _err
try:
    import bme280                    # pressure sensor (bme280.py)
except ImportError as _err:
    bme280, BME_IMPORT_ERROR = None, _err
try:
    import max17048                  # battery gauge (max17048.py)
except ImportError as _err:
    max17048, GAUGE_IMPORT_ERROR = None, _err
try:
    import sx127x                    # LoRa radio (sx127x.py)
except ImportError as _err:
    sx127x, RADIO_IMPORT_ERROR = None, _err
try:
    import ntptime
except ImportError:
    ntptime = None
try:
    import ssl
except ImportError:
    ssl = None
try:
    import neopixel
except ImportError:
    neopixel = None


def _cfg(name, default):
    return getattr(config, name, default) if config else default


# ---------- settings ----------
WIFI_SSID = _cfg("WIFI_SSID", "Wokwi-GUEST")
WIFI_PASSWORD = _cfg("WIFI_PASSWORD", "")
MQTT_HOST = _cfg("MQTT_HOST", "your-deployment-address")
MQTT_PORT = _cfg("MQTT_PORT", 8883)
MQTT_USER = _cfg("MQTT_USER", None)
MQTT_PASSWORD = _cfg("MQTT_PASSWORD", _cfg("MQTT_PASS", None))   # MQTT_PASS is the old name
MQTT_TLS = _cfg("MQTT_TLS", True)
MQTT_CA_FILE = _cfg("MQTT_CA_FILE", "/certs/broker-ca.pem")
DEVICE_ID = _cfg("DEVICE_ID", "FOB-001")
ALERT_TOPIC = "safeping/alert/" + DEVICE_ID       # the Fob publishes here
ACK_TOPIC = "safeping/ack/" + DEVICE_ID           # the server's signed ack comes back here

# WiFi time limits, in milliseconds
WIFI_BUDGET_MS = _cfg("WIFI_BUDGET_MS", 5000)     # the whole WiFi attempt, then LoRa
WIFI_JOIN_MS = _cfg("WIFI_JOIN_MS", 3000)         # one join at press time, inside the budget
MQTT_ACK_WAIT_MS = _cfg("MQTT_ACK_WAIT_MS", 2000) # the server's ack, inside the budget
WIFI_BOOT_MS = _cfg("WIFI_BOOT_MS", _cfg("WIFI_TIMEOUT_MS", 8000))   # the join at power on
WIFI_RECONNECTS = _cfg("WIFI_RECONNECTS", 1)      # driver retries per join, so a bad name fails fast
WIFI_OFF_FOR_LORA = _cfg("WIFI_OFF_FOR_LORA", True)  # WiFi radio fully off during a LoRa fallback
WIFI_SETTLE_MS = _cfg("WIFI_SETTLE_MS", 150)      # pause after WiFi goes quiet, before LoRa sends
WIFI_RESET_MS = _cfg("WIFI_RESET_MS", 200)        # radio off this long in a WiFi reset
WIFI_RETRY_S = _cfg("WIFI_RETRY_S", 30)           # rejoin in the background this often while idle
NTP_RETRY_S = _cfg("NTP_RETRY_S", 1800)           # retry NTP this often until it works
DNS_REFRESH_S = _cfg("DNS_REFRESH_S", 3600)       # look the broker up again this often while idle
WATCHDOG_ENABLED = _cfg("WATCHDOG_ENABLED", False)   # see watchdog_start() before turning on
WATCHDOG_MS = _cfg("WATCHDOG_MS", 30000)
SECRET_KEY = _cfg("SECRET_KEY", "paste-the-key-from-add_device.py")
SECRET_KEY_LEN = _cfg("SECRET_KEY_LEN", 32)      # add_device.py makes 32 hex characters
COUNTER_FILE = _cfg("COUNTER_FILE", "counter.txt")

# Retry queue (alerts not confirmed on both paths)
RETRY_EVERY_MS = _cfg("RETRY_EVERY_MS", 30000)   # try again this often
RETRY_FOR_MS = _cfg("RETRY_FOR_MS", 600000)      # for this long, then give up
RETRY_MAX = _cfg("RETRY_MAX", 5)                 # alerts kept at most
QUEUE_FILE = _cfg("QUEUE_FILE", "queue.json")    # in flash, so a reboot does not lose them

# Help is coming (WiFi): listen this long after a WiFi confirm. 0 = off.
HELP_LISTEN_MS = _cfg("HELP_LISTEN_MS", 120000)
HELP_TOPIC = "safeping/help/" + DEVICE_ID
HELP_KINDS = ("SUSPICIOUS", "MEDICAL", "SILENT")   # STATUS is not acknowledged by staff

# Boot self-check
GPS_CHECK_MS = _cfg("GPS_CHECK_MS", 5000)        # the GPS must send data within this after start
CHECK_OK_MS = 1000                               # green this long when every check passed
CHECK_FAIL_MS = 3000                             # steady red this long when one failed

# Pins
BUTTON_PIN = _cfg("BUTTON_PIN", 0)            # button to GND, internal pull-up
LED_TYPE = _cfg("LED_TYPE", "rgb")            # "rgb" (Wokwi RGB LED) or "neopixel" (real build)
RGB_PINS = _cfg("RGB_PINS", (2, 4, 5))        # red, green, blue
RGB_COMMON_ANODE = _cfg("RGB_COMMON_ANODE", False)
NEOPIXEL_PIN = _cfg("NEOPIXEL_PIN", 8)
MOTOR_PIN = _cfg("MOTOR_PIN", 18)             # drives the PN2222 base (or a stand-in LED in Wokwi)
MOTOR_STRENGTH = _cfg("MOTOR_STRENGTH", 100)  # percent. PWM duty while the motor is on
MOTOR_FREQ = _cfg("MOTOR_FREQ", 200)          # PWM switching speed in Hz
MOTOR_MAX_MS = _cfg("MOTOR_MAX_MS", 5000)     # safety cap: the motor never stays on longer
MEDICAL_PULSE_ON_MS = _cfg("MEDICAL_PULSE_ON_MS", 200)    # MEDICAL cancel window buzz
MEDICAL_PULSE_OFF_MS = _cfg("MEDICAL_PULSE_OFF_MS", 100)
RESULT_GAP_MS = _cfg("RESULT_GAP_MS", 300)    # silence before the sent / not sent buzz

# LoRa radio (the fallback when WiFi fails). These are the bench wiring.
LORA_SCK = _cfg("LORA_SCK", 10)
LORA_MOSI = _cfg("LORA_MOSI", 8)
LORA_MISO = _cfg("LORA_MISO", 9)
LORA_CS = _cfg("LORA_CS", 26)
LORA_RST = _cfg("LORA_RST", 6)

# GPS wing (UART). Wing TX goes to the board RX pin, wing RX to the board TX pin.
GPS_UART = _cfg("GPS_UART", 1)
GPS_TX = _cfg("GPS_TX", 11)
GPS_RX = _cfg("GPS_RX", 12)
GPS_MAX_AGE_S = _cfg("GPS_MAX_AGE_S", 60)         # a fix older than this is not sent

# I2C bus: BME280 on the Qwiic port and the board's own MAX17048 battery gauge (0x36).
# Bench scan 2026-11-07: I2C(0) is SDA 23, SCL 24 and shows 0x36 and 0x77.
I2C_SDA = _cfg("I2C_SDA", 23)
I2C_SCL = _cfg("I2C_SCL", 24)
BME280_ADDR = _cfg("BME280_ADDR", 0x77)            # SparkFun default. 0x76 if the jumper is cut
LOW_BATTERY_PCT = _cfg("LOW_BATTERY_PCT", 20)      # LED dims below this

# Timing, in milliseconds
DEBOUNCE_MS = _cfg("DEBOUNCE_MS", 30)
MULTI_WINDOW_MS = _cfg("MULTI_WINDOW_MS", 600)   # gap that ends a press pattern
HOLD_MS = _cfg("HOLD_MS", 5000)                  # hold this long for SILENT
CANCEL_MS = _cfg("CANCEL_MS", 2000)              # cancel window for SUSPICIOUS and MEDICAL
COOLDOWN_MS = _cfg("COOLDOWN_MS", 3000)          # presses ignored this long after an alert
CONFIRM_MS = _cfg("CONFIRM_MS", 3000)            # solid color shown after the alert is sent
PRESS_TICK_MS = _cfg("PRESS_TICK_MS", 0)         # buzz on each press. 0 = off (Edwin's choice
                                                 # 2026-11-07: 40 ms was too short to feel)
STATUS_SUCCESS_PATTERN = _cfg("STATUS_SUCCESS_PATTERN", "ok")   # "ok" (two pulses) or "short"
SENDING_DIM_PCT = _cfg("SENDING_DIM_PCT", 15)    # brightness of the "sending" light, percent
LORA_ACK = _cfg("LORA_ACK", True)                # wait for the Relay to answer "ACK <id> <ctr>"
ACK_WAIT_MS = _cfg("ACK_WAIT_MS", 1000)          # how long to listen for the ack after each send
LORA_TRIES = _cfg("LORA_TRIES", 3)               # sends of the same message before giving up
ACK_KEY = ackcheck.ack_key(SECRET_KEY.encode()) if ackcheck else None
HELP_KEY = ackcheck.help_key(SECRET_KEY.encode()) if ackcheck and hasattr(ackcheck, "help_key") else None
LOOP_MS = 10

# Colors (red, green, blue 0-255). One kind of meaning per color (docs/led-patterns.md):
#   RED     MEDICAL only            YELLOW  SUSPICIOUS only
#   GREEN   good news               ORANGE  a problem
#   BLUE    the Fob busy with itself (starting up, joining WiFi)
#   WHITE   STATUS only (the dim "sending" light)
WHITE = (255, 255, 255)
YELLOW = (255, 180, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
ORANGE = (255, 45, 0)        # was (255, 90, 0), which looked yellow on the NeoPixel
BLUE = (0, 0, 255)
OFF = (0, 0, 0)

# Buzz patterns: list of (motor on? 1/0, milliseconds)
# Chosen on the bench 2026-11-07 with tests/motor_test.py. The motor needs about
# 50 to 100 ms to spin up, so 100 ms pulses felt too weak. "ok" and "fail" must feel
# different without looking, because SILENT has no light.
PATTERNS = {
    "tick": [(1, PRESS_TICK_MS)],
    "short": [(1, 150)],
    "one": [(1, 300)],
    "ok": [(1, 250), (0, 150), (1, 250)],      # sent: two medium buzzes
    "fail": [(1, 1200)],                        # not sent: one long buzz
    "help": [(1, 400), (0, 400), (1, 400), (0, 400), (1, 400)],   # help is coming: three slow pulses
}
if STATUS_SUCCESS_PATTERN not in PATTERNS:
    STATUS_SUCCESS_PATTERN = "ok"

# States
IDLE, DOWN, COUNT, PENDING, LOCKOUT = "IDLE", "DOWN", "COUNT", "PENDING", "LOCKOUT"


# ---------- signing (message-format.md) ----------
SIGNED_FIELDS = ("v", "id", "type", "ctr", "ts", "lat", "lon", "acc", "p", "t", "bat")
BOOT_FIELDS = ("fail", "wifi", "fw", "rst")      # signed after the others, BOOT only


class PressStop(Exception):
    """A button press stopped a retry or the boot report. No __init__ (MicroPython 1.27)."""
    pass


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
    for name in SIGNED_FIELDS + BOOT_FIELDS if msg.get("type") == "BOOT" else SIGNED_FIELDS:
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
_gps = None


def gps_start():
    """Start the GPS wing. Returns True if it started. The Fob works without it."""
    global _gps
    if gps_module is None:
        print("GPS off:", GPS_IMPORT_ERROR)
        _gps = None
        return False
    try:
        _gps = gps_module.GPS(uart_id=GPS_UART, tx=GPS_TX, rx=GPS_RX)
        return True
    except Exception as err:             # no gps.py on the board, or the pins are wrong
        print("GPS off:", err)
        _gps = None
        return False


def gps_poll():
    """Read any new GPS data. Called many times a second so the buffer never fills."""
    if _gps is not None:
        try:
            _gps.update()
        except Exception as err:
            print("GPS read error:", err)


def read_gps():
    """Return (lat_microdeg, lon_microdeg, accuracy_m) or None if there is no recent fix."""
    if _gps is None or not _gps.has_fix or _gps.lat_e6 is None:
        return None
    age = _gps.age_s()
    if age is None or age > GPS_MAX_AGE_S:
        return None
    try:
        acc = int(float(_gps.hdop) * 5)  # rough: HDOP times about 5 m
    except ValueError:
        acc = 10
    return _gps.lat_e6, _gps.lon_e6, max(acc, 1)


_bme = None
_gauge = None


def sensors_start():
    """Start the BME280 and the battery gauge. Returns a short status line.
    The Fob still works if either one is missing."""
    global _bme, _gauge
    try:
        i2c = machine.I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=400000)
    except Exception as err:
        return "I2C off: {}".format(err)
    parts = []
    try:
        if bme280 is None:
            raise BME_IMPORT_ERROR
        _bme = bme280.BME280(i2c, BME280_ADDR)
        parts.append("pressure on")
    except Exception as err:            # no bme280.py, not plugged in, or wrong address
        _bme = None
        parts.append("pressure off ({})".format(err))
    try:
        if max17048 is None:
            raise GAUGE_IMPORT_ERROR
        _gauge = max17048.MAX17048(i2c)
        parts.append("battery gauge on")
    except Exception as err:
        _gauge = None
        parts.append("battery gauge off ({})".format(err))
    return ", ".join(parts)


def read_battery():
    """Battery percent, or None if there is no gauge.
    Note: with no LiPo plugged in, the gauge still answers but the number means nothing."""
    if _gauge is None:
        return None
    try:
        return _gauge.percent()
    except Exception as err:
        print("battery read error:", err)
        return None


def read_sensors():
    """Return a dict that may hold p (pascals), t (hundredths of C), bat (percent).
    A sensor that fails is left out, so the alert still goes out."""
    out = {}
    if _bme is not None:
        try:
            p, t = _bme.read()
            if p is not None:
                out["p"], out["t"] = p, t
        except Exception as err:
            print("pressure read error:", err)
    bat = read_battery()
    if bat is not None:
        out["bat"] = bat
    return out


_radio = None


def _lora_radio():
    """Start the radio the first time it is needed, then keep using it."""
    global _radio
    if _radio is None:
        if sx127x is None:
            raise OSError("sx127x.py missing: {}".format(RADIO_IMPORT_ERROR))
        spi = machine.SPI(1, baudrate=1000000, polarity=0, phase=0,
                  sck=Pin(LORA_SCK), mosi=Pin(LORA_MOSI), miso=Pin(LORA_MISO))
        radio = sx127x.SX127x(spi, Pin(LORA_CS, Pin.OUT, value=1), Pin(LORA_RST, Pin.OUT, value=1))
        radio.begin()                    # raises OSError if the radio does not answer
        _radio = radio
    return _radio


def _lora_report(radio):
    """Print what the radio says about itself, so a failure in the log shows its cause.
    version 0x00 or 0xff = the board cannot talk to the radio (wire or power).
    mode without 0x80 = the radio reset and lost its LoRa settings."""
    if radio is None:
        return
    try:
        print("LoRa check: version 0x{:02x}, mode 0x{:02x}".format(
            radio.read_reg(0x42), radio.read_reg(0x01)))
    except Exception as err:
        print("LoRa check failed:", err)


def lora_send(payload):
    """Fallback when WiFi fails. Sends the signed message as one LoRa packet.
    Returns True if the radio says the packet left the antenna.
    If the first try fails, the radio is set up again from scratch and tried once more."""
    global _radio
    data = payload.encode()
    if len(data) > 255:                  # retrying would not help, so stop here
        print("LoRa failed: message is", len(data), "bytes, the limit is 255")
        return False
    for attempt in (1, 2):
        try:
            if _lora_radio().send(data):
                if attempt == 2:
                    print("LoRa worked after setting the radio up again")
                return True
            print("LoRa failed: the radio never finished sending (timeout)")
        except Exception as err:         # no radio, bad wiring, or radio lost its settings
            print("LoRa failed:", err)
        _lora_report(_radio)
        _radio = None                    # next _lora_radio() call runs begin() again
        if attempt == 1:
            print("LoRa: setting the radio up again and trying once more")
    return False


def _receive(left, stop):
    """radio.receive(), stopping early when stop() says so. An older sx127x.py without
    the stop option still works, it just cannot stop early."""
    radio = _lora_radio()
    if stop is None:
        return radio.receive(timeout_ms=left)
    try:
        return radio.receive(timeout_ms=left, stop=stop)
    except TypeError:
        return radio.receive(timeout_ms=left)


def _wait_for_ack(expected, wait_ms, stop=None):
    """Listen up to wait_ms for the exact signed ack. Other packets (another Fob's
    alert, noise) are ignored and listening continues until the time is up.
    An ack for this Fob with a wrong signature is reported and ignored."""
    deadline = time.ticks_add(time.ticks_ms(), wait_ms)
    while True:
        watchdog_feed()
        if stop is not None and stop():
            return False
        left = time.ticks_diff(deadline, time.ticks_ms())
        if left <= 0:
            return False
        try:
            packet = _receive(left, stop)
        except Exception as err:
            print("ACK wait failed:", err)
            return False
        if packet is None:
            return False
        if packet[0] == expected:
            return True
        if packet[0].startswith(expected[:expected.rfind(b" ") + 1]):
            print("ACK rejected: bad signature")       # someone faking or replaying an ack
        elif packet[0].startswith(b"ACK " + DEVICE_ID.encode() + b" "):
            print("ACK rejected: not for this alert")


def lora_send_confirmed(payload, ctr, sig, stop=None):
    """Send over LoRa and wait for the Relay to confirm it stored the alert.

    The Relay stores the alert in its flash, then answers with a signed ack
    "ACK <id> <ctr> <mac>" (see ackcheck.py). If no valid ack comes back, the SAME
    message (same ctr, same signature) is sent again, up to LORA_TRIES times.
    Returns:
      "confirmed"    the Relay stored it and sent a valid signed ack
      "unconfirmed"  it left the antenna but no ack came back (the Relay may still have it)
      "failed"       the radio could not send at all
      "sent"         acks are switched off (LORA_ACK = False) and it left the antenna
    Note: the ack proves the Relay stored it, not yet that the server saved it.
    stop (retries only): when it returns True, no more sends and the ack wait ends."""
    if not LORA_ACK:
        return "sent" if lora_send(payload) else "failed"
    if ACK_KEY is None:                  # no ackcheck.py: we cannot check acks, so never claim one
        if not lora_send(payload):
            return "failed"
        print("ACK not checked: ackcheck.py is missing on the Fob")
        return "unconfirmed"
    expected = ackcheck.ack_text(ACK_KEY, DEVICE_ID, ctr, sig).encode()
    sent_once = False
    for attempt in range(1, LORA_TRIES + 1):
        if stop is not None and stop():
            return "unconfirmed" if sent_once else "failed"
        if not lora_send(payload):       # radio problem (it already retried inside)
            return "unconfirmed" if sent_once else "failed"
        sent_once = True
        if _wait_for_ack(expected, ACK_WAIT_MS, stop):
            print("ACK received (try {})".format(attempt))
            return "confirmed"
        print("ACK missing (try {} of {})".format(attempt, LORA_TRIES))
    return "unconfirmed"


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


# ---------- watchdog ----------
_wdt = None


def watchdog_start():
    """Hardware watchdog: resets the board if the program stops feeding it for WATCHDOG_MS.
    Off by default. Once started on the ESP32 it CANNOT be stopped, so after Ctrl+C in
    Thonny the board resets WATCHDOG_MS later. Turn it on only for field use."""
    global _wdt
    if not WATCHDOG_ENABLED:
        return False
    try:
        _wdt = machine.WDT(timeout=WATCHDOG_MS)
        return True
    except Exception as err:
        print("watchdog not started:", err)
        return False


def watchdog_feed():
    if _wdt is not None:
        _wdt.feed()


# ---------- network ----------
_wlan = None
_broker_addr = None               # the broker's address from the last good DNS lookup
_tls_ctx = None
STAT_CONNECTING = getattr(network, "STAT_CONNECTING", 1001)
_JOIN_FAILED = tuple(getattr(network, name) for name in (
    "STAT_NO_AP_FOUND", "STAT_WRONG_PASSWORD", "STAT_CONNECT_FAIL", "STAT_ASSOC_FAIL",
    "STAT_HANDSHAKE_TIMEOUT", "STAT_BEACON_TIMEOUT") if hasattr(network, name))


def _sta():
    """The WiFi interface, switched on if needed (it is switched off for LoRa sends).
    Never used when WiFi is off in config.py."""
    global _wlan
    if _wlan is None:
        _wlan = network.WLAN(network.STA_IF)
    if not _wlan.active():
        _wlan.active(True)
        try:
            # Few driver retries per join, so a wrong name ends the join quickly
            # instead of retrying forever in the background.
            _wlan.config(reconnects=WIFI_RECONNECTS)
        except Exception:
            pass
    return _wlan


def wifi_connected():
    try:
        return _wlan is not None and _wlan.active() and _wlan.isconnected()
    except Exception:
        return False


def wifi_joining():
    try:
        return (_wlan is not None and _wlan.active() and not _wlan.isconnected()
                and _wlan.status() == STAT_CONNECTING)
    except Exception:
        return False


def wifi_start_join():
    """Start a join without waiting. If one is already running, leave it alone: calling
    connect() on top of it is what printed "sta is connecting, cannot set config".
    Raises if the driver refuses (for example "Wifi Internal State Error")."""
    sta = _sta()
    if sta.isconnected() or wifi_joining():
        return
    sta.connect(WIFI_SSID, WIFI_PASSWORD)


def wifi_reset():
    """Get the WiFi driver out of a stuck state: disconnect, radio off, short wait,
    radio on. Takes about WIFI_RESET_MS."""
    if _wlan is not None:
        try:
            _wlan.disconnect()
        except Exception:
            pass
        try:
            _wlan.active(False)
        except Exception:
            pass
    time.sleep_ms(WIFI_RESET_MS)
    _sta()                                  # radio on again, driver settings again


def wifi_join(budget, service=None, join_ms=None):
    """Join inside the budget (a sendpath.Budget). Waits on a join already in progress.
    A "Wifi Internal State Error" gets one WiFi reset and one more try if time allows.
    Returns (connected, reason, detail)."""
    connected, reason, detail = sendpath.join_wifi(
        budget, budget.total if join_ms is None else join_ms, wifi_start_join,
        lambda ms: wifi_wait(ms, service), wifi_reset, WIFI_RESET_MS, print)
    if not connected and detail is not None:
        print("WiFi join failed:", sendpath.plain_error(detail))
    return connected, reason, detail


def wifi_wait(wait_ms, service=None):
    """Wait up to wait_ms for the join to finish. Stops early if the driver says the
    name or password is wrong."""
    sta = _sta()
    deadline = time.ticks_add(time.ticks_ms(), wait_ms)
    while not sta.isconnected():
        now = time.ticks_ms()
        if time.ticks_diff(deadline, now) <= 0:
            break
        try:
            if sta.status() in _JOIN_FAILED:
                break
        except Exception:
            pass
        if service:
            service(now)
        watchdog_feed()
        time.sleep_ms(20)
    return sta.isconnected()


def wifi_quiet(for_lora=False):
    """Stop any join and drop the link.

    for_lora=True (right before a LoRa send) also switches the WiFi radio off
    (WIFI_OFF_FOR_LORA) and waits WIFI_SETTLE_MS for the 3V3 supply to settle.
    Twice on 2026-11-10 LoRa misbehaved right after WiFi activity: all 3 Relay acks
    missed (pre-test 3), then a LoRa send that never finished (ctr 207). Disconnecting
    itself makes WiFi transmit (a goodbye frame), so the wait comes after it.
    The idle upkeep switches WiFi back on and rejoins in the background, so the next
    press usually finds WiFi connected again. If not, the join at press time is inside
    WIFI_JOIN_MS as before."""
    if _wlan is None:
        return
    touched = False
    try:
        if _wlan.active() and (_wlan.isconnected() or wifi_joining()):
            _wlan.disconnect()
            touched = True
        if for_lora and WIFI_OFF_FOR_LORA and _wlan.active():
            _wlan.active(False)
            touched = True
    except Exception as err:
        print("WiFi disconnect error:", err)
        touched = True
    if for_lora and touched and WIFI_SETTLE_MS > 0:
        time.sleep_ms(WIFI_SETTLE_MS)


def ntp_sync():
    """Set the clock from NTP. Only called while idle, never during a send."""
    try:
        if ntptime is None:
            raise OSError("ntptime module missing")
        ntptime.settime()
        print("clock set by NTP, year", time.gmtime()[0])
        return True
    except Exception as err:
        print("no NTP ({}), will retry in {} min".format(err, NTP_RETRY_S // 60))
        return False


def clock_year():
    return time.gmtime()[0]


def dns_lookup():
    """Look the broker up and save the address. Returns the address or None."""
    global _broker_addr
    try:
        addr = socket.getaddrinfo(MQTT_HOST, MQTT_PORT, 0, socket.SOCK_STREAM)[0][-1]
    except Exception as err:
        print("DNS lookup failed for the broker:", err)
        return None
    _broker_addr = addr
    return addr


def broker_address():
    """The saved address if there is one (no DNS wait on a press), else a lookup now.
    The host name is still used for the TLS certificate check."""
    if _broker_addr is not None:
        return _broker_addr, True
    return dns_lookup(), False


def forget_broker_address():
    global _broker_addr
    _broker_addr = None


_ca_found = None


def ca_present():
    """Checked once (at boot), then remembered, so a send never reads flash for it.
    Copy the CA file, then press RST."""
    global _ca_found
    if _ca_found is None:
        try:
            os.stat(MQTT_CA_FILE)
            _ca_found = True
        except OSError:
            _ca_found = False
    return _ca_found


def tls_context():
    """TLS settings, made once. Certificate checks are always on.
    Loads the CA as given (PEM or DER). If the board refuses PEM, it is turned into DER."""
    global _tls_ctx
    if _tls_ctx is None:
        if ssl is None:
            raise OSError("ssl module missing")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = ssl.CERT_REQUIRED
        with open(MQTT_CA_FILE, "rb") as f:
            data = f.read()
        try:
            ctx.load_verify_locations(cadata=data)
        except Exception as err:
            der = sendpath.pem_to_der(data)
            if der is data:
                raise
            print("CA as PEM refused ({}), loading it as DER".format(err))
            ctx.load_verify_locations(cadata=der)
        _tls_ctx = ctx
    return _tls_ctx


def wifi_send(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
    """One WiFi/MQTT attempt inside the budget. Never retries.
    Returns (confirmed, reason, published, detail).
    published = the broker took it (PUBACK). detail = the error behind a failure, or None.
    keep_open: a list. If given, the Fob also subscribes to its help topic, and after a
    confirm the open client is put in the list (for the help listener).
    stop: a function that ends the attempt early when it returns True (retries only)."""
    reason = sendpath.skip_reason(WIFI_SSID, MQTTClient is not None, ACK_KEY is not None,
                                  MQTT_TLS, (not MQTT_TLS) or ca_present(), clock_year())
    if reason:
        if reason == "ca_missing":
            print("TLS CA file missing:", MQTT_CA_FILE)
        elif reason == "clock_not_set":
            print("clock not set, WiFi skipped (TLS needs the date)")
        return False, reason, False, None

    expected = ackcheck.ack_text(ACK_KEY, DEVICE_ID, ctr, sig).encode()
    ack_topic = ACK_TOPIC.encode()
    got = []

    help_topic = HELP_TOPIC.encode()

    def on_message(topic, msg):
        if topic == ack_topic and msg.strip() == expected:
            got.append(True)
        elif topic == help_topic:
            print("help message before the ack, ignored (not waiting for help yet)")
        else:
            print("WiFi ack ignored: not for this alert")

    connected, reason, detail = wifi_join(budget, service, WIFI_JOIN_MS)
    if not connected:
        return False, reason, False, detail
    addr, used_saved_addr = broker_address()
    if addr is None:
        return False, "dns_failed", False, "no address for the broker"
    if budget.left() <= 0:
        return False, "budget_exceeded", False, None
    try:
        ctx = tls_context() if MQTT_TLS else None
    except Exception as err:
        print("WiFi send failed at tls: could not load the CA file:", sendpath.plain_error(err))
        return False, "tls_failed", False, err

    client = MQTTClient(DEVICE_ID, user=MQTT_USER, password=MQTT_PASSWORD, keepalive=30)
    client.set_callback(on_message)
    listen = keep_open is not None and HELP_KEY is not None and HELP_LISTEN_MS > 0
    confirmed, reason, published, detail, step = sendpath.mqtt_attempt(
        client, addr, budget, ctx, MQTT_HOST, ACK_TOPIC, ALERT_TOPIC, payload,
        MQTT_ACK_WAIT_MS, got, step_parts, help_topic=HELP_TOPIC if listen else None,
        keep_open=keep_open if listen else None, stop=stop)
    if not confirmed:
        if reason == "no_server_ack":
            print(detail)
        else:
            print("WiFi send failed at {}: {}".format(step, sendpath.plain_error(detail)))
            if step in ("connect", "tls") and used_saved_addr:
                forget_broker_address()                    # maybe the broker moved: look up again
    return confirmed, reason, published, detail


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
            if neopixel is None:
                raise ImportError("neopixel module missing")
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
    """Vibration motor through the PN2222 on MOTOR_PIN.

    PWM sets the strength (MOTOR_STRENGTH percent).
    play(name)      runs one pattern from PATTERNS.
    start_hold()    pulses (MEDICAL_PULSE_ON_MS on, MEDICAL_PULSE_OFF_MS off) until stop().
    before_send()   turns the motor fully off right before the radio or WiFi sends.
    Safety: the motor is never on for longer than MOTOR_MAX_MS in one go, and a pulsed
    hold never lasts longer than MOTOR_MAX_MS either.

    The motor must never run while the radio transmits. Bench test 2026-11-07: with the
    motor on, every LoRa send timed out (version 0x12, mode 0x81, TX never finished).
    With the motor off, the same send worked. Motor and radio share the 3V3 supply."""

    def __init__(self):
        self.pwm = PWM(Pin(MOTOR_PIN), freq=MOTOR_FREQ, duty_u16=0)
        self.on_duty = 65535 * max(0, min(100, MOTOR_STRENGTH)) // 100
        self.queue = []
        self.level = 0
        self.until = None
        self.hold = False                 # True = pulse until told otherwise (MEDICAL)
        self.hold_start = 0
        self.on_since = None
        self.shown = False

    def _duty(self, value):
        if hasattr(self.pwm, "duty_u16"):
            self.pwm.duty_u16(value)
        else:
            self.pwm.duty(value // 64)

    def _write(self, on, now):
        if on:
            if self.on_since is None:
                self.on_since = now
            elif time.ticks_diff(now, self.on_since) > MOTOR_MAX_MS:
                print("motor safety cap reached, turning it off")
                self.stop()
                return
        else:
            self.on_since = None
        on = bool(on)
        if on != self.shown:
            self.shown = on
            self._duty(self.on_duty if on else 0)

    def play(self, name, gap_ms=0):
        """gap_ms = silence first, so the pattern does not blur into a buzz before it."""
        if name == "tick" and PRESS_TICK_MS <= 0:
            return
        self.queue = ([(0, gap_ms)] if gap_ms else []) + list(PATTERNS[name])
        self.until = None
        if name != "tick":
            print(">>> [VIBRATE: {}]".format(name))
        self.update(time.ticks_ms())

    def start_hold(self):
        self.hold = True
        self.hold_start = time.ticks_ms()
        self.update(self.hold_start)

    def before_send(self):
        """Called right before sending. Motor fully off while the radio transmits."""
        self.stop()

    def stop(self):
        self.queue = []
        self.level = 0
        self.until = None
        self.hold = False
        self.on_since = None
        self.shown = False
        self._duty(0)

    def busy(self):
        return bool(self.queue) or (self.until is not None and time.ticks_diff(time.ticks_ms(), self.until) < 0)

    def update(self, now):
        if self.until is None or time.ticks_diff(now, self.until) >= 0:
            if self.queue:
                self.level, ms = self.queue.pop(0)
                self.until = time.ticks_add(now, ms)
            else:
                self.level, self.until = 0, None
        pulse = False
        if self.hold:
            elapsed = time.ticks_diff(now, self.hold_start)
            if elapsed > MOTOR_MAX_MS:
                print("motor safety cap reached, ending the MEDICAL buzz")
                self.hold = False
            else:
                pulse = elapsed % (MEDICAL_PULSE_ON_MS + MEDICAL_PULSE_OFF_MS) < MEDICAL_PULSE_ON_MS
        self._write(pulse or self.level, now)

    def run(self, name):
        """Play a pattern and wait for it to finish (used right before a slow network call)."""
        self.play(name)
        while self.busy():
            watchdog_feed()
            time.sleep_ms(5)
            self.update(time.ticks_ms())


# ---------- button ----------
class Button:
    """The button, read through presslog: an interrupt records every edge, so a press
    during a slow call (NTP, DNS, a retry's TLS handshake) is never lost.
    events(now) returns [(time, pressed)] for each clean press or release since the
    last call, with the time it really happened. Without interrupts it reads the pin
    each loop, like before."""

    def __init__(self):
        self.pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.deb = presslog.Debouncer(DEBOUNCE_MS)
        self.log = None
        self.mode = "polling"
        try:
            log = presslog.EdgeLog(irq_off=machine.disable_irq, irq_on=machine.enable_irq)
            trigger = Pin.IRQ_FALLING | Pin.IRQ_RISING
            try:
                self.pin.irq(handler=log.irq, trigger=trigger, hard=True)
                self.mode = "interrupt"
            except (TypeError, ValueError, OSError):
                self.pin.irq(handler=log.irq, trigger=trigger)      # soft: times can be late
                self.mode = "soft interrupt"
            self.log = log
        except Exception as err:
            print("button interrupt off, reading the pin each loop:", err)

    def pressed_now(self):
        return self.pin.value() == 0

    def events(self, now):
        edges = self.log.take() if self.log is not None else []
        return self.deb.feed(edges, now, self.pressed_now())

    def touched(self):
        """True if the button is held, or moved since the last events() call. A retry
        stops as soon as this is True."""
        return (self.pressed_now() or self.deb.stable or self.deb.busy()
                or (self.log is not None and self.log.pending()))


# ---------- the Fob ----------
class Fob:
    def __init__(self):
        self.led = Led()
        self.motor = Motor()
        self.btn = Button()
        self.state = IDLE
        self.down = False                # the button, after debounce
        self.count = 0
        self.press_start = 0
        self.last_release = 0
        self.pending = None
        self.pending_start = 0
        self.press_can_cancel = False
        self.in_press = False
        self.lockout_until = 0
        # idle upkeep (WiFi rejoin, NTP, DNS), never during a send
        self.next_upkeep = 0
        self.next_join = 0
        self.join_until = None
        self.clock_ok = False
        self.next_ntp = 0
        self.next_dns = 0
        self.queue = retryq.RetryQueue(QUEUE_FILE, RETRY_MAX, RETRY_EVERY_MS, RETRY_FOR_MS)
        self.queue_dirty = False         # a save waiting for the help listener to finish
        self.boot_pending = None         # (payload, ctr, sig) of a BOOT report a press stopped
        self.reset_cause = None          # machine.reset_cause() at boot, sent in the BOOT report
        self.help = None
        if HELP_KEY is not None and HELP_LISTEN_MS > 0 and not sendpath.wifi_off(WIFI_SSID):
            self.help = helplisten.HelpListener(DEVICE_ID, HELP_KEY, HELP_LISTEN_MS)

    # --- start up ---
    def service(self, now):
        self.led.update(now)
        self.motor.update(now)
        gps_poll()

    def wait(self, ms):
        """Keep the LED, motor and GPS going for ms. Presses are recorded meanwhile."""
        end = time.ticks_add(time.ticks_ms(), ms)
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            self.service(time.ticks_ms())
            watchdog_feed()
            time.sleep_ms(LOOP_MS)

    def boot(self):
        try:
            self.reset_cause = machine.reset_cause()     # why the Fob started (selfcheck.py)
        except Exception:
            self.reset_cause = 0
        print("SafePing Fob", DEVICE_ID, "firmware", FW_VERSION)
        print("Reset cause:", self.reset_cause, selfcheck.reset_name(self.reset_cause))
        print("LoRa fallback on: CS", LORA_CS, "RST", LORA_RST)
        print("Button:", self.btn.mode)
        if SECRET_KEY.startswith("paste-the-key"):
            print("WARNING: SECRET_KEY is the placeholder. The server will reject every message.")
        gps_on = gps_start()
        gps_t0 = time.ticks_ms()
        print("GPS on" if gps_on else "GPS not started, alerts will have no location")
        print("Sensors:", sensors_start())
        if not LORA_ACK:
            print("LoRa acks: off")
        elif ACK_KEY is None:
            print("WARNING: ackcheck.py missing, LoRa alerts will never show as confirmed")
        else:
            print("LoRa acks: signed, waiting up to", ACK_WAIT_MS, "ms, up to", LORA_TRIES, "tries")
        self.led.show(BLUE, duration_ms=200)          # busy: starting up
        self.motor.run("tick")
        time.sleep_ms(250)
        if sendpath.wifi_off(WIFI_SSID):
            print("WiFi off (WIFI_SSID is none), every alert goes over LoRa")
            wifi = "off"
        else:
            wifi = "ok" if self.boot_wifi() else "fail"
        self.led.off()
        results = self.self_check(gps_on, gps_t0, wifi)
        print(selfcheck.summary_line(results, FW_VERSION, self.reset_cause))
        self.show_check(results)
        self.refresh_battery()
        self.resume_queue()
        self.send_boot_report(results)
        if watchdog_start():
            print("watchdog on:", WATCHDOG_MS, "ms")

    def boot_wifi(self):
        print("WiFi path: {}:{} TLS {}, budget {} ms (join {} ms, ack {} ms)".format(
            MQTT_HOST, MQTT_PORT, "on" if MQTT_TLS else "OFF", WIFI_BUDGET_MS, WIFI_JOIN_MS,
            MQTT_ACK_WAIT_MS))
        if MQTTClient is None:
            print("WARNING: umqtt_safe.py missing, every alert goes over LoRa")
        if MQTT_TLS and not ca_present():
            print("TLS CA file missing:", MQTT_CA_FILE)
        elif MQTT_TLS:
            try:
                tls_context()                    # read the CA file now, not during a send
            except Exception as err:
                print("TLS CA file could not be loaded:", sendpath.plain_error(err))
        self.led.show(BLUE, 300, 300)                 # busy: joining WiFi
        if wifi_join(sendpath.Budget(WIFI_BOOT_MS), self.service)[0]:
            print("WiFi connected")
            self.clock_ok = ntp_sync()
            if not self.clock_ok:
                self.next_ntp = time.ticks_add(time.ticks_ms(), NTP_RETRY_S * 1000)
            ok = dns_lookup() is not None
            wait_s = DNS_REFRESH_S if ok else WIFI_RETRY_S
            self.next_dns = time.ticks_add(time.ticks_ms(), wait_s * 1000)
            return True
        print("WiFi not connected yet, will retry in the background")
        wifi_quiet()
        self.next_join = time.ticks_add(time.ticks_ms(), WIFI_RETRY_S * 1000)
        return False

    # --- boot self-check (selfcheck.py) ---
    def self_check(self, gps_on, gps_t0, wifi):
        results = {"wifi": wifi}
        results["key"] = "ok" if selfcheck.key_ok(SECRET_KEY, SECRET_KEY_LEN) else "fail"
        try:
            with open(COUNTER_FILE) as f:
                text = f.read()
        except OSError:
            text = None
        results["counter"] = selfcheck.counter_state(text)
        try:
            radio = _lora_radio()                # begin() reads the version register
            results["lora"] = "ok" if radio.version() == sx127x.EXPECTED_VERSION else "fail"
        except Exception as err:
            print("self-check: LoRa radio not answering:", err)
            results["lora"] = "fail"
        if gps_on:
            while _gps.sentences == 0 and time.ticks_diff(time.ticks_ms(), gps_t0) < GPS_CHECK_MS:
                self.service(time.ticks_ms())
                time.sleep_ms(20)
            results["gps"] = "ok" if _gps.sentences > 0 else "fail"
        else:
            results["gps"] = "fail"
        results["battery"] = "ok" if read_battery() is not None else "fail"
        p = None
        if _bme is not None:
            try:
                p = _bme.read()[0]
            except Exception as err:
                print("self-check: pressure read error:", err)
        results["pressure"] = "ok" if p is not None else "fail"
        return results

    def show_check(self, results):
        """Green 1 s when every required check passed, steady red 3 s when one failed.
        No blink counting: the SELF_CHECK line and the dashboard say what failed."""
        if selfcheck.fail_mask(results) == 0:
            self.led.show(GREEN, duration_ms=CHECK_OK_MS)
            self.wait(CHECK_OK_MS)
        else:
            self.led.show(ORANGE, duration_ms=CHECK_FAIL_MS)   # a problem (red is MEDICAL only)
            self.wait(CHECK_FAIL_MS)
        self.led.off()

    def send_boot_report(self, results):
        """The signed BOOT message: WiFi first, then LoRa, same budget as alerts. Not
        queued if it fails. A button press stops it, and then the SAME signed message is
        sent later, once the press is handled (resend_boot)."""
        mask = selfcheck.fail_mask(results)
        try:
            ctr = next_counter()
        except Exception as err:
            print("BOOT report not sent: counter file problem:", err)
            return
        msg = selfcheck.boot_message(DEVICE_ID, ctr, unix_time(), read_battery(), mask,
                                     results.get("wifi") == "ok", FW_VERSION, self.reset_cause)
        msg["sig"] = sign(msg)
        payload = json.dumps(msg)
        print("SAFEPING_MSG " + payload)
        try:
            ok, outcome, reason = self.deliver("BOOT", payload, ctr, msg["sig"], stop=self.btn.touched)
        except PressStop:
            self.boot_pending = (payload, ctr, msg["sig"])
            print("BOOT_STOPPED ctr={} reason=button (sent after the press)".format(ctr))
            return
        print("BOOT report", "confirmed" if ok else "not confirmed")

    def resend_boot(self):
        """Idle only, after a press stopped the BOOT report: send the same signed message.
        While the Fob listens for help (the press was an alert confirmed over WiFi), it goes
        on that same connection, so listening never stops. Otherwise the normal WiFi-then-
        LoRa send. Not retried if it ends unconfirmed (like any BOOT report)."""
        if self.boot_pending is None or self.btn.touched() or self.motor.busy():
            return
        payload, ctr, sig = self.boot_pending
        print("BOOT_RESEND ctr={} reason=stopped_by_press".format(ctr))
        start = time.ticks_ms()
        if self.help is not None and self.help.active() and ACK_KEY is not None:
            expected = ackcheck.ack_text(ACK_KEY, DEVICE_ID, ctr, sig).encode()
            result = self.help.send_on_connection(ALERT_TOPIC, payload, ACK_TOPIC, expected,
                                                  MQTT_ACK_WAIT_MS, stop=self.btn.touched)
            if result == "confirmed":
                self.boot_pending = None
                print(sendpath.result_line(ctr, "BOOT", "wifi", "confirmed",
                                           time.ticks_diff(time.ticks_ms(), start), "-") + " resend=1")
                print("BOOT report sent later: confirmed")
                return
            if result == "stopped":
                print("BOOT_STOPPED ctr={} reason=button (sent after the press)".format(ctr))
                return
            print("BOOT report: the help connection did not carry it, sending it the normal way")
        try:
            ok, outcome, reason = self.deliver("BOOT", payload, ctr, sig, stop=self.btn.touched)
        except PressStop:
            print("BOOT_STOPPED ctr={} reason=button (sent after the press)".format(ctr))
            return
        self.boot_pending = None
        print("BOOT report sent later:", "confirmed" if ok else "not confirmed")

    def resume_queue(self):
        """Alerts still waiting from before the reboot, if they are inside RETRY_FOR_MS."""
        try:
            resumed, gave_up = self.queue.load(unix_time())
        except Exception as err:
            print("retry queue could not be read:", err)
            return
        for e in gave_up:
            print(retryq.line("RETRY_GAVE_UP", ctr=e["ctr"], kind=e["kind"], reason="too_old_after_reboot"))
        for e in resumed:
            print(retryq.line("RETRY_QUEUED", ctr=e["ctr"], kind=e["kind"], age_s=self.queue.age_ms(e) // 1000,
                              reason="resumed_after_reboot", queue=len(self.queue)))
        if resumed or gave_up:
            self.save_queue()

    def save_queue(self):
        """Write the queue to flash, but never while the help listener holds a WiFi
        connection: then it is saved as soon as listening ends (help_step). Only "done"
        and "tried" changes can wait like this. A new queued alert is saved at once,
        because a send that ends unconfirmed has already closed the listener."""
        if self.help is not None and self.help.active():
            self.queue_dirty = True
            return
        self.queue_dirty = False
        try:
            self.queue.save()
        except Exception as err:
            print("retry queue could not be saved:", err)

    def upkeep(self, now):
        """Idle-only WiFi upkeep, at most once a second: rejoin in the background, retry
        NTP, refresh the broker address. Never runs during a send or a cancel window.
        A join started here does not block: a press during it waits on it (inside the budget).
        NTP and DNS do block (up to about 2 s). Presses during them are still recorded by
        the button interrupt and handled right after."""
        if sendpath.wifi_off(WIFI_SSID) or time.ticks_diff(now, self.next_upkeep) < 0:
            return
        self.next_upkeep = time.ticks_add(now, 1000)
        if wifi_connected():
            self.join_until = None
            if not self.clock_ok and time.ticks_diff(now, self.next_ntp) >= 0:
                watchdog_feed()
                self.clock_ok = ntp_sync()
                self.next_ntp = time.ticks_add(time.ticks_ms(), NTP_RETRY_S * 1000)
            if time.ticks_diff(now, self.next_dns) >= 0 and not self.btn.touched():
                watchdog_feed()
                ok = dns_lookup() is not None              # a failure keeps the old address
                wait_s = DNS_REFRESH_S if ok else WIFI_RETRY_S
                self.next_dns = time.ticks_add(time.ticks_ms(), wait_s * 1000)
            return
        if self.join_until is not None:                     # a background join is running
            if not wifi_joining() or time.ticks_diff(now, self.join_until) >= 0:
                if not wifi_connected():
                    wifi_quiet()                            # stop it, so LoRa has a quiet radio
                self.join_until = None
                self.next_join = time.ticks_add(now, WIFI_RETRY_S * 1000)
            return
        if time.ticks_diff(now, self.next_join) >= 0:
            try:
                wifi_start_join()
                self.join_until = time.ticks_add(now, WIFI_BOOT_MS)
            except Exception as err:
                if sendpath.is_wifi_state_error(err):
                    print("WiFi state error in the background, resetting WiFi")
                    try:
                        wifi_reset()         # ready for the next try, not during a send
                    except Exception as err2:
                        print("WiFi reset failed:", err2)
                else:
                    print("WiFi join could not start:", sendpath.plain_error(err))
                self.next_join = time.ticks_add(time.ticks_ms(), WIFI_RETRY_S * 1000)

    def refresh_battery(self):
        bat = read_battery()
        self.led.scale = 40 if (bat is not None and bat < LOW_BATTERY_PCT) else 100

    # --- sending ---
    def show_sending(self, kind):
        """A dim, steady light while the send runs. SILENT stays dark."""
        if kind == "SILENT":
            return
        color = {"SUSPICIOUS": YELLOW, "MEDICAL": RED}.get(kind, WHITE)
        self.led.show(tuple(c * SENDING_DIM_PCT // 100 for c in color))

    def _stoppable(self, stop):
        """The service function for a stoppable send: raises PressStop on a press."""
        def service(now):
            self.service(now)
            if stop():
                raise PressStop()
        return service

    def deliver(self, kind, payload, ctr, sig, budget=None, stop=None, try_no=None):
        """Send one signed message: WiFi once inside WIFI_BUDGET_MS, then LoRa with the
        same message. Prints one SEND_RESULT line (with try=N for a retry).
        Returns (ok, outcome, reason). ok is True only if it was confirmed (or LoRa acks
        are off and it was sent). With stop given, raises PressStop when it returns True
        before the message is confirmed."""
        budget = budget or sendpath.Budget(WIFI_BUDGET_MS)
        self.motor.before_send()           # motor off while the radio transmits
        if self.help is not None:
            self.help.close("send")        # one MQTT connection at a time
        # Keep the connection for help if this is an alert staff acknowledge, or if an
        # earlier alert is still waiting for help (a STATUS tap must not end that).
        listen = self.help is not None and (kind in HELP_KINDS or bool(self.help.waiting))
        keep = [] if listen else None
        service = self.service if stop is None else self._stoppable(stop)
        extra = "" if try_no is None else " try={}".format(try_no)

        confirmed, reason, published, detail = wifi_send(payload, ctr, sig, budget, service,
                                                         keep_open=keep, stop=stop)
        if confirmed:
            print("sent", kind, "ctr", ctr, "over WiFi, confirmed by the server")
            print(sendpath.result_line(ctr, kind, "wifi", "confirmed", budget.used(), "-") + extra)
            if keep and kind in HELP_KINDS:
                self.help.listen(keep[0], ctr, kind)
            elif keep:
                self.help.attach(keep[0])          # STATUS or BOOT: keep listening for the others
            return True, "confirmed", "-"
        if stop is not None and stop():
            raise PressStop()

        if reason == "wifi_off":
            print("WiFi off, using LoRa")
        else:
            print("falling back to LoRa:", reason)
            print("WiFi problem:", sendpath.plain_reason(reason, detail))
            wifi_quiet(for_lora=True)      # WiFi radio off and settled before LoRa sends
        self.motor.before_send()
        result = lora_send_confirmed(payload, ctr, sig, stop)
        if result != "confirmed" and stop is not None and stop():
            raise PressStop()
        if result == "confirmed":
            print("sent over LoRa", kind, "ctr", ctr, "confirmed by the Relay")
        elif result == "sent":
            print("sent over LoRa", kind, "ctr", ctr)
        elif result == "unconfirmed":
            print("NOT CONFIRMED", kind, "ctr", ctr, "(no ack from the Relay)")
        else:
            print("NOT SENT", kind, "ctr", ctr)
        path, outcome, ok = sendpath.lora_outcome(result, published)
        print(sendpath.result_line(ctr, kind, path, outcome, budget.used(), reason) + extra)
        return ok, outcome, reason

    def send(self, kind):
        """Build, sign and send one alert. Returns True only if it was confirmed (or LoRa
        acks are off and it was sent). Not confirmed on both paths: it goes in the retry queue."""
        self.motor.before_send()           # motor off while the radio transmits
        self.show_sending(kind)
        budget = sendpath.Budget(WIFI_BUDGET_MS)   # starts at the press decision
        if self.help is not None:
            self.help.close("send")        # before the counter is written to flash
        msg = build_message(kind)
        ctr, sig = msg["ctr"], msg["sig"]
        if "lat" in msg:
            print("location sent, accuracy about", msg["acc"], "m")
        else:
            print("no GPS fix, sending without a location")
        payload = json.dumps(msg)
        print("SAFEPING_MSG " + payload)
        ok, outcome, reason = self.deliver(kind, payload, ctr, sig, budget)
        if outcome in ("not_confirmed", "failed"):
            self.queue_retry(kind, msg, payload, reason)
        return ok

    # --- retry queue (retryq.py) ---
    def queue_retry(self, kind, msg, payload, reason):
        ctr = msg["ctr"]
        queued, dropped = self.queue.add(ctr, kind, payload, msg["sig"], msg.get("ts"))
        if not queued:
            if dropped is not None:
                print(retryq.line("RETRY_GAVE_UP", ctr=ctr, kind=kind, reason="queue_full"))
            return
        if dropped is not None:
            if dropped["kind"] == "MEDICAL":
                print("retry queue full of MEDICAL alerts, dropping the oldest MEDICAL")
            print(retryq.line("RETRY_GAVE_UP", ctr=dropped["ctr"], kind=dropped["kind"], reason="queue_full"))
        print(retryq.line("RETRY_QUEUED", ctr=ctr, kind=kind, reason=reason, queue=len(self.queue),
                          dropped=None if dropped is None else dropped["ctr"]))
        self.save_queue()

    def run_retries(self):
        """Idle only. Gives up on old entries, then tries at most one that is due.
        A button press stops the try at once (PressStop) and the press is handled first."""
        if not len(self.queue):
            return
        now = time.ticks_ms()
        changed = False
        for e in self.queue.expired(now):
            print(retryq.line("RETRY_GAVE_UP", ctr=e["ctr"], kind=e["kind"], try_no=e["tries"],
                              reason="timeout"))
            changed = True
        entry = self.queue.next_due(now)
        if entry is None or self.btn.touched():
            if changed:
                self.save_queue()
            return
        n = entry["tries"] + 1
        print(retryq.line("RETRY_TRY", ctr=entry["ctr"], kind=entry["kind"], try_no=n,
                          age_s=self.queue.age_ms(entry, now) // 1000))
        try:
            ok, outcome, reason = self.deliver(entry["kind"], entry["payload"], entry["ctr"], entry["sig"],
                                               stop=self.btn.touched, try_no=n)
        except PressStop:
            print(retryq.line("RETRY_STOPPED", ctr=entry["ctr"], try_no=n, reason="button"))
            self.queue.stopped(entry)
            self.motor.stop()
            self.save_queue()
            return
        if ok:
            self.queue.done(entry)
            print(retryq.line("RETRY_DONE", ctr=entry["ctr"], kind=entry["kind"], try_no=n,
                              path="wifi" if reason == "-" else "lora", reason=reason))
            if entry["kind"] != "SILENT":             # SILENT: nothing at all
                self.show_result(entry["kind"], True)
        else:
            self.queue.tried(entry)
        self.save_queue()

    # --- help is coming (helplisten.py) ---
    def help_step(self, now):
        if self.help is None:
            return
        self.help.step(now, can_send=not self.motor.busy())
        if self.queue_dirty and not self.help.active():
            self.save_queue()                   # the save that waited for listening to end
        if self.help.received and self.state in (IDLE, LOCKOUT) and not self.motor.busy():
            ctr, kind, ms = self.help.received.pop(0)
            if helplisten.feedback(kind) == "help":
                self.led.show(GREEN, 400, 400, 2000)
                self.motor.play("help")
            else:
                print("help for SILENT ctr", ctr, "received: no buzz, no light")

    # --- results ---
    def show_result(self, kind, ok):
        """The light and buzz for a finished send. Confirmed is green (good news) for every
        type, not confirmed is orange (a problem). SILENT has no light."""
        self.motor.hold = False
        self.motor.stop()
        if kind == "SILENT":
            self.motor.play("ok" if ok else "fail", RESULT_GAP_MS)     # no light, ever
        elif kind == "STATUS":
            if ok:
                self.led.show(GREEN, 150, 150, 300)
                gap = RESULT_GAP_MS if STATUS_SUCCESS_PATTERN == "ok" else 0
                self.motor.play(STATUS_SUCCESS_PATTERN, gap)   # "ok" = two pulses, like the rest
            else:
                self.led.show(ORANGE, duration_ms=CONFIRM_MS)
                self.motor.play("fail", RESULT_GAP_MS)
        elif ok:
            self.led.show(GREEN, duration_ms=CONFIRM_MS)    # solid green = confirmed
            self.motor.play("ok", RESULT_GAP_MS)
        else:
            self.led.show(ORANGE, duration_ms=CONFIRM_MS)   # orange = connection problem
            self.motor.play("fail", RESULT_GAP_MS)
        self.refresh_battery()

    def finish(self, kind, ok):
        """Show the result, then ignore presses for a short while."""
        self.show_result(kind, ok)
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
            self.motor.start_hold()
        else:
            self.led.show(YELLOW, 500, 500)
            self.motor.play("one")

    def send_pending(self):
        kind = self.pending
        self.finish(kind, self.send(kind))     # send() shows the dim "sending" light

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
        """Presses and releases come with the time they happened (presslog). Each one is
        handled in order, after the timers are checked at that moment, so a double tap
        recorded during a slow call still counts as a double tap."""
        for t, down in self.btn.events(now):
            self.timers(t)
            self.on_button(t, down)
        self.service(now)
        self.timers(now)
        self.help_step(now)
        if self.state == IDLE and not self.down and not self.btn.touched():
            self.upkeep(now)
            if not self.btn.touched():
                if self.boot_pending is not None:
                    self.resend_boot()           # a BOOT report a press stopped
                else:
                    self.run_retries()

    def on_button(self, t, down):
        self.down = down
        if self.state == IDLE:
            if down:
                self.press_down(t)
        elif self.state == DOWN:
            if not down:
                self.count += 1
                self.last_release = t
                if self.count >= 3:
                    self.start_pending("MEDICAL", t)
                else:
                    self.state = COUNT
        elif self.state == COUNT:
            if down:
                self.press_down(t)
        elif self.state == PENDING:
            self.pending_button(t, down)
        # LOCKOUT: presses are ignored

    def timers(self, t):
        if self.state == DOWN:
            if self.down and time.ticks_diff(t, self.press_start) >= HOLD_MS:
                self.fire_now("SILENT")
        elif self.state == COUNT:
            if time.ticks_diff(t, self.last_release) >= MULTI_WINDOW_MS:
                taps = self.count
                self.count = 0
                if taps == 1:
                    self.fire_now("STATUS")
                else:
                    self.start_pending("SUSPICIOUS", t)
        elif self.state == PENDING:
            self.pending_timers(t)
        elif self.state == LOCKOUT:
            if not self.down and time.ticks_diff(t, self.lockout_until) >= 0:
                self.state = IDLE

    def press_down(self, t):
        self.state = DOWN
        self.press_start = t
        self.motor.play("tick")

    def pending_button(self, t, down):
        age = time.ticks_diff(t, self.pending_start)
        if down:
            self.press_start = t
            self.in_press = True
            # extra presses right after the 3rd MEDICAL press are part of the pattern
            self.press_can_cancel = age >= (MULTI_WINDOW_MS if self.pending == "MEDICAL" else 0)
            return
        if self.in_press:
            self.in_press = False
            if self.press_can_cancel:
                self.cancel_pending()

    def pending_timers(self, t):
        if self.down and self.in_press:
            if time.ticks_diff(t, self.press_start) >= HOLD_MS:
                self.in_press = False
                self.pending = None
                self.motor.stop()
                self.fire_now("SILENT")     # situation got worse, go straight to SILENT
            return
        if not self.down and time.ticks_diff(t, self.pending_start) >= CANCEL_MS:
            self.send_pending()


def main():
    fob = Fob()
    fob.boot()
    while True:
        fob.step(time.ticks_ms())
        watchdog_feed()
        time.sleep_ms(LOOP_MS)


if __name__ == "__main__":
    main()
