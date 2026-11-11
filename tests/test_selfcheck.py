"""Laptop test of the boot self-check and boot report (Part B).

  1. selfcheck.py: key and counter checks, the fail bits, the SELF_CHECK line
  2. the real main.py (fake board): what fails on a board with nothing attached, the
     red light, and a BOOT message signed by the Fob that the server accepts
  3. the server: BOOT is stored on the device, never as an alert, the newest 10 kept,
     same counter rule as alerts, and the Devices API shows it in plain words
  4. tests/field_log.py records the SELF_CHECK line

  python tests/test_selfcheck.py"""
import contextlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard       # noqa: E402

fakeboard._patch_time()
import selfcheck       # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


def test_rules():
    check("key: 32 hex characters is ok", selfcheck.key_ok("ab" * 16))
    check("key: the placeholder fails", not selfcheck.key_ok("paste-the-key-from-add_device.py"))
    check("key: too short fails", not selfcheck.key_ok("ab" * 8))
    check("key: not hex fails", not selfcheck.key_ok("zz" * 16))
    check("counter: a number is ok", selfcheck.counter_state("212\n") == "ok")
    check("counter: no file is new (brand new Fob), not a failure", selfcheck.counter_state(None) == "new")
    check("counter: damaged file fails", selfcheck.counter_state("21x") == "fail")

    all_ok = {"key": "ok", "counter": "ok", "lora": "ok", "gps": "ok", "battery": "ok", "pressure": "ok", "wifi": "fail"}
    check("no WiFi is not a failure", selfcheck.fail_mask(all_ok) == 0)
    check("new counter is not a failure", selfcheck.fail_mask(dict(all_ok, counter="new")) == 0)
    bad = dict(all_ok, lora="fail", gps="fail")
    check("LoRa and GPS failed: bits 4 and 8", selfcheck.fail_mask(bad) == 12)
    line = selfcheck.summary_line(dict(all_ok, wifi="ok"), "2026.11.11")
    check("SELF_CHECK line", line == "SELF_CHECK key=ok counter=ok lora=ok gps=ok battery=ok pressure=ok wifi=ok fw=2026.11.11", line)
    check("SELF_CHECK line parses", selfcheck.parse_line(line)["lora"] == "ok")


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


def test_main():
    main = fakeboard.load_fob(workdir=tempfile.mkdtemp())
    fob = main.Fob()
    results_, log = quiet(fob.self_check, False, fakeboard.clock[0], "fail")
    check("bare board: key ok (32 hex test key)", results_["key"] == "ok")
    check("bare board: counter new", results_["counter"] == "new")
    check("bare board: LoRa, GPS, battery, pressure fail",
          all(results_[k] == "fail" for k in ("lora", "gps", "battery", "pressure")), str(results_))
    start = fakeboard.clock[0]
    quiet(fob.show_check, results_)
    check("a failed check: steady red for 3 s", fakeboard.clock[0] - start >= 3000 and fob.led.color == main.OFF)

    sent = []

    def deliver(kind, payload, ctr, sig, budget=None, stop=None, try_no=None):
        sent.append(payload)
        return True, "confirmed", "-"
    fob.deliver = deliver
    _, log = quiet(fob.send_boot_report, results_)
    msg = json.loads(sent[0])
    check("BOOT message sent once", len(sent) == 1 and msg["type"] == "BOOT", sent[0])
    check("BOOT fail bits: lora 4 + gps 8 + battery 16 + pressure 32 = 60", msg["fail"] == 60, str(msg))
    check("BOOT has the firmware version", msg["fw"] == main.FW_VERSION)
    check("BOOT fits a LoRa packet easily", len(sent[0]) < 200, "{} bytes".format(len(sent[0])))
    check("BOOT uses a counter like any message", msg["ctr"] == 0 and open("counter.txt").read() == "0")

    # a press during the boot report stops it
    def deliver_pressed(kind, payload, ctr, sig, budget=None, stop=None, try_no=None):
        raise main.PressStop()
    fob.deliver = deliver_pressed
    _, log = quiet(fob.send_boot_report, results_)
    check("a press stops the boot report (and keeps it for later)",
          "BOOT_STOPPED ctr=1 reason=button" in log and fob.boot_pending is not None, log)
    return msg


def test_server(fob_msg):
    server = os.path.join(HERE, "..", "server")
    sys.path.insert(0, server)
    os.environ["SAFEPING_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
    for name in ("config", "db", "validate", "processor", "app", "stats"):
        sys.modules.pop(name, None)
    import db
    import processor
    import validate
    db.init_db()
    db.add_device("FOB-T", "FOB", "Test Student", "f" * 32)

    fob_msg = dict(fob_msg)
    fob_msg["ts"] = int(__import__("time").time())        # the fake board had no clock
    msg = dict(fob_msg)
    msg.pop("sig")
    # re-sign with the Fob's own code, so the test proves the Fob and server agree
    main = sys.modules["main"]
    fob_msg["sig"] = main.sign(msg)
    check("server and Fob build the same BOOT signing string", validate.signing_string(fob_msg) == main.signing_string(fob_msg))
    acks = []
    r = processor.process(json.dumps(fob_msg), source="lora", on_ack=lambda *a: acks.append(a))
    check("server accepts the Fob's BOOT", r.get("ok") and r.get("kind") == "boot", str(r))
    check("BOOT is acked like an alert", len(acks) == 1)
    check("BOOT failed parts in plain words", r["failed"] == ["LoRa radio not answering", "GPS not sending data",
                                                               "Battery gauge not reading", "Pressure sensor not reading"], str(r))
    with db.connect() as c:
        alerts = c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    check("BOOT is never stored as an alert", alerts == 0)
    r = processor.process(json.dumps(fob_msg), source="wifi", on_ack=lambda *a: acks.append(a))
    check("same BOOT again is 'duplicate'", r["reason"] == "duplicate", str(r))

    tampered = dict(fob_msg, fail=0)
    check("BOOT with an edited fail field is 'bad_signature'",
          processor.process(json.dumps(tampered))["reason"] == "bad_signature")
    bad_fw = dict(fob_msg, fw="1|2", ctr=99)
    bad_fw.pop("sig")
    bad_fw["sig"] = validate.sign("f" * 32, bad_fw)
    check("BOOT with a | in fw is 'bad_format'", processor.process(json.dumps(bad_fw))["reason"] == "bad_format")

    import fake_fob   # noqa: F401
    now = int(__import__("time").time())
    for i in range(12):
        m = {"v": 1, "id": "FOB-T", "type": "BOOT", "ctr": 100 + i, "ts": now, "fail": 0 if i % 2 else 8,
             "wifi": 1, "fw": "2026.11.11"}
        m["sig"] = validate.sign("f" * 32, m)
        processor.process(json.dumps(m), source="wifi")
    check("only the newest 10 boot reports kept", len(db.list_boots("FOB-T", 50)) == 10)
    check("newest first", db.list_boots("FOB-T")[0]["counter"] == 111)

    import app
    web = app.app.test_client()
    devices = web.get("/api/devices").get_json()["devices"]
    boot = [d for d in devices if d["device_id"] == "FOB-T"][0]["last_boot"]
    check("Devices API: last start with all checks passed", boot["all_passed"] and boot["failed"] == [], str(boot))
    check("Devices API: WiFi result as information", boot["wifi"] is True)
    boots = web.get("/api/devices/FOB-T/boots").get_json()["boots"]
    check("boot history: 10 reports, failures in plain words",
          len(boots) == 10 and boots[1]["failed"] == ["GPS not sending data"], str(boots[1]))
    stats = web.get("/api/stats?from=2026-01-01&to=2026-12-31").get_json()
    check("Overview: BOOT never counts", stats["total"] == 0 and stats["delivery"] == {"lora": 0, "wifi": 0, "unknown": 0},
          str(stats["delivery"]))
    check("Live: BOOT never shows", web.get("/api/alerts?status=1").get_json()["alerts"] == [])
    check("older BOOT without rst still accepted (the 12 above), reason not reported",
          boots[0]["reset_words"] is None and boots[0]["crashed"] is False)

    # reset cause (machine.reset_cause()), signed by the Fob's own code
    for code, words in ((2, "Restarted after a crash"), (1, "Power on")):
        m = selfcheck.boot_message("FOB-T", 200 + code, now, 90, 0, True, main.FW_VERSION, code)
        m["sig"] = main.sign(m)
        r = processor.process(json.dumps(m), source="wifi")
        last = web.get("/api/devices").get_json()["devices"][0]["last_boot"]
        check("BOOT rst={}: accepted, Devices says '{}'".format(code, words),
              r.get("ok") and last["reset_words"] == words and last["crashed"] == (code == 2), str(last))
    tampered = dict(m, rst=2)
    check("BOOT with an edited rst is 'bad_signature'",
          processor.process(json.dumps(tampered))["reason"] == "bad_signature")
    stats = web.get("/api/stats?from=2026-01-01&to=2026-12-31").get_json()
    check("restarts never count as alerts", stats["total"] == 0)
    check("SELF_CHECK line has the reset word",
          "reset=crash fw=" in selfcheck.summary_line({}, "x", 2))


class AckClient:
    """An open MQTT connection for the help listener. publish() of a BOOT gets the server's
    ack back on the ack topic (like the real server), unless answer is False."""

    def __init__(self, ack_text, answer=True):
        self.inbox = []
        self.sock = object()
        self.cb = None
        self.left_ms = lambda: 1000
        self.published = []
        self.ack_text = ack_text
        self.answer = answer
        self.closed = False

    def set_callback(self, cb):
        self.cb = cb

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload))
        if self.answer:
            self.inbox.append((b"safeping/ack/FOB-T", self.ack_text.encode()))

    def wait_msg(self):
        if not self.inbox:
            if self.left_ms() <= 0:
                raise OSError(110)
            fakeboard.clock[0] += 100
            if self.left_ms() <= 0:
                raise OSError(110)
            return None
        topic, msg = self.inbox.pop(0)
        self.cb(topic, msg)

    def ping(self):
        pass

    def disconnect(self):
        self.closed = True

    def close(self):
        self.closed = True


def test_boot_resend():
    """A press stops the BOOT report. The same signed message is sent after the press."""
    main = fakeboard.load_fob(workdir=tempfile.mkdtemp())
    fob = main.Fob()
    results_ = {k: "ok" for k in ("key", "counter", "lora", "gps", "battery")}
    results_.update(pressure="fail", wifi="ok")

    def stopped(*a, **k):
        raise main.PressStop()
    fob.deliver = stopped
    _, log = quiet(fob.send_boot_report, results_)
    first = json.loads(log.split("SAFEPING_MSG ")[1].splitlines()[0])
    check("stopped BOOT: kept for later", fob.boot_pending is not None and fob.boot_pending[1] == first["ctr"])
    check("stopped BOOT: BOOT_STOPPED line", "BOOT_STOPPED ctr={} reason=button".format(first["ctr"]) in log, log)

    # not while the button is held, the motor runs, or the Fob is busy
    fakeboard.button.press()
    fob.btn.events(fakeboard.clock[0])
    sent = []
    fob.deliver = lambda kind, payload, ctr, sig, budget=None, stop=None, try_no=None: (
        sent.append((kind, payload, ctr, sig)) or (True, "confirmed", "-"))
    quiet(fob.resend_boot)
    check("not sent while the button is held", sent == [])
    fakeboard.button.release()
    for _ in range(10):
        fakeboard.clock[0] += 10
        fob.btn.events(fakeboard.clock[0])

    # sent the normal way when the Fob is not listening for help
    fob.state = main.IDLE
    _, log = quiet(fob.resend_boot)
    check("sent later: the same signed message, same counter",
          len(sent) == 1 and json.loads(sent[0][1]) == first and sent[0][2] == first["ctr"], str(sent))
    check("sent later: BOOT_RESEND and 'sent later: confirmed'",
          "BOOT_RESEND ctr={}".format(first["ctr"]) in log and "BOOT report sent later: confirmed" in log, log)
    check("sent later: nothing left to send", fob.boot_pending is None)

    # while listening for help: on the same connection, and listening goes on
    fob.boot_pending = (json.dumps(first), first["ctr"], first["sig"])
    ack = main.ackcheck.ack_text(main.ACK_KEY, "FOB-T", first["ctr"], first["sig"])
    client = AckClient(ack)
    fob.help.listen(client, 99, "SUSPICIOUS")
    sent.clear()
    _, log = quiet(fob.resend_boot)
    check("while listening: sent on the help connection, not a new one",
          sent == [] and client.published == [("safeping/alert/FOB-T", json.dumps(first))], str(client.published))
    check("while listening: confirmed, SEND_RESULT says resend=1",
          "kind=BOOT path=wifi result=confirmed" in log and "resend=1" in log and fob.boot_pending is None, log)
    check("while listening: still listening for help afterwards",
          fob.help.active() and fob.help.client is client and 99 in fob.help.waiting)
    client.inbox.append((b"safeping/help/FOB-T", main.ackcheck.help_text(main.HELP_KEY, "FOB-T", 99).encode()))
    fob.help.ready = lambda sock: bool(client.inbox)      # the fake socket has data
    _, log = quiet(fob.help.step)
    check("while listening: help for the alert still arrives after the BOOT", "HELP_RECEIVED ctr=99" in log, log)

    # the help connection does not answer: falls back to the normal send
    fob.boot_pending = (json.dumps(first), first["ctr"], first["sig"])
    client2 = AckClient(ack, answer=False)
    fob.help.listen(client2, 98, "MEDICAL")
    _, log = quiet(fob.resend_boot)
    check("no ack on the help connection: sent the normal way instead",
          len(sent) == 1 and fob.boot_pending is None and "sending it the normal way" in log, log)

    # step() sends it once the Fob is idle
    fob.boot_pending = (json.dumps(first), first["ctr"], first["sig"])
    fob.help.close()
    fob.help.waiting.clear()
    fob.help.received.clear()           # else the help buzz plays first, and the resend waits for it
    sent.clear()
    fob.state = main.IDLE
    fob.motor.stop()
    quiet(fob.step, fakeboard.clock[0])
    check("step(): sent when the Fob is idle", len(sent) == 1 and fob.boot_pending is None, str(sent))


def test_logger():
    sys.path.insert(0, HERE)
    import field_log
    s = field_log.Session("t", os.path.join(tempfile.mkdtemp(), "x"))
    shown = s.fob_line(0, "SELF_CHECK key=ok counter=ok lora=fail gps=ok battery=ok pressure=ok wifi=fail fw=2026.11.11")
    check("logger shows the SELF_CHECK line", shown is not None and "lora=fail" in shown, str(shown))
    text = s.summary(10)
    check("logger summary lists the failed parts", "Self-check 1:" in text and "FAILED lora" in text, text)


def main():
    test_rules()
    msg = test_main()
    test_server(msg)
    test_boot_resend()
    test_logger()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
