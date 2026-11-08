"""Desktop test for the Fob firmware. Runs main.py with a fake button, fake clock,
fake LED, fake motor and fake MQTT, then hands every message it "sends" to the real
server code (server/validate.py and processor.py) to prove the signatures are good.

  python sim_test.py

Needs only Python 3 and the packages in server/requirements.txt (Flask is not used).
This file is for your laptop. Do not upload it to Wokwi or the board."""
import hashlib
import hmac as std_hmac
import importlib
import json
import os
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "..", "server")
TMP = tempfile.mkdtemp(prefix="safeping_sim_")
KEY = "0123456789abcdef0123456789abcdef"


# ---------------------------------------------------------------- fake world
class World:
    def __init__(self):
        self.now = 0
        self.presses = []          # (down_ms, up_ms)
        self.led = []              # (ms, (r, g, b))
        self.motor = []            # (ms, 0 or 1)
        self.published = []        # (ms, topic, payload, qos)
        self.mqtt_failures = 0
        self.wifi_ok = True
        self.duty = {}
        self.led_by_ms = {}
        self.neo = []              # (ms, (r, g, b)) written to the NeoPixel
        self.epoch_2000 = False

    def button_down(self):
        return any(a <= self.now < b for a, b in self.presses)

    def reset(self, presses=(), mqtt_failures=0, wifi_ok=True):
        self.presses = list(presses)
        self.led, self.motor, self.published = [], [], []
        self.led_by_ms = {}
        self.neo = []
        self.duty = {}
        self.mqtt_failures = mqtt_failures
        self.wifi_ok = wifi_ok

    def motor_at(self, ms):
        level = 0
        for t, v in self.motor:
            if t <= ms:
                level = v
        return level


W = World()


def install_fakes():
    t = time
    t.ticks_ms = lambda: W.now
    t.ticks_diff = lambda a, b: a - b
    t.ticks_add = lambda a, b: a + b

    def sleep_ms(ms):
        W.now += ms
    t.sleep_ms = sleep_ms
    real_time, real_gmtime = time.time, time.gmtime
    base = 1760650000                      # Oct 2025, pretend the clock is right

    def fake_time():
        secs = base + W.now / 1000.0
        return secs - 946684800 if W.epoch_2000 else secs

    def fake_gmtime(secs=None):
        if secs == 0 and W.epoch_2000:
            return (2000, 1, 1, 0, 0, 0, 5, 1)
        return real_gmtime(secs) if secs is not None else real_gmtime()
    t.time, t.gmtime = fake_time, fake_gmtime

    class Pin:
        IN, OUT, PULL_UP = 0, 1, 2

        def __init__(self, number, mode=None, pull=None, value=0):
            self.number, self.mode, self.level = number, mode, value

        def value(self, v=None):
            if v is None:
                return 0 if W.button_down() else 1
            if self.number == 18 and v != self.level:
                W.motor.append((W.now, v))
            self.level = v

    class PWM:
        channels = {}

        def __init__(self, pin, freq=1000):
            self.pin = pin.number

        def duty_u16(self, v):
            W.duty[self.pin] = v // 257
            # three channels are written one after another, so only the state at the
            # end of each millisecond counts as "what the LED showed"
            W.led_by_ms[W.now] = (W.duty.get(2, 0), W.duty.get(4, 0), W.duty.get(5, 0))

    machine = types.ModuleType("machine")
    machine.Pin, machine.PWM = Pin, PWM
    sys.modules["machine"] = machine

    class WLAN:
        def __init__(self, kind): pass
        def active(self, on=True): pass
        def connect(self, ssid, password): pass
        def isconnected(self): return W.wifi_ok

    network = types.ModuleType("network")
    network.WLAN, network.STA_IF = WLAN, 0
    sys.modules["network"] = network

    class MQTTClient:
        def __init__(self, client_id, server, port=0, user=None, password=None, keepalive=0):
            pass

        def connect(self):
            if W.mqtt_failures > 0:
                W.mqtt_failures -= 1
                raise OSError("broker unreachable")

        def publish(self, topic, msg, retain=False, qos=0):
            W.published.append((W.now, topic, msg, qos))

        def disconnect(self): pass

    umqtt = types.ModuleType("umqtt")
    simple = types.ModuleType("umqtt.simple")
    simple.MQTTClient = MQTTClient
    sys.modules["umqtt"], sys.modules["umqtt.simple"] = umqtt, simple

    class NeoPixel:
        def __init__(self, pin, n):
            self.buf = [(0, 0, 0)] * n

        def __setitem__(self, i, rgb):
            self.buf[i] = rgb

        def write(self):
            W.neo.append((W.now, tuple(self.buf[0])))

    neopixel = types.ModuleType("neopixel")
    neopixel.NeoPixel = NeoPixel
    sys.modules["neopixel"] = neopixel

    cfg = types.ModuleType("config")
    cfg.DEVICE_ID, cfg.SECRET_KEY = "FOB-001", KEY
    cfg.COUNTER_FILE = os.path.join(TMP, "counter.txt")
    sys.modules["config"] = cfg


def load_firmware():
    sys.path.insert(0, HERE)
    if "main" in sys.modules:
        del sys.modules["main"]
    return importlib.import_module("main")


# ---------------------------------------------------------------- real server
def load_server():
    os.environ["SAFEPING_DB"] = os.path.join(TMP, "server.db")
    sys.path.insert(0, SERVER)
    # The server and the firmware both have a config.py. Hide the fake firmware one
    # while the server modules import theirs, then put it back for the firmware.
    fake_cfg = sys.modules.pop("config")
    for name in ("db", "validate", "processor", "location", "notify"):
        sys.modules.pop(name, None)
    import db, processor, validate
    db.init_db()
    db.add_device("FOB-001", "FOB", "Test Student", KEY)
    sys.modules["config"] = fake_cfg
    return db, processor, validate


# ---------------------------------------------------------------- helpers
passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  ok    ", name)
    else:
        failed += 1
        print("  FAIL  ", name, detail)


def play(fw, presses, run_ms=12000, **world):
    """Run one scenario. Returns the list of (ms, parsed message)."""
    W.now = 100
    W.reset([(a + 100, b + 100) for a, b in presses], **world)
    fob = fw.Fob()
    end = W.now + run_ms
    while W.now < end:
        fob.step(W.now)
        W.now += 10
    return [(ms - 100, json.loads(p)) for ms, _t, p, _q in W.published], fob


def taps(*times, length=80):
    return [(t, t + length) for t in times]


def lit(colors_only=None):
    out = [(ms - 100, c) for ms, c in sorted(W.led_by_ms.items()) if c != (0, 0, 0)]
    if colors_only:
        out = [x for x in out if x[1] == colors_only]
    return out


def main():
    import io
    install_fakes()
    db, processor, validate = load_server()
    fw = load_firmware()
    loud = sys.stdout

    def quiet(fn, *a, **k):
        sys.stdout = io.StringIO()
        try:
            return fn(*a, **k)
        finally:
            sys.stdout = loud

    print("\nSigning")
    import random
    random.seed(1)
    bad = 0
    for klen in (1, 16, 32, 63, 64, 65, 100, 200):
        key = bytes(random.randrange(256) for _ in range(klen))
        msg = bytes(random.randrange(256) for _ in range(random.randrange(0, 150)))
        if fw.hmac_sha256(key, msg) != std_hmac.new(key, msg, hashlib.sha256).digest():
            bad += 1
    check("HMAC-SHA256 matches Python's hmac for keys of 1 to 200 bytes", bad == 0)
    example = {"v": 1, "id": "FOB-001", "type": "SILENT", "ctr": 42, "ts": 1760650000,
               "lat": 34730123, "lon": -86586104, "acc": 8, "p": 101240, "bat": 87}
    check("signing string matches message-format.md",
          fw.signing_string(example) == "1|FOB-001|SILENT|42|1760650000|34730123|-86586104|8|101240||87")

    def server_accepts(msgs):
        results = [processor.process(json.dumps(m), now=1760650000 + i) for i, (_t, m) in enumerate(msgs)]
        return results

    print("\n1 press: STATUS")
    msgs, _ = quiet(play, fw, taps(1000))
    check("one STATUS message sent", [m["type"] for _t, m in msgs] == ["STATUS"], msgs)
    check("sent about 0.6 s after the release", msgs and 1650 <= msgs[0][0] <= 1800, msgs and msgs[0][0])
    check("white blink, no yellow or red", lit((255, 255, 255)) and not lit((255, 180, 0)) and not lit((255, 0, 0)))
    r = server_accepts(msgs)
    check("server accepts it", r[0]["ok"] and r[0]["type"] == "STATUS" and r[0]["sms"] is None, r)

    print("\n2 presses: SUSPICIOUS")
    msgs, _ = quiet(play, fw, taps(1000, 1300))
    check("one SUSPICIOUS message", [m["type"] for _t, m in msgs] == ["SUSPICIOUS"], msgs)
    t_send = msgs[0][0]
    check("held for the 2 s cancel window first", 4000 <= t_send <= 4150, t_send)
    yellow = lit((255, 180, 0))
    check("yellow slow blink before sending", len([1 for t, _ in yellow if t < t_send]) >= 2)
    check("solid yellow after sending", any(t >= t_send for t, _ in yellow))
    r = server_accepts(msgs)
    check("server accepts it", r[0]["ok"] and r[0]["type"] == "SUSPICIOUS", r)

    print("\n3 presses: MEDICAL")
    msgs, _ = quiet(play, fw, taps(1000, 1250, 1500))
    check("one MEDICAL message", [m["type"] for _t, m in msgs] == ["MEDICAL"], msgs)
    t_send = msgs[0][0]
    check("sent 2 s after the third press", 3550 <= t_send <= 3700, t_send)
    check("buzz stays on from the trigger until sent", all(W.motor_at(t + 100) == 1 for t in range(1700, t_send - 20, 20)))
    check("red fast blink", len(lit((255, 0, 0))) >= 5)
    r = server_accepts(msgs)
    check("server accepts it and texts", r[0]["ok"] and r[0]["type"] == "MEDICAL" and r[0]["sms"] is not None, r)

    print("\n5 fast presses still make ONE medical alert")
    msgs, _ = quiet(play, fw, taps(1000, 1200, 1400, 1550, 1700))
    check("one MEDICAL, not cancelled by extra presses", [m["type"] for _t, m in msgs] == ["MEDICAL"], msgs)

    print("\nCancel window")
    msgs, fob = quiet(play, fw, taps(1000, 1300) + taps(3000))
    check("2 presses then a tap: nothing sent", msgs == [], msgs)
    check("green blink shows it was cancelled", len(lit((0, 255, 0))) >= 1)
    msgs, fob = quiet(play, fw, taps(1000, 1250, 1500) + taps(2900))
    check("3 presses then a tap after 0.6 s: nothing sent", msgs == [], msgs)
    check("buzz is off after the cancel", W.motor_at(W.now - 1) == 0)

    print("\nHold 5 s: SILENT")
    msgs, _ = quiet(play, fw, [(1000, 7000)])
    check("one SILENT message", [m["type"] for _t, m in msgs] == ["SILENT"], msgs)
    check("sent as soon as 5 s is reached", 6000 <= msgs[0][0] <= 6200, msgs and msgs[0][0])
    check("LED never lit", lit() == [], lit())
    check("buzz used", any(v == 1 for _t, v in W.motor))
    r = server_accepts(msgs)
    check("server accepts it", r[0]["ok"] and r[0]["type"] == "SILENT", r)
    msgs, _ = quiet(play, fw, taps(1000, 1300) + [(2500, 8000)])
    check("hold during the cancel window gives SILENT only", [m["type"] for _t, m in msgs] == ["SILENT"], msgs)

    print("\nOther behavior")
    msgs, _ = quiet(play, fw, [(1000, 1005), (1010, 1015), (1020, 1100)])
    check("contact bounce counts as one press", [m["type"] for _t, m in msgs] == ["STATUS"], msgs)
    msgs, _ = quiet(play, fw, taps(1000, 1300) + taps(5000) + taps(8200))
    check("presses right after an alert are ignored, later ones work",
          [m["type"] for _t, m in msgs] == ["SUSPICIOUS", "STATUS"], [m["type"] for _t, m in msgs])

    print("\nCounter and replay")
    ctrs = []
    for _ in range(4):
        msgs, _ = quiet(play, fw, taps(1000))
        ctrs.append(msgs[0][1]["ctr"])
    check("counter goes up by one each message and is saved", ctrs == list(range(ctrs[0], ctrs[0] + 4)), ctrs)
    saved = int(open(os.path.join(TMP, "counter.txt")).read())
    check("saved counter equals the last one sent", saved == ctrs[-1], (saved, ctrs))
    msgs, _ = quiet(play, fw, taps(1000))
    first = msgs[0][1]
    r1 = processor.process(json.dumps(first), now=1760650100)
    r2 = processor.process(json.dumps(first), now=1760650101)
    check("server accepts then rejects the same message as replay",
          r1["ok"] and (not r2["ok"]) and r2["reason"] == "replay", (r1, r2))
    forged = dict(first)
    forged["ctr"] = first["ctr"] + 50
    r3 = processor.process(json.dumps(forged), now=1760650102)
    check("changing a field breaks the signature", (not r3["ok"]) and r3["reason"] == "bad_signature", r3)
    with open(os.path.join(TMP, "counter.txt"), "w") as f:
        f.write("garbage")
    msgs, _ = quiet(play, fw, taps(1000))
    r = processor.process(json.dumps(msgs[0][1]), now=1760650200)
    check("damaged counter file recovers and the server still accepts", r["ok"], (msgs[0][1]["ctr"], r))

    print("\nClock")
    W.epoch_2000 = True
    fw = load_firmware()
    msgs, _ = quiet(play, fw, taps(1000))
    ts = msgs[0][1].get("ts")
    check("clock counting from 2000 is converted to Unix time", ts is not None and 1760650000 <= ts <= 1760650020, ts)
    W.epoch_2000 = False
    fw = load_firmware()

    print("\nStart up and the real LED")
    W.now = 100
    W.reset()
    fob = fw.Fob()
    quiet(fob.boot)
    check("boot runs with WiFi up", True)
    W.reset(wifi_ok=False)
    fob = fw.Fob()
    quiet(fob.boot)
    check("boot runs with no WiFi (no crash)", True)
    sys.modules["config"].LED_TYPE = "neopixel"
    fw = load_firmware()
    msgs, _ = quiet(play, fw, taps(1000, 1300))
    seen = set(c for _t, c in W.neo)
    check("NeoPixel mode drives the pixel (yellow, then off)", (255, 180, 0) in seen and (0, 0, 0) in seen, seen)
    check("NeoPixel mode still sends", [m["type"] for _t, m in msgs] == ["SUSPICIOUS"], msgs)
    del sys.modules["config"].LED_TYPE
    fw = load_firmware()

    print("\nNetwork trouble")
    msgs, _ = quiet(play, fw, taps(1000, 1300), mqtt_failures=2)
    check("sent on the third try", [m["type"] for _t, m in msgs] == ["SUSPICIOUS"], msgs)
    r = processor.process(json.dumps(msgs[0][1]), now=1760650300)
    check("server accepts it", r["ok"], r)
    msgs, _ = quiet(play, fw, taps(1000, 1300), mqtt_failures=99)
    check("nothing published when the broker is down", msgs == [])
    check("orange shows the connection problem", len(lit((255, 90, 0))) >= 1)
    msgs, _ = quiet(play, fw, taps(1000), mqtt_failures=0)
    r = processor.process(json.dumps(msgs[0][1]), now=1760650400)
    check("a later message still works (counter gap is fine)", r["ok"], r)
    msgs, _ = quiet(play, fw, taps(1000), wifi_ok=False)
    check("no WiFi: no crash, nothing sent", msgs == [])
    msgs, _ = quiet(play, fw, [(1000, 7000)], mqtt_failures=99)
    check("failed SILENT stays dark", lit() == [], lit())

    print("\nWhat the server logged")
    with db.connect() as c:
        n_alerts = c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        reasons = [r["reason"] for r in c.execute("SELECT reason FROM rejected")]
    check("every message the server accepted was stored", n_alerts == 8, n_alerts)
    check("rejections logged with reasons", sorted(reasons) == ["bad_signature", "replay"], reasons)

    print("\n{} passed, {} failed".format(passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
