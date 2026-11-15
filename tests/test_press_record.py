"""Laptop test: a press is never lost when the Fob crashes, and a press cut off by a
restart is sent with "cut": 1 and the type its recorded presses give.

Why: on 2026-11-13 at 12:31:30 a press stopped a retry, the Fob saved queue.json and
crashed (cache error) inside that save. The press was only in RAM and was gone after
the reboot. pressrec.py now keeps it in RTC memory, which a crash reset does not clear.
Edwin's rule (2026-11-14) for a cut-off pattern: 3 or more presses MEDICAL, 2
SUSPICIOUS, a hold that started SILENT, 1 STATUS.

A "crash" is an exception nothing in main.py catches (like a panic), raised inside a
flash write, or simply the Fob stopping between two loops. The "reboot" loads main.py
again in the same folder with the fake RTC memory kept, and runs the boot steps that
matter (rec.load, resume_queue, boot_counter_jump, resume_press).

  1. pressrec.py on its own: stages, what may overwrite what, the cut rule, damaged data
  2. today's crash: press during a retry, crash in the queue save -> STATUS, cut=1
  3. cut-off patterns through the real step(): 1 tap, 2 taps, 2 taps + a 3rd down,
     a hold that started, a short press still down
  4. crash in the counter write after a MEDICAL was decided -> MEDICAL, cut=1
  5. crash in the queue save after a signed alert -> the same signed message, no cut
  6. normal cases leave no press behind: confirmed, queued, cancelled, a bounce
  7. a press that crashes every boot is dropped after 3 boots
  8. no RTC memory in the firmware: a warning, and the Fob still works
  9. the server: a Fob message with cut is accepted, stored and shown as cut_off;
     an edited cut is bad_signature; cut on a BOOT or cut=2 is bad_format

  python tests/test_press_record.py"""
import contextlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard                       # noqa: E402  (puts firmware/lib on the path)
import pressrec                        # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


class Crash(BaseException):
    """Like a Guru Meditation: nothing in main.py catches it."""


def quiet(fn, *args, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args, **kw)
    return value, out.getvalue()


def crashing(fn, *args):
    """Run fn until it 'crashes'. Returns (crashed, printed text)."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(*args)
    except Crash:
        return True, out.getvalue()
    return False, out.getvalue()


class MemStore:
    def __init__(self):
        self.data = b""

    def read(self):
        return self.data

    def write(self, data):
        self.data = bytes(data)


def rtc():
    """What the fake RTC memory holds: {"ctr", "press"} or None."""
    return pressrec.parse(fakeboard.rtc_memory[0])


def rtc_press():
    data = rtc()
    return None if data is None else data["press"]


# ---------- 1. pressrec.py on its own ----------
def test_unit():
    rec = pressrec.PressRecord(MemStore())
    check("empty memory: nothing found", rec.load() is None)
    rec.counter(41)
    rec.started(True)
    rec.tap(2)
    rec.started(True)                                 # still touched: must not wipe the 2 taps
    check("started() does not overwrite a tap count", pressrec.parse(rec.store.data)["press"]["taps"] == 2)
    rec.pressing(2)
    rec.hold()
    p = pressrec.parse(rec.store.data)["press"]
    check("pressing() then hold(): down and hold", p["down"] and p["hold"] and p["taps"] == 2, str(p))
    rec.kind("MEDICAL")
    rec.tap(1)
    rec.hold()
    check("tap() and hold() do not overwrite a decided kind", rec.stage == "kind")
    payload = json.dumps({"v": 1, "id": "FOB-T", "type": "MEDICAL", "ctr": 99999, "cut": 1, "x": "y" * 220})
    rec.signed("MEDICAL", 99999, payload, "a" * 64, None)
    rec.kind("STATUS")
    check("kind() does not overwrite a signed message", rec.stage == "signed")
    check("a 255 byte message fits in RTC memory (2048 bytes)", len(rec.store.data) < 2048,
          "{} bytes".format(len(rec.store.data)))
    rec.clear()
    data = pressrec.parse(rec.store.data)
    check("clear() forgets the press, keeps the counter copy", data == {"ctr": 41, "press": None}, str(data))

    rule = [((1, False, False), "STATUS"), ((2, False, False), "SUSPICIOUS"), ((3, False, False), "MEDICAL"),
            ((5, False, False), "MEDICAL"), ((0, True, True), "SILENT"), ((1, True, True), "SILENT"),
            ((2, True, True), "SUSPICIOUS"), ((0, True, False), "STATUS"), ((1, True, False), "SUSPICIOUS"),
            ((2, True, False), "MEDICAL"), ((0, False, False), "STATUS")]
    bad = [(args, want, pressrec.cut_kind(*args)) for args, want in rule if pressrec.cut_kind(*args) != want]
    check("cut rule: 3+ MEDICAL, 2 SUSPICIOUS, hold SILENT, 1 STATUS (a short press down counts)", bad == [], str(bad))

    for raw, name in [(b"\xff\x00garbage", "random bytes (power on)"), (b"SPP2{not json", "damaged JSON"),
                      (b'SPP2{"ctr": 1, "press": {"stage": "kind", "kind": "PANIC"}}', "unknown kind"),
                      (b'SPP2{"ctr": -5, "press": null}', "negative counter"),
                      (b'SPP1{"stage": "press", "taps": 1}', "old format")]:
        store = MemStore()
        store.data = raw
        r = pressrec.PressRecord(store)
        check("ignored and cleaned: " + name, r.load() is None and r.ctr is None
              and pressrec.parse(store.data) == {"ctr": None, "press": None}, str(store.data))

    off = pressrec.PressRecord(None)
    off.started(True)
    off.counter(5)
    off.signed("STATUS", 1, "{}", "s")
    off.clear()
    check("no store: every call does nothing", off.load() is None and not off.on())


# ---------- the Fob on the fake board ----------
def boot_fob(workdir):
    """Load main.py (the RTC memory is kept)."""
    main = fakeboard.load_fob(workdir=workdir)
    fob = main.Fob()
    fob.help = None
    fob.wait = lambda ms: None
    return main, fob


def fail_all(main, sent):
    def wifi(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
        sent.append(json.loads(payload))
        return False, "wifi_join_failed", False, None
    main.wifi_send = wifi
    main.lora_send_confirmed = lambda payload, ctr, sig, stop=None: "unconfirmed"
    main.wifi_quiet = lambda for_lora=False: None


def reboot(workdir):
    main, fob = boot_fob(workdir)
    sent = []
    fail_all(main, sent)

    def steps():
        fob.rec_found = fob.rec.load()
        fob.resume_queue()
        fob.boot_counter_jump()
        fob.resume_press(fob.rec_found)
    _, log = quiet(steps)
    return main, fob, sent, log


def crash_on_save(fob):
    def save(now=None):
        raise Crash()
    fob.queue.save = save


def counter_now(workdir):
    with open(os.path.join(workdir, "counter.txt")) as f:
        return int(f.read())


def drive(fob, pattern):
    """The real step() every 10 ms. pattern: list of (button level, ms)."""
    for level, ms in pattern:
        fakeboard.button.set(level)
        for _ in range(ms // 10):
            fakeboard.clock[0] += 10
            quiet(fob.step, fakeboard.clock[0])


# ---------- 2. today's crash ----------
def test_todays_crash():
    fakeboard.rtc_memory[0] = b""
    workdir = tempfile.mkdtemp()
    main, fob = boot_fob(workdir)
    sent = []
    fail_all(main, sent)
    fob.state = main.IDLE
    quiet(fob.send, "STATUS")                        # ctr 0 waits in the queue
    fakeboard.clock[0] += 30001

    def wifi_pressed(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
        fakeboard.clock[0] += 300
        fakeboard.button.press()                     # the press that stops the retry
        for _ in range(3):
            fakeboard.clock[0] += 20
            service(fakeboard.clock[0])
        return False, "clock_not_set", False, None
    main.wifi_send = wifi_pressed
    crash_on_save(fob)                               # the save after RETRY_STOPPED crashes
    crashed, log = crashing(fob.run_retries)
    check("today: RETRY_STOPPED, then a crash in the queue save",
          crashed and "RETRY_STOPPED ctr=0 try=1 reason=button" in log, log)
    p = rtc_press()
    check("today: the press (button down) was in RTC memory before the save",
          p is not None and p["stage"] == "press" and p["down"] and not p["hold"], str(p))
    last_ctr = counter_now(workdir)

    fakeboard.button.release()
    main, fob, sent, log = reboot(workdir)
    check("today: COUNTER_JUMP by 8 before the first send",
          "COUNTER_JUMP from={} to={}".format(last_ctr, last_ctr + 8) in log, log)
    check("today: PRESS_RESUMED kind=STATUS cut=1", "PRESS_RESUMED kind=STATUS stage=press" in log
          and "cut=1" in log, log)
    statuses = [m for m in sent if m["type"] == "STATUS"]
    check("today: one STATUS with cut=1 and counter after the jump",
          len(statuses) == 1 and statuses[0].get("cut") == 1 and statuses[0]["ctr"] == last_ctr + 9, str(sent))
    check("today: the cut STATUS signs with cut at the end",
          main.signing_string(statuses[0]).endswith("|1") if statuses else False)
    check("today: queued (no Relay), so the press is cleared", rtc_press() is None
          and any(e["ctr"] == last_ctr + 9 for e in fob.queue.entries))


# ---------- 3. cut-off patterns through the real step() ----------
def cut_after(pattern, label, want):
    fakeboard.rtc_memory[0] = b""
    workdir = tempfile.mkdtemp()
    main, fob = boot_fob(workdir)
    fail_all(main, [])
    fob.state = main.IDLE
    drive(fob, pattern)                              # then the Fob stops: the "crash"
    fakeboard.button.release()
    main, fob, sent, log = reboot(workdir)
    types = [(m["type"], m.get("cut")) for m in sent]
    check("cut off: {} -> {} with cut=1".format(label, want), types == [(want, 1)], "{} {}".format(types, log))


def test_patterns():
    cut_after([(0, 100), (1, 200)], "1 tap, crash in the 600 ms window", "STATUS")
    cut_after([(0, 100), (1, 100), (0, 100), (1, 200)], "2 taps, crash in the window", "SUSPICIOUS")
    cut_after([(0, 100), (1, 100), (0, 100), (1, 100), (0, 200)], "2 taps and a 3rd still down", "MEDICAL")
    cut_after([(0, 1200)], "a hold that started (1.2 s down)", "SILENT")
    cut_after([(0, 400)], "a short press still down (0.4 s)", "STATUS")
    cut_after([(0, 100), (1, 100), (0, 100), (1, 100), (0, 100), (1, 300)], "3 taps (cancel window)", "MEDICAL")


# ---------- 4. crash in the counter write, MEDICAL decided ----------
def test_crash_in_counter():
    fakeboard.rtc_memory[0] = b""
    workdir = tempfile.mkdtemp()
    main, fob = boot_fob(workdir)
    fail_all(main, [])
    fob.state = main.IDLE
    drive(fob, [(0, 100), (1, 100), (0, 100), (1, 100), (0, 100), (1, 400)])
    check("counter: MEDICAL cancel window", fob.state == main.PENDING and fob.pending == "MEDICAL", fob.state)

    def bad_write(n):
        raise Crash()
    main._counter.write = bad_write
    out = io.StringIO()
    crashed = False
    try:
        with contextlib.redirect_stdout(out):
            for _ in range(300):
                fakeboard.clock[0] += 10
                fob.step(fakeboard.clock[0])
    except Crash:
        crashed = True
    check("counter: crash in the counter write", crashed)
    check("counter: the RTC copy has the number that was being written", rtc()["ctr"] == 0, str(rtc()))
    main, fob, sent, log = reboot(workdir)
    check("counter: MEDICAL with cut=1 after the reboot",
          "PRESS_RESUMED kind=MEDICAL stage=kind" in log and [(m["type"], m.get("cut")) for m in sent] == [("MEDICAL", 1)], log)
    check("counter: the jump starts from the RTC copy (0), not the missing file",
          "COUNTER_JUMP from=0 to=8" in log and sent and sent[0]["ctr"] == 9, log)


# ---------- 5. crash in the queue save after the alert was signed ----------
def test_crash_after_signed():
    fakeboard.rtc_memory[0] = b""
    workdir = tempfile.mkdtemp()
    main, fob = boot_fob(workdir)
    sent = []
    fail_all(main, sent)
    crash_on_save(fob)
    fob.state = main.IDLE
    crashed, _ = crashing(fob.send, "SUSPICIOUS")
    check("signed: crash in the queue save after an unconfirmed send", crashed and len(sent) == 1)
    first = sent[0]
    main, fob, sent2, log = reboot(workdir)
    check("signed: PRESS_RESUMED with the same counter",
          "PRESS_RESUMED ctr={} kind=SUSPICIOUS stage=signed".format(first["ctr"]) in log, log)
    entry = [e for e in fob.queue.entries if e["ctr"] == first["ctr"]]
    check("signed: the same signed message (no cut) is in the queue, due now",
          len(entry) == 1 and json.loads(entry[0]["payload"]) == first and "cut" not in first
          and fob.queue.next_due() is entry[0], str(fob.queue.entries))
    check("signed: queue.json written, press cleared",
          os.path.isfile(os.path.join(workdir, "queue.json")) and rtc_press() is None)
    check("signed: counter jumped 8 past it", counter_now(workdir) == first["ctr"] + 8, str(counter_now(workdir)))


# ---------- 6. normal cases leave no press behind ----------
def test_normal():
    fakeboard.rtc_memory[0] = b""
    workdir = tempfile.mkdtemp()
    main, fob = boot_fob(workdir)
    main.wifi_send = lambda payload, ctr, sig, budget, service=None, keep_open=None, stop=None: (
        True, "-", True, None)
    fob.state = main.IDLE
    quiet(fob.send, "STATUS")
    check("normal: confirmed send leaves no press, counter copy kept",
          rtc_press() is None and rtc()["ctr"] == 0, str(rtc()))

    fail_all(main, [])
    fob.state = main.IDLE
    quiet(fob.send, "MEDICAL")
    check("normal: queued send leaves no press", rtc_press() is None)

    fob.state = main.IDLE
    drive(fob, [(0, 100), (1, 100), (0, 100), (1, 800), (0, 100), (1, 100)])
    check("normal: a cancelled SUSPICIOUS leaves no press", fob.state == main.LOCKOUT and rtc_press() is None, fob.state)

    drive(fob, [(1, 4000)])
    fakeboard.button.set(0)                          # a 5 ms bounce, shorter than the debounce
    fakeboard.clock[0] += 5
    fakeboard.button.set(1)
    quiet(fob.step, fakeboard.clock[0])
    seen = rtc_press() is not None
    drive(fob, [(1, 100)])
    check("normal: a bounce is written, then cleared when it is not a press",
          seen and rtc_press() is None and fob.state == main.IDLE, fob.state)
    check("normal: a cut-free alert has no cut field and signs as before",
          main.signing_string({"v": 1, "id": "X", "type": "STATUS", "ctr": 1}).count("|") == 10)


# ---------- 7. crash loop ----------
def test_crash_loop():
    workdir = tempfile.mkdtemp()
    store = MemStore()
    pressrec.PressRecord(store).kind("SILENT")
    fakeboard.rtc_memory[0] = store.data
    logs = []
    for _ in range(4):
        main, fob = boot_fob(workdir)
        _, log = quiet(lambda: setattr(fob, "rec_found", fob.rec.load()) or fob.resume_press(fob.rec_found))
        logs.append(log)
        if "PRESS_DROPPED" in log:
            break
        # the send "crashed" before it signed: the press is still the kind, with this boot counted
        fakeboard.rtc_memory[0] = (pressrec.MAGIC + json.dumps(
            {"ctr": None, "press": {"stage": "kind", "kind": "SILENT", "boots": fob.rec_found["boots"]}})).encode()
    check("crash loop: dropped on the 4th boot",
          len(logs) == 4 and "PRESS_DROPPED stage=kind boots=4" in logs[-1], logs[-1])
    check("crash loop: no press after the drop", rtc_press() is None)


# ---------- 8. no RTC memory ----------
def test_no_rtc():
    workdir = tempfile.mkdtemp()
    main = fakeboard.load_fob(workdir=workdir)

    class NoRTC:
        def memory(self, data=None):
            raise AttributeError("no memory")
    main.machine.RTC = NoRTC
    fob = main.Fob()
    check("no RTC: record off, Fob starts", not fob.rec.on() and fob.rec_error is not None)
    fob.help = None
    main.wifi_send = lambda payload, ctr, sig, budget, service=None, keep_open=None, stop=None: (
        True, "-", True, None)
    fob.state = main.IDLE
    ok, _ = quiet(fob.send, "STATUS")
    _, log = quiet(fob.boot_counter_jump)
    check("no RTC: sends and the counter jump still work", ok is True and "COUNTER_JUMP from=0 to=8" in log, log)


# ---------- 9. the server ----------
def test_server():
    fakeboard.rtc_memory[0] = b""
    main, fob = boot_fob(tempfile.mkdtemp())
    msg = main.build_message("SUSPICIOUS", cut=True)
    plain = main.build_message("SUSPICIOUS")

    server = os.path.join(HERE, "..", "server")
    sys.path.insert(0, server)
    os.environ["SAFEPING_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
    for name in ("config", "db", "validate", "processor", "app", "stats"):
        sys.modules.pop(name, None)
    import db
    import processor
    import validate
    db.init_db()
    db.add_device("FOB-T", "FOB", "Test Student", "f" * 32)      # the fake board's test key

    check("server and Fob build the same signing string with cut",
          validate.signing_string(msg) == main.signing_string(msg), validate.signing_string(msg))
    r, _ = quiet(processor.process, json.dumps(msg), source="lora")
    check("server accepts a Fob alert with cut=1 and says cut_off", r.get("ok") and r.get("cut_off") is True, str(r))
    r2, _ = quiet(processor.process, json.dumps(plain), source="lora")
    check("an alert without cut is accepted as before, cut_off False", r2.get("ok") and r2.get("cut_off") is False, str(r2))

    import app
    web = app.app.test_client()
    one = web.get("/api/alerts/{}".format(r["alert_id"])).get_json()
    one = one.get("alert", one)
    two = web.get("/api/alerts/{}".format(r2["alert_id"])).get_json()
    two = two.get("alert", two)
    check("API: cut_off true on the cut alert, false on the other",
          one.get("cut_off") is True and two.get("cut_off") is False, "{} {}".format(one.get("cut_off"), two.get("cut_off")))

    check("removing cut from a signed message is bad_signature",
          quiet(processor.process, json.dumps(dict(msg, cut=None)))[0]["reason"] == "bad_signature")
    added = dict(plain, ctr=plain["ctr"] + 7, cut=1)
    check("adding cut to a signed message is bad_signature",
          quiet(processor.process, json.dumps(added))[0]["reason"] == "bad_signature")
    two_val = dict(msg, cut=2, ctr=msg["ctr"] + 9)
    two_val["sig"] = validate.sign("f" * 32, two_val)
    check("cut=2 is bad_format", quiet(processor.process, json.dumps(two_val))[0]["reason"] == "bad_format")
    boot = {"v": 1, "id": "FOB-T", "type": "BOOT", "ctr": msg["ctr"] + 11, "fail": 0, "cut": 1}
    boot["sig"] = validate.sign("f" * 32, boot)
    check("cut on a BOOT is bad_format", quiet(processor.process, json.dumps(boot))[0]["reason"] == "bad_format")
    big = {"v": 1, "id": "FOB-001", "type": "SUSPICIOUS", "ctr": 2147483647, "ts": 1794595480,
           "lat": -34730123, "lon": -186586104, "acc": 100, "p": 101325, "t": -1234, "bat": 100,
           "cut": 1, "sig": "0" * 64}
    size = len(json.dumps(big))                      # MicroPython's json.dumps spacing
    check("largest alert with cut fits in one LoRa packet (255 bytes)", size <= 255, "{} bytes".format(size))


def main():
    test_unit()
    test_todays_crash()
    test_patterns()
    test_crash_in_counter()
    test_crash_after_signed()
    test_normal()
    test_crash_loop()
    test_no_rtc()
    test_server()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
