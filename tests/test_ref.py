"""Laptop test for the Reference board firmware (firmware/ref/main.py). No board.

Runs the real main.py on fake pins, a fake sensor, fake WiFi and a fake broker, and
checks every REF message against the real server code (throwaway database):

  1. the averaging window (baro.py): one decimal, rounding, the window's middle time
  2. boot: sensor found at 0x76 after 0x77 fails, SELF_CHECK line, broker connected
  3. 30 s of readings make one signed REF with n=15, the server accepts it, and the board
     and the server build the same signing string
  4. the counter is saved in blocks and never reused after a restart
  5. broker drop, WiFi drop, a dead connection (ping) and a sensor that stops: the right
     light, no counter used for nothing, and it reconnects by itself
  6. old-style REF (no pd) still accepted, and the server rejects a REF whose p and pd differ

  python tests/test_ref.py"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard       # noqa: E402  (puts firmware/lib on the path)
import baro            # noqa: E402
import msgsign         # noqa: E402

REF_MAIN = os.path.join(HERE, "..", "firmware", "ref", "main.py")
SERVER = os.path.join(HERE, "..", "server")
KEY = "e" * 32                      # test key, not a real one
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + str(detail) if detail and not passed else ""))


# ---------- fakes ----------
class FakeWLAN:
    connected = [True]

    def __init__(self, i=0):
        self._active = False

    def active(self, v=None):
        if v is None:
            return self._active
        self._active = v

    def isconnected(self):
        return self._active and FakeWLAN.connected[0]

    def status(self):
        return 0

    def connect(self, *a):
        pass

    def disconnect(self):
        pass


class FakeBme:
    """read_q8() gives pascals x 256. values: a list used in turn, or raise when fail."""

    def __init__(self, chip=0x60):
        self.chip_id = chip
        self.values = [int(98812.25 * 256), int(98812.75 * 256)]
        self.i = 0
        self.fail = False

    def read_q8(self):
        if self.fail:
            raise OSError("I2C read failed")
        v = self.values[self.i % len(self.values)]
        self.i += 1
        return v, 2150


class FakeBmeModule:
    def __init__(self):
        self.tried = []
        self.sensor = FakeBme()

    def BME280(self, i2c, addr):
        self.tried.append(addr)
        if addr == 0x77:
            raise OSError("BME280 not found at 0x77")
        return self.sensor


class FakeClient:
    instances = []
    fail_publish = [False]
    fail_connect = [False]
    fail_ping = [False]

    def __init__(self, client_id, user=None, password=None, keepalive=0):
        self.client_id, self.user, self.keepalive = client_id, user, keepalive
        self.published = []
        self.closed = False
        self.left_ms = lambda: 1000
        FakeClient.instances.append(self)

    def open(self, addr, left_ms, ssl_context=None, server_hostname=None):
        if FakeClient.fail_connect[0]:
            raise OSError("connect refused")

    def connect(self):
        return 0

    def publish(self, topic, msg, retain=False, qos=0):
        if FakeClient.fail_publish[0]:
            raise OSError("connection reset")
        self.published.append((topic, msg, qos))

    def ping(self):
        pass

    def wait_msg(self):
        if FakeClient.fail_ping[0]:
            raise OSError("timed out")
        return None                               # PINGRESP

    def close(self):
        self.closed = True


class FakeSocket:
    SOCK_STREAM = 1

    @staticmethod
    def getaddrinfo(host, port, *a):
        return [(2, 1, 0, "", ("192.0.2.10", port))]


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


def load_ref(workdir, extra=None):
    """firmware/ref/main.py with fake modules, in its own folder (counter.txt lives there)."""
    fakeboard._install()
    fakeboard._patch_time()
    sys.modules["network"].WLAN = FakeWLAN
    os.chdir(workdir)
    cfg = types.ModuleType("config")
    values = {"DEVICE_ID": "REF-T", "SECRET_KEY": KEY, "WIFI_SSID": "test-net",
              "MQTT_TLS": False, "WATCHDOG_ENABLED": True, "WIFI_JOIN_MS": 2000}
    values.update(extra or {})
    for k, v in values.items():
        setattr(cfg, k, v)
    sys.modules["config"] = cfg
    sys.modules["machine"].I2C = lambda *a, **k: object()
    spec = importlib.util.spec_from_file_location("ref_main", REF_MAIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.bme280 = FakeBmeModule()
    mod.MQTTClient = FakeClient
    mod.socket = FakeSocket
    mod.ntptime = None
    return mod


def run_for(board, ms, step_ms=50):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        end = fakeboard.clock[0] + ms
        while fakeboard.clock[0] < end:
            fakeboard.clock[0] += step_ms
            board.step(fakeboard.clock[0])
    return out.getvalue()


def every_publish():
    return [p for c in FakeClient.instances for p in c.published]


def all_published():
    """The REF readings only (the BOOT report is the first publish)."""
    return [p for p in every_publish() if json.loads(p[1])["type"] == "REF"]


def boots_published():
    return [json.loads(p[1]) for p in every_publish() if json.loads(p[1])["type"] == "BOOT"]


# ---------- 1. the window ----------
def test_window():
    w = baro.Window()
    check("empty window has no result", w.result() is None and w.tenths() is None)
    w.add(int(98812.25 * 256), 2150, 1000)
    w.add(int(98812.75 * 256), 2160, 3000)
    r = w.result()
    check("average to one decimal (98812.25 and 98812.75 -> 98812.5)", r["pd"] == 988125, r)
    check("whole pascals is pd rounded", r["p"] == 98813, r)
    check("temperature average", r["t"] == 2155, r)
    check("readings counted", r["n"] == 2, r)
    w.add(None)
    check("a failed reading is counted, not averaged", w.failed == 1 and w.result()["n"] == 2)
    # window from 1000 to 3000 ms, middle at 2000; now is 5000 ms at Unix 1763140000
    check("ts is the middle of the window", w.mid_ts(1763140000, 5000, lambda a, b: a - b) == 1763139997)
    check("no clock: no ts", w.mid_ts(None, 5000, lambda a, b: a - b) is None)
    check("text with one decimal", baro.text(988124) == "98812.4" and baro.text(None) == "-")
    w2 = baro.Window()
    for v in (98800.0, 98800.0, 98800.1):
        w2.add(int(round(v * 256)))
    check("rounding: 98800.033 -> 98800.0", w2.tenths() == 988000, w2.tenths())


# ---------- 2 to 5. the board ----------
def test_board():
    work = tempfile.mkdtemp()
    FakeClient.instances.clear()
    FakeWLAN.connected[0] = True
    ref = load_ref(work)
    board = ref.RefBoard()
    _, log = quiet(board.boot)
    check("sensor tried 0x77 then 0x76", ref.bme280.tried == [0x77, 0x76], ref.bme280.tried)
    check("boot says which chip it found", "Sensor: BME280 (chip id 0x60) at 0x76" in log, log)
    check("SELF_CHECK line with the board's checks and the sensor",
          "SELF_CHECK key=ok counter=new pressure=ok wifi=ok reset=power_on fw=" + ref.FW_VERSION
          + " sensor=BME280@0x76" in log, log)
    check("SENSOR line: model, chip id and address",
          "SENSOR model=BME280 chip_id=0x60 address=0x76 i2c=-" in log, log)
    check("MicroPython version printed at boot", "MicroPython " in log)
    boots = boots_published()
    check("BOOT report published on the first connection", len(boots) == 1 and "BOOT_SENT ctr=0" in log, log)
    b = boots[0]
    check("BOOT report: sensor, no failed checks, WiFi, firmware, reset cause",
          b["sensor"] == "BME280@0x76" and b["fail"] == 0 and b["wifi"] == 1 and b["fw"] == ref.FW_VERSION
          and b["rst"] == 1 and b["ctr"] == 0, b)
    check("BOOT report signed with the sensor at the end",
          msgsign.signing_string(b).endswith("|BME280@0x76") and b["sig"] == msgsign.sign(
              KEY, {k: v for k, v in b.items() if k != "sig"}))
    check("broker connected at boot", board.client is not None and "broker connected" in log, log)
    check("broker user and client id", board.client.user == "safeping-ref" and board.client.client_id == "REF-T")
    check("watchdog started", board.wdt is not None and "watchdog on" in log)
    check("topic is safeping/ref/<id>", ref.REF_TOPIC == "safeping/ref/REF-T")

    log = run_for(board, 30000)
    pubs = all_published()
    check("30 s: one REF published", len(pubs) == 1, log)
    topic, payload, qos = pubs[0]
    msg = json.loads(payload)
    check("published to safeping/ref/REF-T at QoS 0", topic == "safeping/ref/REF-T" and qos == 0)
    check("n=15 readings in 30 s", msg["n"] == 15, msg)
    check("pd to one decimal (alternating .25 and .75)", msg["pd"] in (988125, 988124, 988126), msg)
    check("p is pd rounded", msg["p"] == (msg["pd"] + 5) // 10, msg)
    check("fw sent", msg["fw"] == ref.FW_VERSION)
    check("ts is set (clock works on the laptop)", isinstance(msg.get("ts"), int))
    check("first reading's counter is 1 (the BOOT report had 0)", msg["ctr"] == 1)
    check("signature made by msgsign", msg["sig"] == msgsign.sign(KEY, {k: v for k, v in msg.items() if k != "sig"}))
    check("payload under 512 bytes", len(payload) < 512, len(payload))
    check("REF_SENT log line", "REF_SENT ctr=1 p=" in log and " n=15 " in log, log)
    check("green flash after the publish", board.green_until is not None or board.led.shown == ref.OFF)
    with open(os.path.join(work, "counter.txt")) as f:
        check("counter saved as a block (ceiling 19)", f.read().strip() == "19")

    # ---- LED: green right after, then off ----
    board.green_until = time.ticks_add(fakeboard.clock[0], 150)
    board.led_update(fakeboard.clock[0])
    green = board.led.shown == ref.GREEN
    board.led_update(fakeboard.clock[0] + 200)
    check("short green blink, then off", green and board.led.shown == ref.OFF, board.led.shown)

    # ---- counter blocks: 25 publishes, then a restart never reuses ----
    log = run_for(board, 30000 * 24)
    ctrs = [json.loads(p[1])["ctr"] for p in every_publish()]
    check("counters go up by one (BOOT report, then readings)", ctrs == list(range(len(ctrs))), ctrs[-3:])
    with open(os.path.join(work, "counter.txt")) as f:
        ceiling = int(f.read().strip())
    check("second block written when the first ran out", ceiling == 39, ceiling)
    again = ref.BlockCounter(ref.COUNTER_FILE, ref.COUNTER_BLOCK)
    again.start(None)
    first = again.take()
    check("after a restart the counter starts above every used one", first > max(ctrs) and first == 40, first)

    # ---- broker drops: orange, no counter used, reconnect with a growing wait ----
    used_before = board.counter.next
    FakeClient.fail_publish[0] = True
    log = run_for(board, 30000)
    FakeClient.fail_publish[0] = False
    check("publish failure logged", "REF_SEND_FAIL reason=publish" in log, log)
    check("client dropped and broker marked failed", board.client is None and board.broker_fault)
    board.led_update(fakeboard.clock[0] + 1000)
    check("steady orange while the broker is down", board.led.shown == ref.ORANGE)
    FakeClient.fail_connect[0] = True
    log = run_for(board, 6000)
    check("reconnect tried after 5 s and failed: next wait 10 s",
          "next try in 10 s" in log, log)
    log = run_for(board, 11000)
    check("then 20 s", "next try in 20 s" in log, log)
    FakeClient.fail_connect[0] = False
    log = run_for(board, 21000)
    check("reconnects by itself", board.client is not None and not board.broker_fault and "broker connected" in log, log)
    check("wait back to 5 s after a good connect", board.wait_s == ref.RECONNECT_MIN_S)
    check("windows while the broker was down used no counter",
          board.counter.next - used_before <= 1, board.counter.next - used_before)

    # ---- WiFi drops: blue blink while joining, then reconnect ----
    FakeWLAN.connected[0] = False
    log = run_for(board, 200)
    check("WiFi loss drops the broker", "WiFi lost" in log and board.client is None, log)
    run_for(board, 6000)
    colors = set()
    for t in range(0, 1200, 100):
        board.led_update(fakeboard.clock[0] + t)
        colors.add(board.led.shown)
    check("blue blink while WiFi is down (joining or waiting)", ref.BLUE in colors and ref.OFF in colors, colors)
    FakeWLAN.connected[0] = True
    log = run_for(board, 1000)
    check("WiFi back: broker reconnects", "WiFi connected" in log and board.client is not None, log)

    # ---- dead connection found by ping ----
    FakeClient.fail_ping[0] = True
    log = run_for(board, (ref.PING_EVERY_S + 1) * 1000)
    FakeClient.fail_ping[0] = False
    check("no answer to ping: reconnect", "reason=ping" in log, log)

    # ---- the sensor stops: orange, nothing sent, it is started again ----
    run_for(board, 15000)
    ref.bme280.sensor.fail = True
    run_for(board, 31000)                          # the window the failure started in still had readings
    before = len(all_published())
    log = run_for(board, 31000)
    check("a window with no readings is skipped", "REF_SKIP reason=no_readings" in log, log)
    check("the sensor is started again while it fails", "Sensor: BME280" in log, log[-300:])
    check("nothing published without readings", len(all_published()) == before)
    board.led_update(fakeboard.clock[0] + 1000)
    check("steady orange while the sensor fails", board.led.shown == ref.ORANGE)
    ref.bme280.sensor.fail = False
    log = run_for(board, 65000)
    check("sensor reads again: readings published, orange gone",
          len(all_published()) > before and not board.sensor_fault, log[-400:])
    return [json.loads(p[1]) for p in all_published()], boots_published()


def test_i2c_scan():
    """The sensor is picked from the addresses that answer (1.29's new I2C driver)."""
    class ScanI2C:
        def scan(self):
            return [0x36, 0x77]
    ref = load_ref(tempfile.mkdtemp())
    sys.modules["machine"].I2C = lambda *a, **k: ScanI2C()
    tried = []

    class Module:
        def BME280(self, i2c, addr):
            tried.append(addr)
            return FakeBme(chip=0x58)
    ref.bme280 = Module()
    board = ref.RefBoard()
    status, log = quiet(board.sensor_start)
    check("I2C scan: only the address that answered is tried", tried == [0x77], tried)
    check("BMP280 named from its chip id", board.sensor_name == "BMP280@0x77" and "BMP280" in status, status)
    check("SENSOR line lists what answered on the bus", "SENSOR model=BMP280 chip_id=0x58 address=0x77 i2c=0x36,0x77" in log, log)

    class EmptyI2C:
        def scan(self):
            return []
    sys.modules["machine"].I2C = lambda *a, **k: EmptyI2C()
    tried.clear()
    ref.bme280 = types.SimpleNamespace(BME280=lambda i2c, addr: tried.append(addr) or (_ for _ in ()).throw(OSError("no device")))
    board = ref.RefBoard()
    status, log = quiet(board.sensor_start)
    check("nothing on the bus: both addresses tried, then sensor off", tried == [0x77, 0x76] and status.startswith("off"), tried)
    check("SENSOR line says none", "SENSOR model=none address=- i2c=nothing" in log and board.sensor_name == "none", log)


# ---------- 6. against the real server ----------
def test_server(msgs, boots=()):
    sys.path.insert(0, SERVER)
    os.environ["SAFEPING_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
    for name in ("config", "db", "validate", "processor", "refmatch", "location", "app", "stats"):
        sys.modules.pop(name, None)
    import db
    import processor
    import validate
    db.init_db()
    db.add_device("REF-T", "REF", None, KEY)
    msg = msgs[0]
    if boots:
        b = boots[0]
        check("board and server build the same BOOT signing string (with sensor)",
              validate.signing_string(b) == msgsign.signing_string(b), validate.signing_string(b))
        acks = []
        r = processor.process(json.dumps(b), now=time.time(), on_ack=lambda *a: acks.append(a))
        check("server accepts the Reference board's BOOT report", r.get("ok") and r.get("kind") == "boot", r)
        check("the BOOT report is stored with its sensor", db.latest_boots()["REF-T"]["sensor"] == "BME280@0x76")
        import app
        devices = app.app.test_client().get("/api/devices").get_json()["devices"]
        refdev = [d for d in devices if d["device_id"] == "REF-T"][0]
        check("/api/devices: the board's last start has the sensor",
              refdev["last_boot"] is not None and refdev["last_boot"]["sensor"] == "BME280@0x76", refdev["last_boot"])
        bad = dict(b, ctr=b["ctr"] + 500, sensor="BME 280!")
        bad.pop("sig")
        bad["sig"] = msgsign.sign(KEY, bad)
        r = processor.process(json.dumps(bad))
        check("a sensor name with bad characters is rejected", r == {"ok": False, "reason": "bad_format"}, r)
    check("board and server build the same REF signing string",
          validate.signing_string(msg) == msgsign.signing_string(msg), validate.signing_string(msg))
    check("REF signing string ends with pd|n|fw",
          validate.signing_string(msg).endswith("|{}|{}|{}".format(msg["pd"], msg["n"], msg["fw"])))
    now = time.time()
    r = processor.process(json.dumps(msg), now=now, source="wifi")
    check("server accepts the board's REF", r == {"ok": True, "kind": "reference"}, r)
    row = db.latest_reference()
    check("stored with device, one decimal, samples and firmware",
          row["device_id"] == "REF-T" and row["pressure_dpa"] == msg["pd"] and row["samples"] == 15
          and row["firmware"] == msg["fw"], row)
    check("ref_time is the board's ts", row["ref_time"] == msg["ts"], row)
    r = processor.process(json.dumps(msg), now=now + 1)
    check("the same REF again is a replay", r == {"ok": False, "reason": "replay"}, r)
    ok = all(processor.process(json.dumps(m), now=now + 2)["ok"] for m in msgs[1:6])
    check("the next readings are accepted (counter goes up)", ok)

    old = {"v": 1, "id": "REF-T", "type": "REF", "ctr": 100000, "p": 98810, "t": 2100}
    old["sig"] = validate.sign(KEY, old)
    r = processor.process(json.dumps(old), now=now + 3)
    check("old-style REF without pd still accepted", r.get("ok"), r)

    bad = dict(msg, ctr=100001, p=98700)
    bad.pop("sig")
    bad["sig"] = msgsign.sign(KEY, bad)
    r = processor.process(json.dumps(bad), now=now + 4)
    check("REF whose p and pd differ is rejected", r == {"ok": False, "reason": "bad_format"}, r)
    badfw = dict(msg, ctr=100002, fw="bad fw!")
    badfw.pop("sig")
    badfw["sig"] = msgsign.sign(KEY, badfw)
    r = processor.process(json.dumps(badfw), now=now + 5)
    check("REF with a bad fw is rejected", r == {"ok": False, "reason": "bad_format"}, r)
    forged = dict(msg, ctr=100003)
    r = processor.process(json.dumps(forged), now=now + 6)
    check("REF with a wrong signature is rejected", r == {"ok": False, "reason": "bad_signature"}, r)
    db.add_device("FOB-X", "FOB", "Someone", KEY)
    fob_ref = dict(msg, id="FOB-X", ctr=5)
    fob_ref.pop("sig")
    fob_ref["sig"] = msgsign.sign(KEY, fob_ref)
    r = processor.process(json.dumps(fob_ref), now=now + 7)
    check("a Fob cannot send REF", r == {"ok": False, "reason": "wrong_role"}, r)


def main():
    test_window()
    test_i2c_scan()
    msgs, boots = test_board()
    test_server(msgs, boots)
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
