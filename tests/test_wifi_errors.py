"""Laptop test: every WiFi error the Fob can hit gives its real reason.

Board test 2026-11-10, ctr 207: building umqtt_safe's error crashed on MicroPython
("type object 'Exception' has no attribute '__init__'"), so a connect problem was
reported as connect_failed. This test:
  1. checks the firmware source for exception code MicroPython 1.27 cannot run
     (an __init__ on an exception class, Exception.__init__ or super().__init__ calls)
  2. raises each error type inside the real umqtt_safe client, through the same
     sendpath.mqtt_attempt() the Fob runs, and checks the reason and the plain words

  python tests/test_wifi_errors.py"""
import ast
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, "..", "firmware")
sys.path.insert(0, os.path.join(FIRMWARE, "lib"))

import ackcheck     # noqa: E402
import sendpath     # noqa: E402
import umqtt_safe   # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


# ---------- 1. source check ----------
FILES = ["lib/umqtt_safe.py", "lib/sendpath.py", "fob/main.py"]


def _exception_class(node):
    for base in node.bases:
        name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        if name.endswith("Exception") or name.endswith("Error"):
            return True
    return False


def test_source():
    for rel in FILES:
        path = os.path.join(FIRMWARE, rel)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), rel)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _exception_class(node):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        bad.append("{} defines __init__ (line {})".format(node.name, item.lineno))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "__init__":
                owner = node.func.value
                if isinstance(owner, ast.Name) and (owner.id.endswith("Exception") or owner.id.endswith("Error")):
                    bad.append("{}.__init__ call (line {})".format(owner.id, node.lineno))
                if isinstance(owner, ast.Call) and getattr(owner.func, "id", "") == "super":
                    bad.append("super().__init__ call (line {})".format(node.lineno))
        check("{}: no exception code MicroPython cannot run".format(rel), not bad, "; ".join(bad))

    err = umqtt_safe.StepError("connect", "no answer", True)
    check("StepError has no __init__ of its own", "__init__" not in umqtt_safe.StepError.__dict__)
    check("StepError keeps step, detail, timed_out in args", err.args == ("connect", "no answer", True))
    check("step_parts reads a StepError", umqtt_safe.step_parts(err) == ("connect", "no answer", True))
    check("step_parts ignores other errors", umqtt_safe.step_parts(OSError(110)) is None)
    check("StepError prints", "no answer" in str(err))


# ---------- 2. scripted sockets ----------
class Script:
    """What the fake broker does. read_data is what the client gets to read.
    After it runs out: end_error is raised, or b"" (connection closed) if end_error is None."""

    def __init__(self, connect_error=None, read_data=b"", end_error=OSError(110),
                 write_error=None, before_end=None):
        self.connect_error = connect_error
        self.buf = read_data
        self.end_error = end_error
        self.write_error = write_error
        self.before_end = before_end
        self.written = b""


class ScriptSocket:
    script = None

    def __init__(self, *args):
        self.s = ScriptSocket.script

    def connect(self, addr):
        if self.s.connect_error is not None:
            raise self.s.connect_error

    def settimeout(self, t):
        pass

    def setblocking(self, flag):
        pass

    def read(self, n):
        if self.s.buf:
            out, self.s.buf = self.s.buf[:n], self.s.buf[n:]
            return out
        if self.s.before_end:
            self.s.before_end()
        if self.s.end_error is None:
            return b""
        raise self.s.end_error

    def write(self, data):
        if self.s.write_error is not None and b"safeping/alert" in bytes(data):
            raise self.s.write_error            # fails when the publish topic goes out
        self.s.written += bytes(data)
        return len(data)

    def close(self):
        pass


class FakeSocketModule:
    socket = ScriptSocket


class FakeSelect:
    """For the non-blocking connect path: poll() returns these events."""
    POLLOUT, POLLERR, POLLHUP = 4, 8, 16

    def __init__(self, events):
        self.events = events

    def poll(self):
        sel = self

        class Poller:
            def register(self, sock, mask):
                pass

            def poll(self, ms):
                return sel.events

        return Poller()


class FakeTLS:
    def __init__(self, error):
        self.error = error

    def wrap_socket(self, sock, server_hostname=None):
        raise self.error


umqtt_safe.socket = FakeSocketModule

CONNACK = b"\x20\x02\x00\x00"
SUBACK = b"\x90\x03\x00\x01\x01"        # pid 1 (the subscribe)
PUBACK = b"\x40\x02\x00\x02"            # pid 2 (the publish)
KEY = ackcheck.ack_key(b"test-secret")
SIG = "ab" * 32
GOOD_ACK = ackcheck.ack_text(KEY, "FOB-T", 7, SIG)


def publish_packet(topic, payload, pid=9):
    t = topic.encode()
    body = struct.pack("!H", len(t)) + t + struct.pack("!H", pid) + payload
    return bytes([0x32, len(body)]) + body


def attempt(script, budget_ms=5000, select_mod=None, tls=None, clock=None):
    """Run one attempt through the same code the Fob uses. Returns (reason, detail, published)."""
    ScriptSocket.script = script
    umqtt_safe.select = select_mod
    if clock is not None:
        budget = sendpath.Budget(budget_ms, clock=lambda: clock[0], diff=lambda a, b: a - b)
    else:
        budget = sendpath.Budget(budget_ms)
    got = []

    def on_msg(topic, msg):
        if topic == b"safeping/ack/FOB-T" and msg.strip() == GOOD_ACK.encode():
            got.append(1)

    client = umqtt_safe.MQTTClient("FOB-T", user="safeping-fob", password="placeholder", keepalive=30)
    client.set_callback(on_msg)
    confirmed, reason, published, detail, step = sendpath.mqtt_attempt(
        client, ("10.0.0.1", 8883), budget, tls, "broker.example", "safeping/ack/FOB-T",
        "safeping/alert/FOB-T", b'{"v":1}', 300, got, umqtt_safe.step_parts)
    return ("confirmed" if confirmed else reason), detail, published


def case(name, expect, script, words=None, **kw):
    reason, detail, published = attempt(script, **kw)
    plain = sendpath.plain_reason(reason, detail) if reason != "confirmed" else ""
    ok = reason == expect and (words is None or words in plain)
    check(name, ok, "{} | {}".format(reason, plain))
    return reason, detail, published


def test_errors():
    # TCP connect, blocking path (no poll)
    case("connect timed out (lwIP ETIMEDOUT 116)", "connect_timeout",
         Script(connect_error=OSError(116)), words="did not answer")
    case("connect timed out (ETIMEDOUT 110)", "connect_timeout", Script(connect_error=OSError(110)))
    case("connect refused (111)", "connect_failed", Script(connect_error=OSError(111)),
         words="refused the connection")
    case("connect reset (104, like the pre-test)", "connect_failed", Script(connect_error=OSError(104)),
         words="reset the connection")
    case("no route (113)", "connect_failed", Script(connect_error=OSError(113)), words="no route")

    # TCP connect, non-blocking path with poll (what the board uses)
    case("silent address: poll finds nothing", "connect_timeout",
         Script(connect_error=OSError(119)), select_mod=FakeSelect([]), words="no answer")
    case("poll says hung up", "connect_failed",
         Script(connect_error=OSError(119)), select_mod=FakeSelect([(None, FakeSelect.POLLHUP)]),
         words="refused or unreachable")
    case("budget already used up before connect", "connect_timeout", Script(), budget_ms=0,
         words="time budget used up")

    # TLS
    case("bad certificate (mbedTLS -9984)", "tls_failed", Script(), tls=FakeTLS(OSError(-9984)),
         words="certificate did not check out")
    case("TLS handshake timed out", "tls_failed", Script(), tls=FakeTLS(OSError(110)))
    case("TLS closed by the broker (-29312)", "tls_failed", Script(), tls=FakeTLS(OSError(-29312)))
    case("TLS other error (ValueError)", "tls_failed", Script(), tls=FakeTLS(ValueError("bad key")))

    # MQTT login
    case("login refused (code 5)", "connect_failed", Script(read_data=b"\x20\x02\x00\x05"),
         words="refused the login (code 5)")
    case("not an MQTT broker", "connect_failed", Script(read_data=b"HTTP"), words="not an MQTT broker")
    case("login timed out, budget left", "connect_timeout", Script(read_data=b""))
    clock = [0]

    def jump():
        clock[0] = 6000                    # the wait used up the whole budget

    case("login timed out, budget gone", "budget_exceeded",
         Script(read_data=b"", before_end=jump), clock=clock)
    case("connection closed during login", "connect_failed", Script(read_data=b"", end_error=None),
         words="connection closed")

    # subscribe and publish
    case("connection closed at subscribe", "connect_failed",
         Script(read_data=CONNACK, end_error=None), words="connection closed")
    case("subscription refused", "connect_failed",
         Script(read_data=CONNACK + b"\x90\x03\x00\x01\x80"), words="refused the subscription")
    case("write error at publish", "connect_failed",
         Script(read_data=CONNACK + SUBACK, write_error=OSError(104)), words="reset the connection")

    # the server's ack
    reason, detail, published = case("no ack from the server", "no_server_ack",
                                     Script(read_data=CONNACK + SUBACK + PUBACK),
                                     words="server did not confirm")
    check("no ack: the broker had it (published)", published)
    wrong = publish_packet("safeping/ack/FOB-T", b"ACK FOB-T 7 0000000000000000")
    case("wrong ack, then nothing", "no_server_ack", Script(read_data=CONNACK + SUBACK + PUBACK + wrong))
    good = publish_packet("safeping/ack/FOB-T", GOOD_ACK.encode())
    case("right ack confirms", "confirmed", Script(read_data=CONNACK + SUBACK + PUBACK + good))
    case("ack before PUBACK confirms", "confirmed", Script(read_data=CONNACK + SUBACK + good + PUBACK))

    # every reason has plain words
    missing = [r for r in sendpath.REASONS if r != "-" and r not in sendpath.PLAIN]
    check("every reason has plain words", not missing, str(missing))
    text = " ".join(sendpath.PLAIN.values()) + " ".join(sendpath.ERRNO_WORDS.values())
    check("no em dashes in the plain words", "—" not in text)


def main():
    test_source()
    test_errors()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
