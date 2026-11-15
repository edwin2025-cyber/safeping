"""SafePing Reference board firmware (MicroPython 1.27, SparkFun Thing Plus ESP32-C5).

The Reference board sits on academic building floor 1, on USB wall power and school
WiFi. Weather moves the air pressure by more than a floor in a few hours, so the server
compares each Fob's pressure with this board's (message-format.md, "Reference readings").

What it does
  Reads the pressure sensor (BME280 on Qwiic) every SAMPLE_MS (2 s). Every PUBLISH_MS
  (30 s) it publishes one signed REF message to safeping/ref/<id> at QoS 0: average
  pressure to one decimal (pd, tenths of a pascal), whole pascals (p), average
  temperature (t), readings in the average (n) and the firmware version (fw). ts is the
  middle of the 30 s window.

Runs unattended for days
  WiFi or the broker drops: it reconnects by itself, waiting a little longer after each
  failure (RECONNECT_MIN_S up to RECONNECT_MAX_S). The watchdog (on by default) resets
  the board if the program freezes. The clock is set by NTP at boot and every NTP_EVERY_S.

Light
  blue blink       WiFi not connected (joining, or waiting to try again)
  short green      each reading published
  steady orange    the sensor is not reading, or the broker is not connected
  off              all good, between readings

Counter
  Crash-safe, the Fob's method (counterfile.py: counter.txt written through
  counter.txt.tmp). Saved in blocks: counter.txt holds the highest counter the board may
  use, so a write happens every COUNTER_BLOCK readings (10 minutes) instead of every 30 s.
  After a restart it starts above that number, so a counter is never used twice.

Log lines
  SELF_CHECK key=.. counter=.. pressure=.. wifi=.. reset=.. fw=..
  REF_SENT ctr=.. p=98812.4 t=21.50 n=15 ts=..
  REF_SKIP reason=..        a window not published (no readings, broker down)
  REF_SEND_FAIL reason=..   the publish failed, reconnecting

Shared with the Fob (firmware/lib, copied to the board's top level /): msgsign.py,
ackcheck.py, sendpath.py, selfcheck.py, counterfile.py, umqtt_safe.py, bme280.py, baro.py.
Settings come from config.py (see config.example.py).
"""
import json
import network
import os
import socket
import time
import machine
from machine import Pin

# Every import is at the top (an import inside a function reads flash each time it runs,
# see docs/features-changes.md section 8). tests/test_imports.py checks this folder too.
import sendpath                      # Budget, tls_context, plain_error, is_wifi_state_error
import selfcheck                     # key_ok, reset_name, summary_line
import counterfile                   # counter.txt through a .tmp file
import msgsign                       # the signing string, shared with the Fob
import baro                          # the 30 s average to one decimal

try:
    from umqtt_safe import MQTTClient
except ImportError:
    MQTTClient = None
try:
    import config
except ImportError:
    config = None
try:
    import bme280
except ImportError as _err:
    bme280, BME_IMPORT_ERROR = None, _err
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

FW_VERSION = "ref-2026.11.15a"       # sent in every REF message. Change it when this file changes.


def _cfg(name, default):
    return getattr(config, name, default) if config else default


# ---------- settings ----------
DEVICE_ID = _cfg("DEVICE_ID", "REF-001")
SECRET_KEY = _cfg("SECRET_KEY", "paste-the-key-from-add_device.py")
SECRET_KEY_LEN = _cfg("SECRET_KEY_LEN", 32)
WIFI_SSID = _cfg("WIFI_SSID", "your-wifi-name")
WIFI_PASSWORD = _cfg("WIFI_PASSWORD", "")
MQTT_HOST = _cfg("MQTT_HOST", "your-deployment-address")
MQTT_PORT = _cfg("MQTT_PORT", 8883)
MQTT_USER = _cfg("MQTT_USER", "safeping-ref")
MQTT_PASSWORD = _cfg("MQTT_PASSWORD", None)
MQTT_TLS = _cfg("MQTT_TLS", True)
MQTT_CA_FILE = _cfg("MQTT_CA_FILE", "/certs/broker-ca.pem")
MQTT_KEEPALIVE_S = _cfg("MQTT_KEEPALIVE_S", 120)
REF_TOPIC = "safeping/ref/" + DEVICE_ID

SAMPLE_MS = _cfg("SAMPLE_MS", 2000)            # one sensor reading this often
PUBLISH_MS = _cfg("PUBLISH_MS", 30000)         # one REF message this often
CONNECT_MS = _cfg("CONNECT_MS", 15000)         # TCP + TLS + MQTT login, at most
PUBLISH_IO_MS = _cfg("PUBLISH_IO_MS", 5000)    # one publish write, at most
PING_EVERY_S = _cfg("PING_EVERY_S", 60)        # check the broker connection this often
PING_WAIT_MS = _cfg("PING_WAIT_MS", 3000)      # wait this long for the broker's answer
WIFI_JOIN_MS = _cfg("WIFI_JOIN_MS", 15000)     # one join, then wait and try again
WIFI_RESET_MS = _cfg("WIFI_RESET_MS", 200)
RECONNECT_MIN_S = _cfg("RECONNECT_MIN_S", 5)   # first wait after a failure
RECONNECT_MAX_S = _cfg("RECONNECT_MAX_S", 120) # the wait doubles up to this
NTP_EVERY_S = _cfg("NTP_EVERY_S", 21600)       # set the clock again every 6 hours
NTP_RETRY_S = _cfg("NTP_RETRY_S", 300)         # until it works
WATCHDOG_ENABLED = _cfg("WATCHDOG_ENABLED", True)   # unattended for days: on by default
WATCHDOG_MS = _cfg("WATCHDOG_MS", 60000)
COUNTER_FILE = _cfg("COUNTER_FILE", "counter.txt")
COUNTER_BLOCK = _cfg("COUNTER_BLOCK", 20)      # counters saved per flash write (20 x 30 s = 10 min)
SENSOR_RETRY_S = _cfg("SENSOR_RETRY_S", 30)    # start the sensor again this often while it fails

I2C_SDA = _cfg("I2C_SDA", 23)
I2C_SCL = _cfg("I2C_SCL", 24)
BME280_ADDR = _cfg("BME280_ADDR", None)        # None: try 0x77 (SparkFun default), then 0x76
NEOPIXEL_PIN = _cfg("NEOPIXEL_PIN", 27)
LOOP_MS = 50

CHECKS = ("key", "counter", "pressure")        # the SELF_CHECK line (wifi is added after)

BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
ORANGE = (255, 45, 0)                          # same orange as the Fob
OFF = (0, 0, 0)
GREEN_FLASH_MS = 150

UNIX_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0


def unix_time():
    """Unix seconds, or None while the clock has obviously not been set."""
    now = int(time.time()) + UNIX_OFFSET
    return now if now > 1700000000 else None


# ---------- counter ----------
class BlockCounter:
    """The counter, saved in blocks through counterfile.CounterFile (tmp file, then rename).
    The file holds the highest counter the board may use. take() writes a new block
    BEFORE it hands out the first number of that block, so a crash never reuses one."""

    def __init__(self, path, block, files=None):
        self.file = counterfile.CounterFile(path, files)
        self.block = max(1, block)
        self.next = 0
        self.ceiling = -1
        self.state = "new"

    def start(self, clock_now=None):
        """Read the file. A damaged file restarts from the clock (when set), which is
        above any counter this board has used. Returns the state: ok, new or damaged."""
        value, state = self.file.read()
        self.state = state
        if value is None:
            value = -1 if state == "new" else counterfile.jump_base(None, [clock_now])
            if state != "new":
                print("counter file damaged, restarting from", value)
        self.ceiling = value
        self.next = value + 1
        return state

    def take(self):
        if self.next > self.ceiling:
            ceiling = self.next + self.block - 1
            self.file.write(ceiling)
            self.ceiling = ceiling
        n = self.next
        self.next += 1
        return n


# ---------- LED ----------
class Led:
    def __init__(self):
        self.pixel = None
        self.shown = None
        if neopixel is not None:
            try:
                self.pixel = neopixel.NeoPixel(Pin(NEOPIXEL_PIN), 1)
            except Exception as err:
                print("LED off:", err)
        self.set(OFF)

    def set(self, rgb):
        if self.pixel is None or rgb == self.shown:
            return
        self.shown = rgb
        self.pixel[0] = rgb
        self.pixel.write()


def micropython_version():
    """Like 1.29.0, so the log shows which MicroPython the board runs."""
    try:
        return os.uname().release
    except Exception:
        return "unknown"


def make_i2c():
    return machine.I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=400000)


# ---------- the board ----------
class RefBoard:
    def __init__(self):
        self.led = Led()
        self.counter = BlockCounter(COUNTER_FILE, COUNTER_BLOCK)
        self.window = baro.Window()
        self.wlan = None
        self.bme = None
        self.client = None
        self.tls = None
        self.wdt = None
        self.reset_cause = 0
        self.sensor_fault = False
        self.broker_fault = False
        self.joining = False
        self.join_until = 0
        self.next_join = 0
        self.next_connect = 0
        self.wait_s = RECONNECT_MIN_S
        self.next_sample = 0
        self.next_publish = 0
        self.next_ping = 0
        self.next_ntp = 0
        self.next_sensor = 0
        self.green_until = None
        self.sent = 0
        self.clock_ok = False
        self.sensor_name = "none"          # "BME280@0x77", sent in the BOOT report
        self.i2c_found = None
        self.boot_msg = None               # the BOOT report, until it is published

    # --- start up ---
    def boot(self):
        try:
            self.reset_cause = machine.reset_cause()
        except Exception:
            self.reset_cause = 0
        print("SafePing Reference", DEVICE_ID, "firmware", FW_VERSION)
        print("MicroPython", micropython_version())
        print("Reset cause:", self.reset_cause, selfcheck.reset_name(self.reset_cause))
        if SECRET_KEY.startswith("paste-the-key"):
            print("WARNING: SECRET_KEY is the placeholder. The server will reject every reading.")
        print("Sensor:", self.sensor_start())
        wifi = self.boot_wifi()
        if MQTT_TLS:
            try:
                self.tls = sendpath.tls_context(ssl, MQTT_CA_FILE, print)   # read the CA now, not later
            except Exception as err:
                print("TLS CA file could not be loaded ({}): {}".format(MQTT_CA_FILE, sendpath.plain_error(err)))
        state = self.counter.start(unix_time())
        results = {
            "key": "ok" if selfcheck.key_ok(SECRET_KEY, SECRET_KEY_LEN) else "fail",
            "counter": "fail" if state == "damaged" else state,
            "pressure": "ok" if self.read_once() else "fail",
            "wifi": "ok" if wifi else "fail",
        }
        print(selfcheck.summary_line(results, FW_VERSION, self.reset_cause, checks=CHECKS)
              + " sensor=" + self.sensor_name)
        print("Publishing to {} every {} s, a reading every {} s".format(REF_TOPIC, PUBLISH_MS // 1000, SAMPLE_MS // 1000))
        self.boot_msg = self.build_boot(results)
        self.watchdog_start()
        now = time.ticks_ms()
        self.next_sample = now
        self.next_publish = time.ticks_add(now, PUBLISH_MS)
        if wifi:
            self.connect_broker()

    def build_boot(self, results):
        """The signed BOOT report (message-format.md, "Boot report"): the failed checks
        (key 1, counter 2, pressure 32), WiFi, firmware, reset cause and the sensor.
        Published once the broker is connected. None if no counter could be taken."""
        mask = 0
        for name, bit in (("key", 1), ("counter", 2), ("pressure", 32)):
            if results.get(name) == "fail":
                mask |= bit
        try:
            ctr = self.counter.take()
        except Exception as err:
            print("BOOT report not made: counter problem:", err)
            return None
        msg = selfcheck.boot_message(DEVICE_ID, ctr, unix_time(), None, mask,
                                     results.get("wifi") == "ok", FW_VERSION, self.reset_cause)
        msg["sensor"] = self.sensor_name
        msg["sig"] = msgsign.sign(SECRET_KEY, msg)
        return msg

    def send_boot(self):
        """Publish the BOOT report once (QoS 0, like the readings). A failure is not retried:
        the readings still show the board is alive."""
        if self.boot_msg is None or self.client is None:
            return
        msg, self.boot_msg = self.boot_msg, None
        self.feed()
        try:
            self.client.left_ms = lambda: PUBLISH_IO_MS
            self.client.publish(REF_TOPIC, json.dumps(msg), qos=0)
            print("BOOT_SENT ctr={} fail={} sensor={}".format(msg["ctr"], msg["fail"], msg["sensor"]))
        except Exception as err:
            print("REF_SEND_FAIL reason=boot ({})".format(sendpath.plain_error(err)))
            self.broker_failed("publish failed")

    def sensor_start(self):
        """Start the BME280. Returns a short status line. A start that works does not
        clear the orange light: only a window with readings does (publish)."""
        self.bme = None
        if bme280 is None:
            self.sensor_fault = True
            return "off (bme280.py missing: {})".format(BME_IMPORT_ERROR)
        try:
            i2c = make_i2c()
        except Exception as err:
            self.sensor_fault = True
            return "off (I2C: {})".format(err)
        try:
            found = i2c.scan()                    # which addresses answer on the bus
        except Exception as err:
            found = None
            print("I2C scan failed:", err)
        self.i2c_found = found
        candidates = (BME280_ADDR,) if BME280_ADDR else (0x77, 0x76)
        if found is not None:
            # Only addresses that answered. With MicroPython 1.29's new I2C driver, a read
            # from an address that is not there can be slow, so do not try those.
            present = [a for a in candidates if a in found]
            candidates = present or candidates
        last = None
        for addr in candidates:
            try:
                self.bme = bme280.BME280(i2c, addr)
                name = "BME280" if self.bme.chip_id == 0x60 else "BMP280"
                self.sensor_name = "{}@0x{:02x}".format(name, addr)
                print("SENSOR model={} chip_id=0x{:02x} address=0x{:02x} i2c={}".format(
                    name, self.bme.chip_id, addr, self.i2c_text()))
                return "{} (chip id 0x{:02x}) at 0x{:02x}".format(name, self.bme.chip_id, addr)
            except Exception as err:
                last = err
        self.sensor_fault = True
        self.sensor_name = "none"
        print("SENSOR model=none address=- i2c={} ({})".format(self.i2c_text(), last))
        return "off ({})".format(last)

    def i2c_text(self):
        """The addresses that answered, like 0x36,0x77, or - when the scan failed."""
        if self.i2c_found is None:
            return "-"
        return ",".join("0x{:02x}".format(a) for a in self.i2c_found) or "nothing"

    def read_once(self):
        if self.bme is None:
            return False
        try:
            return self.bme.read_q8()[0] is not None
        except Exception as err:
            print("pressure read error:", err)
            return False

    def boot_wifi(self):
        self.wifi_start_join()
        deadline = time.ticks_add(time.ticks_ms(), WIFI_JOIN_MS)
        while not self.wifi_connected() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            self.led_update(time.ticks_ms())
            time.sleep_ms(LOOP_MS)
        self.joining = False
        if not self.wifi_connected():
            print("WiFi not connected yet, will keep trying")
            self.wifi_stop()
            self.next_join = time.ticks_add(time.ticks_ms(), RECONNECT_MIN_S * 1000)
            return False
        print("WiFi connected")
        self.ntp()
        return True

    def watchdog_start(self):
        """Resets the board if the loop stops for WATCHDOG_MS. It cannot be stopped once on:
        after Ctrl+C in Thonny the board resets WATCHDOG_MS later. Set WATCHDOG_ENABLED =
        False in config.py while copying files."""
        if not WATCHDOG_ENABLED:
            print("watchdog off")
            return
        try:
            self.wdt = machine.WDT(timeout=WATCHDOG_MS)
            print("watchdog on:", WATCHDOG_MS, "ms")
        except Exception as err:
            print("watchdog not started:", err)

    def feed(self):
        if self.wdt is not None:
            self.wdt.feed()

    # --- WiFi ---
    def sta(self):
        if self.wlan is None:
            self.wlan = network.WLAN(network.STA_IF)
        if not self.wlan.active():
            self.wlan.active(True)
        return self.wlan

    def wifi_connected(self):
        try:
            return self.wlan is not None and self.wlan.active() and self.wlan.isconnected()
        except Exception:
            return False

    def wifi_start_join(self):
        """Start a join without waiting. A driver state error gets a WiFi reset first."""
        self.joining = True
        self.join_until = time.ticks_add(time.ticks_ms(), WIFI_JOIN_MS)
        try:
            self.sta().connect(WIFI_SSID, WIFI_PASSWORD)
        except Exception as err:
            if sendpath.is_wifi_state_error(err):
                print("WiFi state error, resetting WiFi")
                self.wifi_stop()
                time.sleep_ms(WIFI_RESET_MS)
                try:
                    self.sta().connect(WIFI_SSID, WIFI_PASSWORD)
                    return
                except Exception as err2:
                    err = err2
            print("WiFi join could not start:", sendpath.plain_error(err))
            self.joining = False

    def wifi_stop(self):
        if self.wlan is None:
            return
        try:
            self.wlan.disconnect()
        except Exception:
            pass
        try:
            self.wlan.active(False)
        except Exception:
            pass

    def ntp(self):
        if ntptime is None:
            print("no NTP (ntptime module missing)")
            self.next_ntp = time.ticks_add(time.ticks_ms(), NTP_EVERY_S * 1000)
            return
        self.feed()
        try:
            ntptime.settime()
            self.clock_ok = True
            print("clock set by NTP, year", time.gmtime()[0])
            self.next_ntp = time.ticks_add(time.ticks_ms(), NTP_EVERY_S * 1000)
        except Exception as err:
            print("no NTP ({}), will retry".format(err))
            self.next_ntp = time.ticks_add(time.ticks_ms(), NTP_RETRY_S * 1000)

    # --- broker ---
    def connect_broker(self):
        """TCP, TLS, MQTT login, inside CONNECT_MS. On a failure: orange, and try again later."""
        self.feed()
        if MQTTClient is None:
            return self.broker_failed("umqtt_safe.py missing")
        if MQTT_TLS and self.tls is None:
            return self.broker_failed("no TLS settings (CA file {})".format(MQTT_CA_FILE))
        if MQTT_TLS and unix_time() is None:
            return self.broker_failed("clock not set (TLS needs the date)")
        try:
            addr = socket.getaddrinfo(MQTT_HOST, MQTT_PORT, 0, socket.SOCK_STREAM)[0][-1]
        except Exception as err:
            return self.broker_failed("DNS lookup failed: {}".format(err))
        self.feed()
        budget = sendpath.Budget(CONNECT_MS)
        client = MQTTClient(DEVICE_ID, user=MQTT_USER, password=MQTT_PASSWORD, keepalive=MQTT_KEEPALIVE_S)
        try:
            client.open(addr, budget.left, self.tls if MQTT_TLS else None, MQTT_HOST)
            client.connect()
        except Exception as err:
            try:
                client.close()
            except Exception:
                pass
            return self.broker_failed(sendpath.plain_error(err))
        self.feed()
        self.client = client
        self.broker_fault = False
        self.wait_s = RECONNECT_MIN_S
        self.next_ping = time.ticks_add(time.ticks_ms(), PING_EVERY_S * 1000)
        print("broker connected:", MQTT_HOST)
        self.send_boot()                          # the BOOT report goes on the first connection
        return self.client is not None

    def broker_failed(self, why):
        print("broker not connected:", why, "- next try in", self.wait_s, "s")
        self.drop_broker()
        self.broker_fault = True
        self.next_connect = time.ticks_add(time.ticks_ms(), self.wait_s * 1000)
        self.wait_s = min(self.wait_s * 2, RECONNECT_MAX_S)
        return False

    def drop_broker(self):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None

    def ping(self):
        """PINGREQ, then wait up to PING_WAIT_MS for PINGRESP. A dead connection is found
        here even when publishes (QoS 0) still seem to go out."""
        self.feed()
        try:
            self.client.left_ms = lambda: PUBLISH_IO_MS
            self.client.ping()
            budget = sendpath.Budget(PING_WAIT_MS)
            self.client.left_ms = budget.left
            while self.client.wait_msg() is not None:
                pass                                   # not the PINGRESP, read on
        except Exception as err:
            print("REF_SEND_FAIL reason=ping ({})".format(sendpath.plain_error(err)))
            self.broker_failed("no answer to ping")
            return
        self.next_ping = time.ticks_add(time.ticks_ms(), PING_EVERY_S * 1000)

    # --- readings ---
    def sample(self, now):
        if self.bme is None:
            if time.ticks_diff(now, self.next_sensor) >= 0:
                self.next_sensor = time.ticks_add(now, SENSOR_RETRY_S * 1000)
                print("Sensor:", self.sensor_start())
            if self.bme is None:
                self.window.add(None)
                return
        try:
            p, t = self.bme.read_q8()
        except Exception as err:
            print("pressure read error:", err)
            p, t = None, None
        self.window.add(p, t, now)

    def build(self, res, ts, ctr):
        msg = {"v": 1, "id": DEVICE_ID, "type": "REF", "ctr": ctr}
        if ts is not None:
            msg["ts"] = ts
        msg["p"] = res["p"]
        if res["t"] is not None:
            msg["t"] = res["t"]
        msg["pd"] = res["pd"]
        msg["n"] = res["n"]
        msg["fw"] = FW_VERSION
        msg["sig"] = msgsign.sign(SECRET_KEY, msg)
        return msg

    def publish(self, now):
        """The 30 s window as one signed REF. Nothing is sent (and no counter used) when
        there is no reading or no broker."""
        res = self.window.result()
        failed = self.window.failed
        ts = self.window.mid_ts(unix_time(), now, time.ticks_diff)
        self.window.reset()
        if res is None:
            self.sensor_fault = True
            print("REF_SKIP reason=no_readings failed={}".format(failed))
            if self.bme is not None:
                self.bme = None                       # start it again at the next reading
            return
        self.sensor_fault = False
        if self.client is None:
            print("REF_SKIP reason=broker_down p={}".format(baro.text(res["pd"])))
            return
        try:
            ctr = self.counter.take()                 # a flash write once per block
        except Exception as err:
            print("REF_SKIP reason=counter ({})".format(err))
            return
        msg = self.build(res, ts, ctr)
        self.feed()
        try:
            self.client.left_ms = lambda: PUBLISH_IO_MS
            self.client.publish(REF_TOPIC, json.dumps(msg), qos=0)
        except Exception as err:
            print("REF_SEND_FAIL reason=publish ({})".format(sendpath.plain_error(err)))
            self.broker_failed("publish failed")
            return
        self.sent += 1
        self.green_until = time.ticks_add(time.ticks_ms(), GREEN_FLASH_MS)
        print("REF_SENT ctr={} p={} t={} n={} ts={}".format(
            ctr, baro.text(res["pd"]), "-" if res["t"] is None else "{:.2f}".format(res["t"] / 100),
            res["n"], "-" if ts is None else ts))

    # --- network upkeep ---
    def upkeep(self, now):
        if not self.wifi_connected():
            if self.client is not None:
                print("WiFi lost")
                self.drop_broker()
            if self.joining:
                if time.ticks_diff(now, self.join_until) >= 0:
                    print("WiFi join timed out, next try in", self.wait_s, "s")
                    self.joining = False
                    self.wifi_stop()
                    self.next_join = time.ticks_add(now, self.wait_s * 1000)
                    self.wait_s = min(self.wait_s * 2, RECONNECT_MAX_S)
            elif time.ticks_diff(now, self.next_join) >= 0:
                self.wifi_start_join()
            return
        if self.joining:
            self.joining = False
            print("WiFi connected")
            self.wait_s = RECONNECT_MIN_S
            self.next_connect = now
            if not self.clock_ok:
                self.ntp()
        if time.ticks_diff(now, self.next_ntp) >= 0:
            self.ntp()
        if self.client is None:
            if time.ticks_diff(now, self.next_connect) >= 0:
                self.connect_broker()
        elif time.ticks_diff(now, self.next_ping) >= 0:
            self.ping()

    def led_update(self, now):
        if self.green_until is not None:
            if time.ticks_diff(now, self.green_until) < 0:
                self.led.set(GREEN)
                return
            self.green_until = None
        if self.sensor_fault:
            self.led.set(ORANGE)
        elif self.joining or not self.wifi_connected():
            self.led.set(BLUE if (now // 300) % 2 == 0 else OFF)     # joining, or waiting to try again
        elif self.broker_fault or self.client is None:
            self.led.set(ORANGE)
        else:
            self.led.set(OFF)

    def step(self, now):
        self.feed()
        # The publish first: a reading due at the same moment starts the next window,
        # so each 30 s window holds 15 readings, not 16.
        if time.ticks_diff(now, self.next_publish) >= 0:
            self.publish(now)
            self.next_publish = time.ticks_add(self.next_publish, PUBLISH_MS)
            if time.ticks_diff(now, self.next_publish) >= 0:
                self.next_publish = time.ticks_add(now, PUBLISH_MS)
        if time.ticks_diff(now, self.next_sample) >= 0:
            self.sample(now)
            self.next_sample = time.ticks_add(self.next_sample, SAMPLE_MS)
            if time.ticks_diff(now, self.next_sample) >= 0:      # fell behind (a slow connect)
                self.next_sample = time.ticks_add(now, SAMPLE_MS)
        self.upkeep(time.ticks_ms())
        self.led_update(time.ticks_ms())


def main():
    board = RefBoard()
    board.boot()
    while True:
        board.step(time.ticks_ms())
        time.sleep_ms(LOOP_MS)


if __name__ == "__main__":
    main()
