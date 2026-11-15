"""Laptop test for survey mode on the Fob (firmware/fob/main.py, firmware/lib/survey.py).
No board. Runs the real main.py on the fake board, then sends every SURVEY message it
made through the real server code (throwaway database).

Fob side
  1. survey mode on: long blue blink at boot, the waiting points are read
  2. one press: a survey point (15 readings, GPS info, WiFi scan, signed), sent to
     safeping/survey/<id> over WiFi, never LoRa, two short green blinks, SURVEY_POINT line
  3. two presses: still a normal SUSPICIOUS alert. Survey mode off: one press is STATUS
  4. no WiFi: the point is kept in survey_q/<ctr>.json and survives a restart; a .tmp
     left by a crash is removed; sent later while idle, oldest first; a press stops that;
     alerts in the retry queue go first; a full store gives orange
  5. SURVEY_AUTO_MS makes points by itself (calibration)
  6. ap_list: strongest first, one per BSSID, at most 15, SSID as hex
Server side
  7. the server accepts each point, acks it, stores it in survey_points, never as an
     alert, never Pushover; the Fob and server build the same signing string
  8. a point far below the newest counter is still accepted (no window), a copy is a
     duplicate and acked again, the same counter with another signature is a replay
  9. bad points are rejected (APs, size, fix without position)
 10. the reference pressure at the point's time is stored, and /api/survey shows SSIDs

  python tests/test_survey.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard       # noqa: E402
import msgsign         # noqa: E402
import survey          # noqa: E402

SERVER = os.path.join(HERE, "..", "server")
KEY = "f" * 32                      # fakeboard's test key, not a real one
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + str(detail) if detail and not passed else ""))


# ---------- fakes ----------
class FakeBme:
    def __init__(self):
        self.values = [int(98760.2 * 256), int(98760.4 * 256)]
        self.i = 0

    def read_q8(self):
        v = self.values[self.i % 2]
        self.i += 1
        return v, 2210


class FakeGps:
    def __init__(self, fix):
        self.has_fix = fix
        self.lat_e6, self.lon_e6 = (34725549, -86655274) if fix else (None, None)
        self.sats = 7 if fix else 2
        self.hdop = "0.9"
        self.sentences = 10

    def age_s(self):
        return 1

    def update(self):
        pass


def scan_entries(n=18, long_ssid=False):
    out = []
    for i in range(n):
        ssid = ("x" * 40).encode() if long_ssid else "School-{}".format(i % 4).encode()
        out.append((ssid, bytes([0x10, 0x20, 0x30, 0x40, 0x50, i]), 1 + i % 11, -40 - i * 3, 3, False))
    out.append((b"School-0", bytes([0x10, 0x20, 0x30, 0x40, 0x50, 5]), 6, -30, 3, False))   # same BSSID, stronger
    out.append((b"broken", b"\x01\x02", 6, -20, 3, False))                                   # bad BSSID, skipped
    return out


class FakeSta:
    def __init__(self, entries):
        self.entries = entries
        self.scans = 0

    def scan(self):
        self.scans += 1
        return list(self.entries)


class Recorder:
    def __init__(self):
        self.sent = []            # (topic, payload) of every WiFi send
        self.lora = []
        self.wifi_ok = True

    def wifi_send(self, payload, ctr, sig, budget, service=None, keep_open=None, stop=None, topic=None):
        self.sent.append((topic, payload))
        if self.wifi_ok:
            return True, "-", True, None
        return False, "wifi_join_failed", False, None

    def lora_send(self, payload, ctr, sig, stop=None):
        self.lora.append(ctr)
        return "confirmed"


LOGS = []                           # every Fob log line, for the field logger check


def run(fob, pattern):
    """Drive step() every 10 ms. pattern: list of (button level, ms). Returns the log."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        for level, ms in pattern:
            fakeboard.button.set(level)
            for _ in range(ms // 10):
                fakeboard.clock[0] += 10
                fob.step(fakeboard.clock[0])
    LOGS.append(out.getvalue())
    return out.getvalue()


def test_field_log():
    import field_log
    session = field_log.Session("survey_test", tempfile.mkdtemp())
    for line in "".join(LOGS).splitlines():
        session.fob_line(time.time(), line)
    text = "\n".join(session._extra_lines())
    check("field logger counts SURVEY_POINT lines", len(session.survey_points) >= 8, len(session.survey_points))
    check("field logger summary has the survey points", "Survey points:" in text and "stored" in text, text[-300:])
    check("survey points are not counted as alerts", all(session.fob[c]["msg"]["type"] != "SURVEY" for c in session.fob))


def setup(config=None, workdir=None, wifi_ok=True, gps_fix=False, entries=None):
    values = {"SURVEY_MODE": True}
    values.update(config or {})
    main = fakeboard.load_fob(values, workdir=workdir or tempfile.mkdtemp())
    fob = main.Fob()
    fob.help = None
    rec = Recorder()
    rec.wifi_ok = wifi_ok
    main.wifi_send = rec.wifi_send
    main.lora_send_confirmed = rec.lora_send
    main._bme = FakeBme()
    main._gps = FakeGps(gps_fix)
    sta = FakeSta(scan_entries() if entries is None else entries)
    main._sta = lambda: sta
    shows = []
    real_show = fob.led.show
    fob.led.show = lambda color, on_ms=0, off_ms=0, duration_ms=0: (
        shows.append((color, on_ms, off_ms, duration_ms)) or real_show(color, on_ms, off_ms, duration_ms))
    return main, fob, rec, shows, sta


SINGLE = [(0, 100), (1, 800)]
DOUBLE = [(0, 100), (1, 100), (0, 100), (1, 3000)]


# ---------- 6. ap_list ----------
def test_ap_list():
    aps = survey.ap_list(scan_entries())
    check("at most 15 access points", len(aps) == 15, len(aps))
    check("strongest first", [a[1] for a in aps] == sorted([a[1] for a in aps], reverse=True), aps[:3])
    check("one per BSSID, its strongest reading", sum(1 for a in aps if a[0] == "102030405005") == 1
          and aps[0] == ["102030405005", -30, 6, "5363686f6f6c2d30"], aps[0])
    check("a bad BSSID is skipped", all(len(a[0]) == 12 for a in aps))
    check("SSID as lowercase hex", aps[1][3] == "School-0".encode().hex(), aps[1])
    long = survey.ap_list(scan_entries(long_ssid=True))
    check("an SSID over 32 bytes is cut to 32 (64 hex)",
          all(len(a[3]) <= 64 for a in long) and sum(1 for a in long if len(a[3]) == 64) == 14, long[:2])
    check("an empty scan gives an empty list", survey.ap_list([]) == [])
    check("rssi and channel clamped to the format's range",
          survey.ap_list([(b"a", b"\x00" * 6, 300, 20, 0, 0)]) == [["000000000000", 0, 255, "61"]])


# ---------- 1 to 5. the Fob ----------
def test_fob():
    work = tempfile.mkdtemp()
    main, fob, rec, shows, sta = setup(workdir=work, gps_fix=True)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fob.survey_boot()
    log = out.getvalue()
    check("boot: long blue blink in survey mode", (main.BLUE, 0, 0, 2000) in shows, shows)
    check("boot: survey mode line", "SURVEY_MODE on: 1 press = survey point" in log, log)
    check("survey store folder made", os.path.isdir(os.path.join(work, "survey_q")))

    shows.clear()
    log = run(fob, SINGLE)
    check("one press: one WiFi send", len(rec.sent) == 1, log)
    topic, payload = rec.sent[0]
    msg = json.loads(payload)
    check("sent to safeping/survey/<id>", topic == "safeping/survey/FOB-T", topic)
    check("type SURVEY, never STATUS", msg["type"] == "SURVEY")
    check("15 pressure readings", msg["n"] == 15, msg)
    check("pressure to one decimal (98760.2 and 98760.4)", msg["pd"] in (987602, 987603, 987604), msg)
    check("p is pd rounded", msg["p"] == (msg["pd"] + 5) // 10)
    check("temperature", msg["t"] == 2210)
    check("GPS fix info with a position", msg["fix"] == 1 and msg["sats"] == 7 and msg["lat"] == 34725549
          and "acc" in msg, msg)
    check("WiFi scan: 15 strongest", len(msg["aps"]) == 15 and msg["aps"][0][1] == -30)
    check("signature by the Fob's own code", msg["sig"] == main.sign({k: v for k, v in msg.items() if k != "sig"}))
    check("never over LoRa", rec.lora == [])
    check("SURVEY_POINT line", "SURVEY_POINT n=1 ctr={} p=".format(msg["ctr"]) in log and " sats=7 aps=15 sent=wifi" in log, log)
    check("full point in the log (SURVEY_MSG)", "SURVEY_MSG {" in log)
    check("no SAFEPING_MSG line (not an alert)", "SAFEPING_MSG" not in log)
    check("two short green blinks", (main.GREEN, 150, 150, 600) in shows, shows)
    check("the press record is cleared (never resent as an alert)", fob.rec.stage is None, fob.rec.stage)
    check("back to idle", fob.state == main.IDLE)
    points = [payload]

    # ---- two presses: still a normal alert ----
    log = run(fob, DOUBLE)
    alert = json.loads(rec.sent[-1][1])
    check("two presses: a SUSPICIOUS alert on the alert topic", alert["type"] == "SUSPICIOUS" and rec.sent[-1][0] is None, log)
    run(fob, [(1, 3500)])                          # the 3 s lockout after an alert

    # ---- no WiFi: kept in flash ----
    rec.wifi_ok = False
    shows.clear()
    log = run(fob, SINGLE)
    stored = json.loads(rec.sent[-1][1])
    path = os.path.join(work, "survey_q", "{}.json".format(stored["ctr"]))
    check("no WiFi: point kept in survey_q/<ctr>.json", os.path.isfile(path), log)
    with open(path) as f:
        check("the file is the signed message", f.read() == rec.sent[-1][1])
    check("SURVEY_POINT says stored", "sent=stored" in log, log)
    check("stored also gives two short green blinks", (main.GREEN, 150, 150, 600) in shows, shows)
    check("still never LoRa", rec.lora == [])
    points.append(rec.sent[-1][1])
    log = run(fob, SINGLE)
    second = json.loads(rec.sent[-1][1])
    points.append(rec.sent[-1][1])
    check("two points waiting", len(fob.survey_store) == 2)

    # ---- a restart keeps them; a .tmp from a crash is removed ----
    with open(os.path.join(work, "survey_q", "999.json.tmp"), "w") as f:
        f.write('{"half')
    main2, fob2, rec2, shows2, _ = setup(workdir=work)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fob2.survey_boot()
    check("after a restart both points are still waiting", fob2.survey_store.ctrs == [stored["ctr"], second["ctr"]],
          fob2.survey_store.ctrs)
    check("a .tmp left by a crash is removed", not os.path.exists(os.path.join(work, "survey_q", "999.json.tmp")))

    # ---- sent later, oldest first, while idle and WiFi is up ----
    main2.wifi_connected = lambda: True
    fob2.queue.add(900, "MEDICAL", '{"ctr": 900}', "s", None)
    fob2.queue.entries[0]["next"] = fakeboard.clock[0] + 10 ** 9      # not due: just waiting
    log = run(fob2, [(1, 1000)])
    check("alerts waiting in the retry queue go first (no survey send)", rec2.sent == [], rec2.sent)
    fob2.queue.entries.clear()

    def press_during(payload, ctr, sig, budget, service=None, keep_open=None, stop=None, topic=None):
        rec2.sent.append((topic, payload))
        fakeboard.button.level = 0                 # the wearer presses during the send
        return False, "wifi_join_failed", False, None
    main2.wifi_send = press_during
    fob2.next_survey_flush = 0
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fob2.survey_flush()
    fakeboard.button.level = 1
    check("a press stops the send, the point stays",
          "SURVEY_SEND_STOPPED ctr={} reason=button".format(stored["ctr"]) in out.getvalue()
          and len(fob2.survey_store) == 2, out.getvalue())
    main2.wifi_send = rec2.wifi_send
    rec2.sent.clear()
    fob2.next_survey_flush = 0
    log = run(fob2, [(1, 3000)])
    order = [json.loads(p)["ctr"] for _, p in rec2.sent]
    check("sent later, oldest first", order == [stored["ctr"], second["ctr"]], order)
    check("SURVEY_SENT lines", log.count("SURVEY_SENT ctr=") == 2, log)
    check("files removed once the server confirmed", os.listdir(os.path.join(work, "survey_q")) == [],
          os.listdir(os.path.join(work, "survey_q")))
    check("sent to the survey topic", all(t == "safeping/survey/FOB-T" for t, _ in rec2.sent))

    # ---- a full store: orange, not kept ----
    rec.wifi_ok = False
    fob.survey_store.max = len(fob.survey_store)
    shows.clear()
    log = run(fob, SINGLE)
    check("full store: SURVEY_POINT says full", "sent=full" in log, log)
    check("full store: orange", any(s[0] == main.ORANGE for s in shows), shows)
    rec.wifi_ok = True

    # ---- survey mode off: a press is a STATUS alert ----
    main3, fob3, rec3, _, sta3 = setup({"SURVEY_MODE": False})
    run(fob3, SINGLE)
    check("survey mode off: one press is a STATUS alert",
          len(rec3.sent) == 1 and json.loads(rec3.sent[0][1])["type"] == "STATUS" and sta3.scans == 0)

    # ---- calibration: points by themselves ----
    main4, fob4, rec4, _, _ = setup({"SURVEY_AUTO_MS": 30000})
    with contextlib.redirect_stdout(io.StringIO()):
        fob4.survey_boot()
    log = run(fob4, [(1, 95000)])
    check("SURVEY_AUTO_MS: a point every 30 s by itself", len(rec4.sent) == 3 and log.count("auto=1") == 3, len(rec4.sent))

    # ---- no GPS fix, no sensor ----
    main5, fob5, rec5, _, _ = setup({"DEVICE_ID": "FOB-U"}, gps_fix=False)   # own id: its counter starts at 0
    main5._bme = None
    run(fob5, SINGLE)
    m5 = json.loads(rec5.sent[0][1])
    check("no fix: fix 0, satellites, no position", m5["fix"] == 0 and m5["sats"] == 2 and "lat" not in m5, m5)
    check("no sensor: n 0 and no pd", m5["n"] == 0 and "pd" not in m5 and "p" not in m5, m5)
    points.append(rec5.sent[0][1])

    # ---- the biggest point fits ----
    main6, fob6, rec6, _, _ = setup({"DEVICE_ID": "FOB-V"}, gps_fix=True, entries=scan_entries(long_ssid=True))
    run(fob6, SINGLE)
    big = rec6.sent[0][1]
    check("biggest point (15 APs, 32-byte SSIDs) under 2048 bytes", len(big) <= 2048, len(big))
    points.append(big)
    return points


# ---------- 7 to 10. the server ----------
def test_server(points):
    sys.path.insert(0, SERVER)
    os.environ["SAFEPING_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
    for name in ("config", "db", "validate", "processor", "refmatch", "location", "app", "stats", "pushover"):
        sys.modules.pop(name, None)
    import db
    import processor
    import validate
    db.init_db()
    db.add_device("FOB-T", "FOB", "Survey Walker", KEY)
    db.add_device("FOB-U", "FOB", "Survey Walker U", KEY)
    db.add_device("FOB-V", "FOB", "Survey Walker V", KEY)
    db.add_device("REF-T", "REF", None, "e" * 32)
    pushes = []
    processor.pushover.send = lambda *a, **k: pushes.append(a)
    texts = []
    processor.textbelt.send = lambda *a, **k: texts.append(a)

    first = json.loads(points[0])
    check("Fob and server build the same SURVEY signing string",
          validate.signing_string(first) == msgsign.signing_string(first), validate.signing_string(first)[:120])
    now = time.time()
    # a reference reading 10 s before and 20 s after the first point
    t0 = first.get("ts") or int(now)
    db.insert_reference(now, 98750, 2100, "REF-T", t0 - 10, 987500, 15, "ref-x")
    db.insert_reference(now, 98753, 2100, "REF-T", t0 + 20, 987530, 15, "ref-x")
    acks = []
    r = processor.process(points[0], now=now, source="wifi", on_ack=lambda *a: acks.append(a))
    check("server accepts the survey point", r.get("ok") and r.get("kind") == "survey", r)
    check("acked like an alert", acks == [("FOB-T", first["ctr"], first["sig"])], acks)
    check("reference at the point's time stored (interpolated)", r.get("matched_reference"), r)
    with db.connect() as c:
        row = dict(c.execute("SELECT * FROM survey_points WHERE counter = ?", (first["ctr"],)).fetchone())
        alerts = c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    check("stored with pressure, GPS and APs", row["pressure_dpa"] == first["pd"] and row["gps_fix"] == 1
          and len(json.loads(row["aps"])) == 15, row)
    check("reference pressure interpolated to one decimal", abs(row["ref_pressure"] - 98751.0) < 0.05, row["ref_pressure"])
    check("never stored as an alert", alerts == 0, alerts)
    check("never Pushover, never a text", pushes == [] and texts == [])

    others = [json.loads(p) for p in points[1:]]
    for p in points[1:]:
        r = processor.process(p, now=now + 1, source="wifi")
        check("point ctr {} accepted".format(json.loads(p)["ctr"]), r.get("ok") and r["kind"] == "survey", r)

    # ---- no window for survey points ----
    high = {"v": 1, "id": "FOB-T", "type": "STATUS", "ctr": 5000}
    high["sig"] = validate.sign(KEY, high)
    processor.process(json.dumps(high), now=now + 2)
    late = dict(others[0], ctr=100)
    late.pop("sig")
    late["sig"] = msgsign.sign(KEY, late)
    r = processor.process(json.dumps(late), now=now + 3)
    check("a point far below the newest counter is still accepted (no window)", r.get("ok"), r)
    acks = []
    r = processor.process(json.dumps(late), now=now + 4, on_ack=lambda *a: acks.append(a))
    check("the same point again: duplicate, acked again", r == {"ok": False, "reason": "duplicate"} and len(acks) == 1, r)
    other_sig = dict(late, sats=9)
    other_sig.pop("sig")
    other_sig["sig"] = msgsign.sign(KEY, other_sig)
    r = processor.process(json.dumps(other_sig), now=now + 5)
    check("same counter, another signature: replay", r == {"ok": False, "reason": "replay"}, r)
    old_alert = {"v": 1, "id": "FOB-T", "type": "STATUS", "ctr": 101}
    old_alert["sig"] = validate.sign(KEY, old_alert)
    r = processor.process(json.dumps(old_alert), now=now + 6)
    check("an alert that far below is still a replay (window unchanged)", r == {"ok": False, "reason": "replay"}, r)

    # ---- bad points ----
    def resigned(**changes):
        m = dict(first, ctr=first["ctr"] + 7000 + len(changes), **changes)
        m.pop("sig")
        for k in [k for k, v in m.items() if v is None]:
            m.pop(k)
        m["sig"] = msgsign.sign(KEY, m)
        return json.dumps(m)
    cases = [
        ("uppercase BSSID", resigned(aps=[["A1B2C3D4E5F6", -50, 6, ""]])),
        ("odd-length SSID hex", resigned(aps=[["a1b2c3d4e5f6", -50, 6, "abc"]])),
        ("positive RSSI", resigned(aps=[["a1b2c3d4e5f6", 5, 6, ""]])),
        ("16 access points", resigned(aps=[["a1b2c3d4e5f6", -50, 6, ""]] * 16)),
        ("fix 1 without a position", resigned(lat=None, lon=None, acc=None)),
        ("a position with fix 0", resigned(fix=0)),
        ("p and pd differ", resigned(p=98000)),
        ("aps missing", resigned(aps=None)),
    ]
    for name, payload in cases:
        r = processor.process(payload, now=now + 7)
        check("rejected: " + name, r == {"ok": False, "reason": "bad_format"}, r)
    big_alert = {"v": 1, "id": "FOB-T", "type": "STATUS", "ctr": 6000, "pad": "x" * 600}
    big_alert["sig"] = validate.sign(KEY, big_alert)
    r = processor.process(json.dumps(big_alert), now=now + 8)
    check("an alert over 512 bytes is still rejected", r == {"ok": False, "reason": "bad_json"}, r)
    huge = dict(first, ctr=6001, aps=[["a1b2c3d4e5f6", -50, 6, "61" * 32]] * 15, pad="x" * 1200)
    r = processor.process(json.dumps(huge), now=now + 9)
    check("a SURVEY over 2048 bytes is rejected", r == {"ok": False, "reason": "bad_json"}, r)
    db.add_device("REF-Z", "REF", None, KEY)
    as_ref = dict(first, id="REF-Z")
    as_ref.pop("sig")
    as_ref["sig"] = msgsign.sign(KEY, as_ref)
    r = processor.process(json.dumps(as_ref), now=now + 10)
    check("a Reference board cannot send SURVEY", r == {"ok": False, "reason": "wrong_role"}, r)

    # ---- the API ----
    import app
    client = app.app.test_client()
    data = client.get("/api/survey?start={}&end={}".format(now - 60, now + 60)).get_json()
    pts = data["points"]
    check("/api/survey lists the points", len(pts) >= len(points), len(pts))
    p0 = [p for p in pts if p["counter"] == first["ctr"]][0]
    check("/api/survey: SSIDs as text, pressure in Pa", p0["aps"][0]["ssid"] == "School-0"
          and abs(p0["pressure"] - first["pd"] / 10) < 0.01 and p0["ref_pressure"] is not None, p0["aps"][0])
    alerts = client.get("/api/alerts?status=1&resolved=1").get_json()["alerts"]
    check("survey points never on Live (/api/alerts has only the STATUS alert)",
          all(a["alert_type"] != "SURVEY" for a in alerts) and len(alerts) == 1, len(alerts))


def main():
    test_ap_list()
    points = test_fob()
    test_field_log()
    test_server(points)
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
