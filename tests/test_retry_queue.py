"""Laptop test of the Fob's retry queue (Part C) and the button edge log.

  1. retryq.py rules: full queue, drop order, give up after 10 minutes, try spacing
  2. retryq.py in flash: reboot resume, power cut in the middle of a write
  3. presslog.py: presses during a slow call are not lost, and keep their timing
  4. the real main.py (fake board): an unconfirmed alert is queued, a retry gets through
     with the right buzz (none for SILENT), and a press during a retry stops it at once

  python tests/test_retry_queue.py"""
import contextlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard     # noqa: E402  (puts firmware/lib and firmware/fob on the path, patches time)

fakeboard._patch_time()
import presslog      # noqa: E402
import retryq        # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    if passed and "\n" in detail:
        detail = ""                      # a whole log: only shown when the check fails
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


class MemFiles:
    """Fake flash. crash_on_write=True writes half the text and then "loses power"."""

    def __init__(self):
        self.data = {}
        self.crash_on_write = False

    def read(self, name):
        return self.data.get(name)

    def write(self, name, text):
        if self.crash_on_write:
            self.data[name] = text[: len(text) // 2]
            raise OSError("power cut")
        self.data[name] = text

    def replace(self, src, dst):
        self.data[dst] = self.data.pop(src)


def make_queue(clock, files=None):
    return retryq.RetryQueue("queue.json", 5, 30000, 600000, clock=lambda: clock[0],
                             diff=lambda a, b: a - b, add=lambda a, b: a + b, files=files or MemFiles())


def add(q, ctr, kind, clock):
    return q.add(ctr, kind, '{"ctr":%d}' % ctr, "s%d" % ctr, wall=None, now=clock[0])


def kinds(q):
    return [(e["ctr"], e["kind"]) for e in q.entries]


# ---------- 1. rules ----------
def test_rules():
    clock = [0]
    q = make_queue(clock)
    for i, kind in enumerate(["SUSPICIOUS", "STATUS", "MEDICAL", "SILENT", "STATUS"]):
        clock[0] += 1000
        add(q, 10 + i, kind, clock)
    check("queue holds 5", len(q) == 5)
    check("same ctr is not queued twice", add(q, 10, "SUSPICIOUS", clock) == (False, None))

    queued, dropped = add(q, 20, "SUSPICIOUS", clock)
    check("full: the oldest STATUS is dropped first", queued and dropped["ctr"] == 11, str(kinds(q)))
    queued, dropped = add(q, 21, "SILENT", clock)
    check("full: then the other STATUS", queued and dropped["ctr"] == 14, str(kinds(q)))
    queued, dropped = add(q, 22, "MEDICAL", clock)
    check("full, no STATUS left: the oldest SUSPICIOUS", queued and dropped["ctr"] == 10, str(kinds(q)))
    queued, dropped = add(q, 23, "MEDICAL", clock)
    check("then the next SUSPICIOUS", queued and dropped["ctr"] == 20, str(kinds(q)))
    queued, dropped = add(q, 24, "MEDICAL", clock)
    check("then the oldest SILENT", queued and dropped["ctr"] == 13, str(kinds(q)))
    check("now: one SILENT and four MEDICAL",
          sorted(k for _, k in kinds(q)) == ["MEDICAL"] * 4 + ["SILENT"], str(kinds(q)))
    queued, dropped = add(q, 25, "SUSPICIOUS", clock)
    check("a new SUSPICIOUS never pushes out a SILENT or MEDICAL (it is not queued)",
          not queued and dropped["ctr"] == 25 and 25 not in [c for c, _ in kinds(q)], str(kinds(q)))
    queued, dropped = add(q, 26, "SILENT", clock)
    check("a new SILENT replaces the older SILENT", queued and dropped["ctr"] == 21, str(kinds(q)))
    queued, dropped = add(q, 27, "MEDICAL", clock)
    check("a new MEDICAL pushes out the SILENT before any MEDICAL", queued and dropped["ctr"] == 26)
    check("all MEDICAL now", all(k == "MEDICAL" for _, k in kinds(q)), str(kinds(q)))
    queued, dropped = add(q, 28, "SILENT", clock)
    check("all MEDICAL: a new SILENT is not queued, no MEDICAL dropped", not queued and dropped["ctr"] == 28)
    oldest = q.entries[0]["ctr"]
    queued, dropped = add(q, 29, "MEDICAL", clock)
    check("all MEDICAL: a new MEDICAL drops the oldest MEDICAL", queued and dropped["ctr"] == oldest,
          "dropped {} oldest {}".format(dropped["ctr"], oldest))

    # timing: due every 30 s, highest type first, give up after 10 minutes
    clock = [0]
    q = make_queue(clock)
    add(q, 1, "SUSPICIOUS", clock)
    clock[0] = 5000
    add(q, 2, "MEDICAL", clock)
    clock[0] = 29999
    check("nothing due before 30 s", q.next_due() is None)
    clock[0] = 35000
    e = q.next_due()
    check("both due: MEDICAL is tried first", e is not None and e["ctr"] == 2)
    q.tried(e)
    check("after a failed try: next one 30 s later", e["next"] == 65000 and e["tries"] == 1)
    e = q.next_due()
    check("then the SUSPICIOUS", e["ctr"] == 1)
    q.stopped(e)
    check("a stopped try does not count", e["tries"] == 0 and e["next"] == 35000 + retryq.STOPPED_RETRY_MS)
    clock[0] = 599999
    check("not given up before 10 minutes", q.expired() == [])
    clock[0] = 600000
    gone = q.expired()
    check("given up after 10 minutes", [g["ctr"] for g in gone] == [1] and len(q) == 1)
    check("an expired entry is never due", q.next_due(604999 + 1000) is None or q.next_due()["ctr"] == 2)
    q.done(q.entries[0])
    check("done removes it", len(q) == 0)

    line = retryq.line("RETRY_TRY", ctr=5, kind="MEDICAL", try_no=2, age_s=61)
    check("log line format", line == "RETRY_TRY ctr=5 kind=MEDICAL try=2 age_s=61", line)


# ---------- 2. flash ----------
def test_flash():
    clock = [1000]
    files = MemFiles()
    q = make_queue(clock, files)
    add(q, 40, "MEDICAL", clock)
    q.entries[0]["wall"] = 1762800000
    clock[0] += 120000
    add(q, 41, "SILENT", clock)
    clock[0] += 60000                        # 40 is now 180 s old, 41 is 60 s old
    q.save()
    saved = json.loads(files.data["queue.json"])
    check("saved to flash with the age of each entry",
          [e["age_ms"] for e in saved["entries"]] == [180000, 60000], str(saved))
    check("no .tmp file left after a good save", "queue.json.tmp" not in files.data)

    # reboot: ticks start again from a new number
    clock[0] = 5
    q2 = make_queue(clock, files)
    resumed, gave_up = q2.load(unix_now=None)
    check("reboot: both resumed", [e["ctr"] for e in resumed] == [40, 41] and gave_up == [])
    check("reboot: age kept from the saved value", q2.age_ms(q2.entries[0]) == 180000, str(q2.age_ms(q2.entries[0])))
    check("reboot: tried right away", q2.next_due()["ctr"] == 40)

    q3 = make_queue(clock, files)
    resumed, gave_up = q3.load(unix_now=1762800000 + 700)    # clock set: 40 was pressed 700 s ago
    check("reboot with the clock set: an alert pressed 700 s ago is given up",
          [e["ctr"] for e in gave_up] == [40] and [e["ctr"] for e in resumed] == [41])

    # power cut in the middle of a write: the old queue is still there
    q2.entries[0]["tries"] = 7
    files.crash_on_write = True
    try:
        q2.save()
    except OSError:
        pass
    files.crash_on_write = False
    check("power cut: .tmp is half written", files.data["queue.json.tmp"].count("{") != files.data["queue.json.tmp"].count("}"))
    q4 = make_queue(clock, files)
    resumed, _ = q4.load()
    check("power cut: the old queue loads in full", [e["ctr"] for e in resumed] == [40, 41]
          and resumed[0]["tries"] == 0)

    # power cut after the .tmp was complete but before the rename
    files.data["queue.json.tmp"] = json.dumps({"v": 1, "entries": [
        {"ctr": 42, "kind": "MEDICAL", "payload": "{}", "sig": "x", "wall": None, "age_ms": 1000, "tries": 0}]})
    resumed, _ = make_queue(clock, files).load()
    check("a complete .tmp (newer) wins", [e["ctr"] for e in resumed] == [42])

    files.data = {"queue.json": "not json at all"}
    resumed, gave_up = make_queue(clock, files).load()
    check("a damaged file gives an empty queue, no crash", resumed == [] and gave_up == [])
    files.data = {}
    check("no file: empty queue", make_queue(clock, files).load() == ([], []))

    # real files on the laptop: save, then load
    d = tempfile.mkdtemp()
    real = retryq.RetryQueue(os.path.join(d, "queue.json"))
    real.add(50, "MEDICAL", "{}", "sig", None)
    real.save()
    again = retryq.RetryQueue(os.path.join(d, "queue.json"))
    check("real file: save then load", [e["ctr"] for e in again.load()[0]] == [50])
    real.save()
    check("real file: saving twice replaces the file", sorted(os.listdir(d)) == ["queue.json"], str(os.listdir(d)))


# ---------- 3. presslog ----------
def feed(log, deb, now, pin_pressed):
    return deb.feed(log.take(), now, pin_pressed)


def test_presslog():
    log = presslog.EdgeLog(size=16)
    deb = presslog.Debouncer(30, diff=lambda a, b: a - b)
    # a double tap with contact bounce, all while the loop was blocked for 2 s
    t = 1000
    for dt, level in [(0, 0), (2, 1), (3, 0), (120, 1), (121, 0), (123, 1),
                      (300, 0), (302, 1), (304, 0), (420, 1)]:
        log.add(t + dt, level)
    events = feed(log, deb, 3000, False)
    check("blocked loop: double tap seen as 2 presses and 2 releases",
          [p for _, p in events] == [True, False, True, False], str(events))
    check("blocked loop: real press times kept", [e[0] for e in events] == [1003, 1123, 1304, 1420], str(events))

    # no interrupts: reads the pin like the old loop (needs 30 ms steady)
    deb = presslog.Debouncer(30, diff=lambda a, b: a - b)
    out = []
    for now, pin in [(0, True), (10, False), (20, True), (40, True), (55, True), (100, False), (140, False)]:
        out += deb.feed([], now, pin)
    check("polling: a 10 ms blip is ignored, then press and release",
          out == [(20, True), (100, False)], str(out))

    # a full buffer keeps the newest edges and counts the lost ones
    log = presslog.EdgeLog(size=4)
    for i in range(6):
        log.add(i, i % 2)
    edges = log.take()
    check("full buffer: newest 4 kept, 2 counted as lost", len(edges) == 4 and log.lost == 2 and edges[0][0] == 2)
    check("nothing pending after take", not log.pending())


# ---------- 4. the real main.py ----------
class Calls:
    def __init__(self):
        self.wifi = []
        self.lora = []


def fob_setup(workdir=None):
    main = fakeboard.load_fob(workdir=workdir)
    fob = main.Fob()
    fob.help = None
    return main, fob


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


def fail_everything(main, calls):
    def wifi_send(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
        calls.wifi.append(ctr)
        return False, "wifi_join_failed", False, None

    def lora(payload, ctr, sig, stop=None):
        calls.lora.append(ctr)
        return "unconfirmed"
    main.wifi_send = wifi_send
    main.lora_send_confirmed = lora
    main.wifi_quiet = lambda for_lora=False: None


def run_until_idle(fob, ms=100):
    for _ in range(ms // 10):
        fakeboard.clock[0] += 10
        fob.step(fakeboard.clock[0])


def test_main():
    workdir = tempfile.mkdtemp()
    main, fob = fob_setup(workdir)
    calls = Calls()
    fail_everything(main, calls)
    fob.state = main.IDLE
    ok, log = quiet(fob.send, "MEDICAL")
    check("main: not confirmed on both paths", ok is False and "result=not_confirmed" in log)
    check("main: RETRY_QUEUED printed", "RETRY_QUEUED ctr=0 kind=MEDICAL reason=wifi_join_failed queue=1" in log, log)
    check("main: queue.json written", os.path.isfile(os.path.join(workdir, "queue.json")))

    # nothing is tried before 30 s
    fob.state = main.IDLE
    fakeboard.clock[0] += 20000
    quiet(fob.run_retries)
    check("main: no retry before RETRY_EVERY_MS", calls.wifi == [0], str(calls.wifi))

    # a retry that fails again: same message, try 1
    fakeboard.clock[0] += 10001
    sent = []

    def wifi_spy(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
        sent.append(payload)
        return False, "no_server_ack", True, None
    main.wifi_send = wifi_spy
    _, log = quiet(fob.run_retries)
    first_payload = json.loads(open(os.path.join(workdir, "queue.json")).read())["entries"][0]["payload"]
    check("main: retry sends the exact same signed message", sent == [first_payload], str(sent))
    check("main: RETRY_TRY and SEND_RESULT try=1", "RETRY_TRY ctr=0 kind=MEDICAL try=1" in log
          and "SEND_RESULT ctr=0 kind=MEDICAL path=lora result=not_confirmed" in log and "try=1" in log, log)
    check("main: counter not used again by a retry", open(os.path.join(workdir, "counter.txt")).read() == "0")

    # a retry that gets through: RETRY_DONE and the normal confirm buzz
    fakeboard.clock[0] += 30001
    main.lora_send_confirmed = lambda payload, ctr, sig, stop=None: "confirmed"
    fob.motor.stop()
    _, log = quiet(fob.run_retries)
    check("main: RETRY_DONE", "RETRY_DONE ctr=0 kind=MEDICAL try=2 path=lora" in log, log)
    check("main: confirm buzz played for MEDICAL", fob.motor.busy(), str(fob.motor.queue))
    check("main: queue empty after done", len(fob.queue) == 0)

    # SILENT: queued, then confirmed by a retry: no buzz and no light
    fail_everything(main, calls)
    quiet(fob.send, "SILENT")
    fob.motor.stop()
    fob.led.off()
    fakeboard.clock[0] += 30001
    main.lora_send_confirmed = lambda payload, ctr, sig, stop=None: "confirmed"
    _, log = quiet(fob.run_retries)
    check("main: SILENT retry confirmed", "RETRY_DONE ctr=1 kind=SILENT" in log, log)
    check("main: SILENT retry: no buzz", not fob.motor.busy(), str(fob.motor.queue))
    check("main: SILENT retry: no light", fob.led.color == main.OFF)

    # gives up after 10 minutes
    fail_everything(main, calls)
    quiet(fob.send, "SUSPICIOUS")
    fakeboard.clock[0] += 600001
    _, log = quiet(fob.run_retries)
    check("main: RETRY_GAVE_UP after 10 minutes", "RETRY_GAVE_UP ctr=2 kind=SUSPICIOUS try=0 reason=timeout" in log, log)

    # a press during a retry (WiFi join): stopped at once, press handled first
    fail_everything(main, calls)
    quiet(fob.send, "MEDICAL")
    fakeboard.clock[0] += 30001

    def wifi_pressed(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
        fakeboard.clock[0] += 300
        fakeboard.button.press()                  # the wearer presses during the join
        for _ in range(3):
            fakeboard.clock[0] += 20
            service(fakeboard.clock[0])          # wifi_wait calls this every 20 ms
        return False, "wifi_join_failed", False, None
    main.wifi_send = wifi_pressed
    lora_calls = []
    main.lora_send_confirmed = lambda *a, **k: lora_calls.append(1) or "confirmed"
    pressed_at = fakeboard.clock[0] + 300
    _, log = quiet(fob.run_retries)
    check("press during a retry: RETRY_STOPPED reason=button", "RETRY_STOPPED ctr=3 try=1 reason=button" in log, log)
    check("press during a retry: LoRa never started", lora_calls == [])
    check("press during a retry: still queued, try not counted",
          len(fob.queue) == 1 and fob.queue.entries[0]["tries"] == 0)
    stop_ms = fakeboard.clock[0] - pressed_at
    check("press during a retry: stopped within 50 ms of the press", stop_ms <= 50, "{} ms".format(stop_ms))
    fail_everything(main, calls)                     # back to the recording fakes
    fakeboard.clock[0] += 100
    fob.step(fakeboard.clock[0])
    check("press during a retry: the press is handled (state DOWN, real press time)",
          fob.state == main.DOWN and fob.press_start == pressed_at, "{} {}".format(fob.state, fob.press_start))
    fakeboard.button.release()
    run_until_idle(fob, 800)
    check("press during a retry: the tap becomes a STATUS press",
          calls.wifi[-1] == 4, str(calls.wifi))

    # a press during the LoRa ack wait of a retry: the real lora_send_confirmed
    main, fob = fob_setup(workdir)                  # reboot: the queue comes back
    _, log = quiet(fob.resume_queue)
    check("reboot: queued alerts resumed", "RETRY_QUEUED" in log and "resumed_after_reboot" in log, log)

    class Radio:
        def send(self, data):
            return True

        def receive(self, timeout_ms=1000, stop=None):
            for _ in range(timeout_ms // 2):
                fakeboard.clock[0] += 2
                if fakeboard.clock[0] % 1000 < 2:
                    fakeboard.button.press()
                if stop is not None and stop():
                    return None
            return None
    main._radio = Radio()
    main._lora_radio = lambda: main._radio
    main.wifi_send = lambda *a, **k: (False, "wifi_off", False, None)
    main.lora_send = lambda payload: True
    fakeboard.button.release()
    fob.btn.events(fakeboard.clock[0])
    fakeboard.clock[0] += 1000
    fob.btn.events(fakeboard.clock[0])
    entry = fob.queue.next_due()
    _, log = quiet(fob.run_retries)
    check("press during the LoRa ack wait: stopped", entry is not None and "RETRY_STOPPED" in log, log)

    # the upkeep problem: a double tap while NTP blocks for 2 s is a double tap
    main, fob = fob_setup()
    fob.state = main.IDLE
    t0 = fakeboard.clock[0]
    for dt, level in [(100, 0), (220, 1), (400, 0), (520, 1)]:
        fakeboard.clock[0] = t0 + dt
        fakeboard.button.set(level)
    fakeboard.clock[0] = t0 + 2000                 # the blocking call returns
    fob.step(fakeboard.clock[0])
    check("tap during a blocking call: double tap is SUSPICIOUS, not lost",
          fob.state == main.PENDING and fob.pending == "SUSPICIOUS", "{} {}".format(fob.state, fob.pending))


def taps(fob, pattern):
    """Drive the real step() every 10 ms. pattern: list of (button level, ms)."""
    for level, ms in pattern:
        fakeboard.button.set(level)
        for _ in range(ms // 10):
            fakeboard.clock[0] += 10
            quiet(fob.step, fakeboard.clock[0])


def test_patterns():
    """The press patterns still work after step() was split into events and timers."""
    main, fob = fob_setup()
    sent = []
    main.wifi_send = lambda payload, ctr, sig, budget, service=None, keep_open=None, stop=None: (
        sent.append(json.loads(payload)["type"]) or (True, "-", True, None))
    fob.state = main.IDLE
    taps(fob, [(0, 100), (1, 100), (0, 100), (1, 100), (0, 100), (1, 300)])
    check("3 presses: MEDICAL cancel window", fob.state == main.PENDING and fob.pending == "MEDICAL", fob.state)
    taps(fob, [(1, 2100)])
    check("MEDICAL sent after the 2 s window", sent == ["MEDICAL"], str(sent))
    taps(fob, [(1, 3500)])
    taps(fob, [(0, 2100), (1, 100)])
    check("hold 2 s: SILENT", sent[-1:] == ["SILENT"], str(sent))
    taps(fob, [(1, 3500)])
    taps(fob, [(0, 100), (1, 100), (0, 100), (1, 800)])
    check("2 presses: SUSPICIOUS cancel window", fob.state == main.PENDING and fob.pending == "SUSPICIOUS")
    taps(fob, [(0, 100), (1, 100)])
    check("a tap in the window cancels", fob.state == main.LOCKOUT and sent[-1:] == ["SILENT"], str(sent))
    taps(fob, [(1, 3500)])
    taps(fob, [(0, 100), (1, 100), (0, 100), (1, 100), (0, 100), (1, 100), (0, 100), (1, 2300)])
    check("MEDICAL: a 4th press right after the 3rd does not cancel", sent[-1:] == ["MEDICAL"], str(sent))


def main():
    test_rules()
    test_flash()
    test_presslog()
    test_main()
    test_patterns()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
