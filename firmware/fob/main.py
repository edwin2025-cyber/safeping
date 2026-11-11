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
from machine import Pin, PWM

import sendpath                      # the send rules (sendpath.py must be on the board)

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
WIFI_RETRY_S = _cfg("WIFI_RETRY_S", 30)           # rejoin in the background this often while idle
NTP_RETRY_S = _cfg("NTP_RETRY_S", 1800)           # retry NTP this often until it works
DNS_REFRESH_S = _cfg("DNS_REFRESH_S", 3600)       # look the broker up again this often while idle
WATCHDOG_ENABLED = _cfg("WATCHDOG_ENABLED", False)   # see watchdog_start() before turning on
WATCHDOG_MS = _cfg("WATCHDOG_MS", 30000)
SECRET_KEY = _cfg("SECRET_KEY", "paste-the-key-from-add_device.py")
COUNTER_FILE = _cfg("COUNTER_FILE", "counter.txt")

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
LOOP_MS = 10

# Colors (red, green, blue 0-255)
WHITE = (255, 255, 255)
YELLOW = (255, 180, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
ORANGE = (255, 90, 0)
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
}
if STATUS_SUCCESS_PATTERN not in PATTERNS:
    STATUS_SUCCESS_PATTERN = "ok"

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
_gps = None


def gps_start():
    """Start the GPS wing. Returns True if it started. The Fob works without it."""
    global _gps
    try:
        import gps as gps_module
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
        from machine import I2C
        i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=400000)
    except Exception as err:
        return "I2C off: {}".format(err)
    parts = []
    try:
        import bme280
        _bme = bme280.BME280(i2c, BME280_ADDR)
        parts.append("pressure on")
    except Exception as err:            # no bme280.py, not plugged in, or wrong address
        _bme = None
        parts.append("pressure off ({})".format(err))
    try:
        import max17048
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
        from machine import SPI
        import sx127x
        spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
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


def _wait_for_ack(expected, wait_ms):
    """Listen up to wait_ms for the exact signed ack. Other packets (another Fob's
    alert, noise) are ignored and listening continues until the time is up.
    An ack for this Fob with a wrong signature is reported and ignored."""
    deadline = time.ticks_add(time.ticks_ms(), wait_ms)
    while True:
        watchdog_feed()
        left = time.ticks_diff(deadline, time.ticks_ms())
        if left <= 0:
            return False
        try:
            packet = _lora_radio().receive(timeout_ms=left)
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


def lora_send_confirmed(payload, ctr, sig):
    """Send over LoRa and wait for the Relay to confirm it stored the alert.

    The Relay stores the alert in its flash, then answers with a signed ack
    "ACK <id> <ctr> <mac>" (see ackcheck.py). If no valid ack comes back, the SAME
    message (same ctr, same signature) is sent again, up to LORA_TRIES times.
    Returns:
      "confirmed"    the Relay stored it and sent a valid signed ack
      "unconfirmed"  it left the antenna but no ack came back (the Relay may still have it)
      "failed"       the radio could not send at all
      "sent"         acks are switched off (LORA_ACK = False) and it left the antenna
    Note: the ack proves the Relay stored it, not yet that the server saved it."""
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
        if not lora_send(payload):       # radio problem (it already retried inside)
            return "unconfirmed" if sent_once else "failed"
        sent_once = True
        if _wait_for_ack(expected, ACK_WAIT_MS):
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
        from machine import WDT
        _wdt = WDT(timeout=WATCHDOG_MS)
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
    connect() on top of it is what printed "sta is connecting, cannot set config"."""
    sta = _sta()
    if sta.isconnected() or wifi_joining():
        return True
    try:
        sta.connect(WIFI_SSID, WIFI_PASSWORD)
        return True
    except OSError as err:
        print("WiFi join could not start:", err)
        return False


def wifi_join(wait_ms, service=None):
    """Be connected within wait_ms. Waits on a join already in progress instead of starting
    a second one. Stops early if the driver says the name or password is wrong."""
    if not wifi_start_join():
        return False
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
        import ntptime
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


def ca_present():
    try:
        os.stat(MQTT_CA_FILE)
        return True
    except OSError:
        return False


def tls_context():
    """TLS settings, made once. Certificate checks are always on.
    Loads the CA as given (PEM or DER). If the board refuses PEM, it is turned into DER."""
    global _tls_ctx
    if _tls_ctx is None:
        import ssl
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


def wifi_send(payload, ctr, sig, budget, service=None):
    """One WiFi/MQTT attempt inside the budget. Never retries.
    Returns (confirmed, reason, published, detail).
    published = the broker took it (PUBACK). detail = the error behind a failure, or None."""
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

    def on_message(topic, msg):
        if topic == ack_topic and msg.strip() == expected:
            got.append(True)
        else:
            print("WiFi ack ignored: not for this alert")

    if not wifi_join(budget.left(WIFI_JOIN_MS), service):
        return False, "wifi_join_failed", False, None
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
    confirmed, reason, published, detail, step = sendpath.mqtt_attempt(
        client, addr, budget, ctx, MQTT_HOST, ACK_TOPIC, ALERT_TOPIC, payload,
        MQTT_ACK_WAIT_MS, got, step_parts)
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
        # idle upkeep (WiFi rejoin, NTP, DNS), never during a send
        self.next_upkeep = 0
        self.next_join = 0
        self.join_until = None
        self.clock_ok = False
        self.next_ntp = 0
        self.next_dns = 0

    # --- start up ---
    def service(self, now):
        self.led.update(now)
        self.motor.update(now)
        gps_poll()

    def boot(self):
        print("SafePing Fob", DEVICE_ID)
        print("LoRa fallback on: CS", LORA_CS, "RST", LORA_RST)
        if SECRET_KEY.startswith("paste-the-key"):
            print("WARNING: SECRET_KEY is the placeholder. The server will reject every message.")
        print("GPS on" if gps_start() else "GPS not started, alerts will have no location")
        print("Sensors:", sensors_start())
        if not LORA_ACK:
            print("LoRa acks: off")
        elif ACK_KEY is None:
            print("WARNING: ackcheck.py missing, LoRa alerts will never show as confirmed")
        else:
            print("LoRa acks: signed, waiting up to", ACK_WAIT_MS, "ms, up to", LORA_TRIES, "tries")
        self.led.show(WHITE, duration_ms=200)
        self.motor.run("tick")
        time.sleep_ms(250)
        if sendpath.wifi_off(WIFI_SSID):
            print("WiFi off (WIFI_SSID is none), every alert goes over LoRa")
        else:
            self.boot_wifi()
        self.led.off()
        self.refresh_battery()
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
        self.led.show(ORANGE, 300, 300)
        if wifi_join(WIFI_BOOT_MS, self.service):
            print("WiFi connected")
            self.clock_ok = ntp_sync()
            if not self.clock_ok:
                self.next_ntp = time.ticks_add(time.ticks_ms(), NTP_RETRY_S * 1000)
            ok = dns_lookup() is not None
            wait_s = DNS_REFRESH_S if ok else WIFI_RETRY_S
            self.next_dns = time.ticks_add(time.ticks_ms(), wait_s * 1000)
        else:
            print("WiFi not connected yet, will retry in the background")
            wifi_quiet()
            self.next_join = time.ticks_add(time.ticks_ms(), WIFI_RETRY_S * 1000)

    def upkeep(self, now):
        """Idle-only WiFi upkeep, at most once a second: rejoin in the background, retry
        NTP, refresh the broker address. Never runs during a send or a cancel window.
        A join started here does not block: a press during it waits on it (inside the budget)."""
        if sendpath.wifi_off(WIFI_SSID) or time.ticks_diff(now, self.next_upkeep) < 0:
            return
        self.next_upkeep = time.ticks_add(now, 1000)
        if wifi_connected():
            self.join_until = None
            if not self.clock_ok and time.ticks_diff(now, self.next_ntp) >= 0:
                watchdog_feed()
                self.clock_ok = ntp_sync()
                self.next_ntp = time.ticks_add(time.ticks_ms(), NTP_RETRY_S * 1000)
            if time.ticks_diff(now, self.next_dns) >= 0:
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
            if wifi_start_join():
                self.join_until = time.ticks_add(now, WIFI_BOOT_MS)
            else:
                self.next_join = time.ticks_add(now, WIFI_RETRY_S * 1000)

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

    def send(self, kind):
        """Build, sign and send one message: WiFi once inside WIFI_BUDGET_MS, then LoRa
        with the same message. Returns True only if it was confirmed (or LoRa acks are off
        and it was sent). Always prints one SEND_RESULT line."""
        self.motor.before_send()           # motor off while the radio transmits
        self.show_sending(kind)
        budget = sendpath.Budget(WIFI_BUDGET_MS)   # starts at the press decision
        msg = build_message(kind)
        ctr, sig = msg["ctr"], msg["sig"]
        if "lat" in msg:
            print("location sent, accuracy about", msg["acc"], "m")
        else:
            print("no GPS fix, sending without a location")
        payload = json.dumps(msg)
        print("SAFEPING_MSG " + payload)

        confirmed, reason, published, detail = wifi_send(payload, ctr, sig, budget, self.service)
        if confirmed:
            print("sent", kind, "ctr", ctr, "over WiFi, confirmed by the server")
            print(sendpath.result_line(ctr, kind, "wifi", "confirmed", budget.used(), "-"))
            return True

        if reason == "wifi_off":
            print("WiFi off, using LoRa")
        else:
            print("falling back to LoRa:", reason)
            print("WiFi problem:", sendpath.plain_reason(reason, detail))
            wifi_quiet(for_lora=True)      # WiFi radio off and settled before LoRa sends
        self.motor.before_send()
        result = lora_send_confirmed(payload, ctr, sig)
        if result == "confirmed":
            print("sent over LoRa", kind, "ctr", ctr, "confirmed by the Relay")
        elif result == "sent":
            print("sent over LoRa", kind, "ctr", ctr)
        elif result == "unconfirmed":
            print("NOT CONFIRMED", kind, "ctr", ctr, "(no ack from the Relay)")
        else:
            print("NOT SENT", kind, "ctr", ctr)
        path, outcome, ok = sendpath.lora_outcome(result, published)
        print(sendpath.result_line(ctr, kind, path, outcome, budget.used(), reason))
        return ok

    def finish(self, kind, ok):
        """Show the result, then ignore presses for a short while."""
        self.motor.hold = False
        self.motor.stop()
        color = {"SUSPICIOUS": YELLOW, "MEDICAL": RED}.get(kind, WHITE)
        if kind == "SILENT":
            self.motor.play("ok" if ok else "fail", RESULT_GAP_MS)     # no light, ever
        elif kind == "STATUS":
            if ok:
                self.led.show(WHITE, 150, 150, 300)
                gap = RESULT_GAP_MS if STATUS_SUCCESS_PATTERN == "ok" else 0
                self.motor.play(STATUS_SUCCESS_PATTERN, gap)   # "ok" = two pulses, like the rest
            else:
                self.led.show(ORANGE, duration_ms=CONFIRM_MS)
                self.motor.play("fail", RESULT_GAP_MS)
        elif ok:
            self.led.show(color, duration_ms=CONFIRM_MS)    # solid = confirmed
            self.motor.play("ok", RESULT_GAP_MS)
        else:
            self.led.show(ORANGE, duration_ms=CONFIRM_MS)   # orange = connection problem
            self.motor.play("fail", RESULT_GAP_MS)
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
        before = self.btn.state
        down = self.btn.update(now)
        pressed = down and not before
        released = before and not down
        self.service(now)

        if self.state == IDLE:
            if pressed:
                self.press_down(now)
            elif not down:
                self.upkeep(now)

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
        watchdog_feed()
        time.sleep_ms(LOOP_MS)


if __name__ == "__main__":
    main()