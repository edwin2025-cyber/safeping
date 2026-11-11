"""Laptop test of "help is coming" over WiFi (Part D).

  1. the signed help message: the server's text is what the Fob checks
  2. helplisten.py: valid message buzzes, wrong signature ignored, wrong ctr ignored,
     unsigned ignored, timeout after 2 minutes, pings keep the connection open
  3. the real main.py (fake board): the buzz, SILENT never buzzes or lights, a press
     still works while listening, and a new send closes the listener first
  4. sendpath.mqtt_attempt: one SUBSCRIBE for ack + help, a refused help topic never
     stops the alert, and the client is kept open only after a confirm
  5. the server: Acknowledge publishes the help message and the history shows it

  python tests/test_help.py"""
import contextlib
import io
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard        # noqa: E402

fakeboard._patch_time()
import ackcheck         # noqa: E402
import helplisten       # noqa: E402
import sendpath         # noqa: E402
import umqtt_safe       # noqa: E402

SECRET = b"f" * 32                       # test key, not a real one
KEY = ackcheck.help_key(SECRET)
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


class FakeClient:
    """Stands in for an open umqtt_safe client. inbox holds (topic, text) to deliver."""

    def __init__(self):
        self.inbox = []
        self.sock = object()
        self.cb = None
        self.pings = 0
        self.closed = False
        self.left_ms = lambda: 1000
        self.fail_next = False

    def set_callback(self, cb):
        self.cb = cb

    def wait_msg(self):
        if self.fail_next:
            raise OSError(104)
        topic, msg = self.inbox.pop(0)
        self.cb(topic.encode(), msg.encode())
        return 0x30

    def ping(self):
        self.pings += 1

    def disconnect(self):
        self.closed = True

    def close(self):
        self.closed = True


def listener(clock, logs):
    return helplisten.HelpListener("FOB-T", KEY, 120000, log=logs.append, clock=lambda: clock[0],
                                   diff=lambda a, b: a - b, add=lambda a, b: a + b,
                                   ready=lambda sock: bool(client_of(sock)))


_clients = {}


def client_of(sock):
    c = _clients.get(id(sock))
    return c is not None and (c.inbox or c.fail_next)


def new_client():
    c = FakeClient()
    _clients[id(c.sock)] = c
    return c


TOPIC = "safeping/help/FOB-T"


# ---------- 1 and 2 ----------
def test_listener():
    good = ackcheck.help_text(KEY, "FOB-T", 12)
    check("help text format", good.startswith("HELP FOB-T 12 ") and len(good.split()[3]) == 16, good)
    check("help key differs from the ack key", KEY != ackcheck.ack_key(SECRET))

    clock, logs = [0], []
    hl = listener(clock, logs)
    c = new_client()
    hl.listen(c, 12, "MEDICAL", now=0)
    check("listening after a WiFi confirm", hl.active() and 12 in hl.waiting)

    # wrong signature
    bad = "HELP FOB-T 12 0000000000000000"
    c.inbox.append((TOPIC, bad))
    clock[0] = 1000
    hl.step()
    check("wrong signature ignored and logged", hl.received == [] and "HELP ignored: bad_signature ctr=12" in logs, str(logs))
    # wrong ctr (validly signed, but for another alert)
    c.inbox.append((TOPIC, ackcheck.help_text(KEY, "FOB-T", 11)))
    hl.step()
    check("wrong ctr ignored and logged", hl.received == [] and "HELP ignored: other_ctr ctr=11" in logs, str(logs))
    # unsigned, junk, other device, ack topic
    c.inbox.append((TOPIC, "HELP"))
    hl.step()
    c.inbox.append((TOPIC, ackcheck.help_text(KEY, "FOB-X", 12).replace("FOB-X", "FOB-X")))
    hl.step()
    check("unsigned and other-device messages ignored",
          "HELP ignored: not_help ctr=-" in logs and "HELP ignored: other_device ctr=-" in logs, str(logs))
    c.inbox.append(("safeping/ack/FOB-T", good))
    hl.step()
    check("a help text on another topic is ignored", hl.received == [])
    signed_with_ack_key = ackcheck.help_text(ackcheck.ack_key(SECRET), "FOB-T", 12)
    c.inbox.append((TOPIC, signed_with_ack_key))
    hl.step()
    check("signed with the ack key (what a stolen Relay has): rejected", hl.received == [])
    check("still listening after bad messages", hl.active())

    # valid
    clock[0] = 45000
    c.inbox.append((TOPIC, good))
    hl.step()
    check("valid help received", hl.received == [(12, "MEDICAL", 45000)], str(hl.received))
    check("HELP_RECEIVED line with ms_after_confirm", "HELP_RECEIVED ctr=12 ms_after_confirm=45000" in logs, str(logs))
    check("disconnects once nothing is left to wait for", not hl.active() and c.closed)

    # a repeat of the same help (QoS 1 resend) after that does nothing
    hl.received.clear()
    check("not listening any more, so no second buzz", hl.received == [])

    # timeout after 2 minutes
    clock[0], logs[:] = 0, []
    hl = listener(clock, logs)
    c = new_client()
    hl.listen(c, 20, "SUSPICIOUS", now=0)
    clock[0] = 20000
    hl.step(can_send=False)
    check("no ping while the motor runs", c.pings == 0)
    hl.step(can_send=True)
    check("ping every 20 s keeps the connection open", c.pings == 1)
    clock[0] = 119999
    hl.step()
    check("still listening just before 2 minutes", hl.active())
    clock[0] = 120000
    hl.step()
    check("stops after 2 minutes", not hl.active() and c.closed and "HELP_TIMEOUT ctr=20 ms=120000" in logs, str(logs))
    c.inbox.append((TOPIC, ackcheck.help_text(KEY, "FOB-T", 20)))
    hl.step()
    check("help after the timeout is never read", hl.received == [])

    # connection lost while listening
    clock[0], logs[:] = 0, []
    hl = listener(clock, logs)
    c = new_client()
    hl.listen(c, 30, "MEDICAL", now=0)
    c.fail_next = True
    hl.step()
    check("connection lost: listener ends cleanly", not hl.active() and "HELP_LISTEN_END reason=connection_lost" in logs, str(logs))

    check("feedback: SILENT never buzzes", helplisten.feedback("SILENT") is None)
    check("feedback: others get the help buzz",
          all(helplisten.feedback(k) == "help" for k in ("MEDICAL", "SUSPICIOUS")))


# ---------- 3. the real main.py ----------
def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


def test_main():
    main = fakeboard.load_fob(workdir=tempfile.mkdtemp())
    fob = main.Fob()
    check("main: help listener on when WiFi is on", fob.help is not None)
    clients = []

    def wifi_ok(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
        c = new_client()
        clients.append((ctr, c))
        if keep_open is not None:
            keep_open.append(c)
        return True, "-", True, None
    main.wifi_send = wifi_ok
    fob.help.ready = lambda sock: bool(client_of(sock))
    fob.state = main.IDLE

    ok, log = quiet(fob.send, "MEDICAL")
    ctr, client = clients[-1]
    check("main: WiFi confirm starts listening", ok and fob.help.active() and ctr in fob.help.waiting, log)
    check("main: HELP_LISTEN line", "HELP_LISTEN ctr={} kind=MEDICAL ms=120000".format(ctr) in log, log)

    fob.motor.stop()
    fob.state = main.IDLE
    client.inbox.append((TOPIC, ackcheck.help_text(KEY, "FOB-T", ctr)))
    fakeboard.clock[0] += 3000
    _, log = quiet(fob.step, fakeboard.clock[0])
    # play() starts the first 400 ms pulse at once, the other four steps wait in the queue
    check("main: valid help gives three slow pulses (400 ms on, 400 ms off)",
          fob.motor.level == 1 and fob.motor.queue == [(0, 400), (1, 400), (0, 400), (1, 400)]
          and fob.led.color == main.GREEN, str(fob.motor.queue))
    check("main: help buzz playing", fob.motor.busy() and fob.motor.level == 1, str(fob.motor.queue))
    check("main: HELP_RECEIVED logged", "HELP_RECEIVED ctr={}".format(ctr) in log, log)

    # SILENT: logged, never a buzz or light
    fob.motor.stop()
    fob.led.off()
    ok, log = quiet(fob.send, "SILENT")
    ctr, client = clients[-1]
    fob.motor.stop()
    fob.led.off()
    fob.state = main.IDLE
    client.inbox.append((TOPIC, ackcheck.help_text(KEY, "FOB-T", ctr)))
    fakeboard.clock[0] += 3000
    led_calls, motor_calls = [], []
    real_show, real_play = fob.led.show, fob.motor.play
    fob.led.show = lambda color, *a, **k: led_calls.append(color) or real_show(color, *a, **k)
    fob.motor.play = lambda name, *a, **k: motor_calls.append(name) or real_play(name, *a, **k)
    _, log = quiet(fob.step, fakeboard.clock[0])
    for _ in range(300):                       # 3 s more: the whole time a help buzz would last
        fakeboard.clock[0] += 10
        quiet(fob.step, fakeboard.clock[0])
    fob.led.show, fob.motor.play = real_show, real_play
    check("main: SILENT help is logged", "HELP_RECEIVED ctr={}".format(ctr) in log, log)
    check("main: SILENT help: the green blink is never shown", main.GREEN not in led_calls and led_calls == [],
          str(led_calls))
    check("main: SILENT help: the help buzz is never played", "help" not in motor_calls, str(motor_calls))
    check("main: SILENT help: no buzz", not fob.motor.busy() and fob.motor.shown is False, str(fob.motor.queue))
    check("main: SILENT help: no light", fob.led.color == main.OFF)

    # STATUS: no listening at all
    quiet(fob.send, "STATUS")
    check("main: STATUS does not listen", not fob.help.active())

    # a press while listening still works, and the next send closes the listener first
    quiet(fob.send, "SUSPICIOUS")
    ctr, first = clients[-1]
    fob.motor.stop()
    fob.state = main.IDLE
    fakeboard.button.press()
    for _ in range(10):
        fakeboard.clock[0] += 10
        fob.step(fakeboard.clock[0])
    check("main: press while listening is handled", fob.state == main.DOWN, fob.state)
    check("main: listening goes on during the press", fob.help.active())
    fakeboard.button.release()
    for _ in range(80):
        fakeboard.clock[0] += 10
        quiet(fob.step, fakeboard.clock[0])
    check("main: the tap was sent (STATUS) and closed the old connection first", first.closed)
    check("main: the older alert is still waited for", ctr in fob.help.waiting)
    status_ctr, second = clients[-1]
    check("main: the STATUS connection is kept for the older alert",
          fob.help.active() and fob.help.client is second and status_ctr not in fob.help.waiting)
    fob.motor.stop()
    fob.state = main.IDLE
    second.inbox.append((TOPIC, ackcheck.help_text(KEY, "FOB-T", ctr)))
    fakeboard.clock[0] += 1000
    _, log = quiet(fob.step, fakeboard.clock[0])
    check("main: help for the older alert still arrives after the STATUS tap",
          "HELP_RECEIVED ctr={}".format(ctr) in log and fob.motor.busy(), log)


# ---------- 4. sendpath with the help topic ----------
class ScriptSocket:
    data = b""
    written = b""

    def __init__(self, *a):
        pass

    def connect(self, addr):
        pass

    def settimeout(self, t):
        pass

    def read(self, n):
        if not ScriptSocket.data:
            raise OSError(110)
        out, ScriptSocket.data = ScriptSocket.data[:n], ScriptSocket.data[n:]
        return out

    def write(self, data):
        ScriptSocket.written += bytes(data)
        return len(data)

    def close(self):
        pass


class SockMod:
    socket = ScriptSocket


def publish_packet(topic, payload, pid=9):
    t = topic.encode()
    body = struct.pack("!H", len(t)) + t + struct.pack("!H", pid) + payload
    return bytes([0x32, len(body)]) + body


def attempt(suback, ack=True):
    umqtt_safe.socket = SockMod
    umqtt_safe.select = None
    ack_key = ackcheck.ack_key(SECRET)
    good = ackcheck.ack_text(ack_key, "FOB-T", 7, "ab" * 32)
    ScriptSocket.written = b""
    ScriptSocket.data = (b"\x20\x02\x00\x00" + suback + b"\x40\x02\x00\x02"
                         + (publish_packet("safeping/ack/FOB-T", good.encode()) if ack else b""))
    got = []

    def cb(topic, msg):
        if msg == good.encode():
            got.append(1)
    client = umqtt_safe.MQTTClient("FOB-T", keepalive=30)
    client.set_callback(cb)
    keep = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = sendpath.mqtt_attempt(client, ("10.0.0.1", 8883), sendpath.Budget(5000), None, "b",
                                       "safeping/ack/FOB-T", "safeping/alert/FOB-T", b"{}", 300, got,
                                       umqtt_safe.step_parts, help_topic=TOPIC, keep_open=keep)
    return result, keep, out.getvalue()


def test_sendpath():
    (confirmed, reason, *_), keep, log = attempt(b"\x90\x04\x00\x01\x01\x01")
    check("one SUBSCRIBE packet holds both topics",
          ScriptSocket.written.count(b"\x82") == 1 and b"safeping/help/FOB-T" in ScriptSocket.written)
    check("both granted and confirmed: client kept open for the listener", confirmed and len(keep) == 1)
    (confirmed, reason, *_), keep, log = attempt(b"\x90\x04\x00\x01\x01\x80")
    check("help topic refused (no EMQX permission yet): alert still confirmed", confirmed, reason)
    check("help topic refused: client not kept, message says why", keep == [] and "EMQX permission" in log, log)
    (confirmed, reason, *_), keep, log = attempt(b"\x90\x04\x00\x01\x80\x01")
    check("ack topic refused: not confirmed (as before)", not confirmed and reason == "connect_failed", reason)
    (confirmed, reason, *_), keep, log = attempt(b"\x90\x04\x00\x01\x01\x01", ack=False)
    check("no ack: not confirmed, client not kept", not confirmed and reason == "no_server_ack" and keep == [])


# ---------- 5. the server ----------
def test_server():
    server = os.path.join(HERE, "..", "server")
    sys.path.insert(0, server)
    os.environ["SAFEPING_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
    for name in ("config", "db", "validate", "processor", "mqtt_listener", "app", "stats"):
        sys.modules.pop(name, None)
    import db
    import fake_fob
    import mqtt_listener
    import processor
    try:
        import app
    except ImportError as err:
        print("SKIP  server checks ({})".format(err))
        return
    db.init_db()
    secret = SECRET.decode()
    db.add_device("FOB-T", "FOB", "Test Student", secret)
    topic, text = mqtt_listener.help_for("FOB-T", 41)
    ctr, reason = ackcheck.check_help(KEY, "FOB-T", text, {41: None})
    check("server: help goes to safeping/help/FOB-T", topic == "safeping/help/FOB-T", topic)
    check("server: the Fob accepts the server's help text", ctr == 41 and reason is None, str(reason))

    msg = fake_fob.build_message("FOB-T", secret, "MEDICAL", 41, battery=80)
    r = processor.process(__import__("json").dumps(msg), source="wifi")
    sent = []
    app.help_sender = lambda device_id, c: sent.append((device_id, c)) or True
    web = app.app.test_client()
    first = web.post("/api/ack", json={"id": r["alert_id"]}).get_json()
    check("server: Acknowledge sends one help message with the alert's ctr",
          sent == [("FOB-T", 41)] and first["help_sent"] is True, str(sent))
    again = web.post("/api/ack", json={"id": r["alert_id"]}).get_json()
    check("server: a second Acknowledge sends nothing", len(sent) == 1 and again["help_sent"] is False)
    alert = web.get("/api/alerts/{}".format(r["alert_id"])).get_json()["alert"]
    check("server: alert history has help_sent_at", alert["help_sent_at"] is not None, str(alert.get("help_sent_at")))

    app.help_sender = None
    msg = fake_fob.build_message("FOB-T", secret, "MEDICAL", 42, battery=80)
    r = processor.process(__import__("json").dumps(msg), source="wifi")
    out = web.post("/api/ack", json={"id": r["alert_id"]}).get_json()
    alert = web.get("/api/alerts/{}".format(r["alert_id"])).get_json()["alert"]
    check("server: no MQTT (NO_MQTT=1): acknowledged, no help claimed",
          out["changed"] and out["help_sent"] is False and alert["help_sent_at"] is None)


def main():
    test_listener()
    test_main()
    test_sendpath()
    test_server()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
