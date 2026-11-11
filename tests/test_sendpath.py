"""Laptop test of the Fob's WiFi budget and fallback logic. No board, no real config.

Tests firmware/lib/sendpath.py (the rules) and firmware/lib/umqtt_safe.py (the MQTT client)
against a tiny fake broker on this laptop:
  - connect, subscribe, publish and the signed ack, in order
  - a broker that accepts TCP but never answers MQTT: gives up inside the budget
  - a server that never acks: the ack wait ends on time

  python tests/test_sendpath.py"""
import os
import socket
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware", "lib"))

import ackcheck     # noqa: E402
import sendpath     # noqa: E402
import umqtt_safe   # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


# ---------- pure rules ----------
def test_rules():
    clock = [1000]
    b = sendpath.Budget(5000, clock=lambda: clock[0], diff=lambda a, c: a - c)
    check("budget starts full", b.left() == 5000)
    check("join is capped by WIFI_JOIN_MS", b.left(3000) == 3000)
    clock[0] += 4200
    check("budget counts down", b.left() == 800 and b.used() == 4200)
    check("join cap never exceeds what is left", b.left(3000) == 800)
    clock[0] += 2000
    check("budget never below 0", b.left() == 0 and b.left(3000) == 0)

    s = sendpath.skip_reason
    check("WIFI_SSID none skips WiFi", s("none", True, True, True, True, 2026) == "wifi_off")
    check("WIFI_SSID None skips WiFi", s(None, True, True, True, True, 2026) == "wifi_off")
    check("WIFI_SSID empty skips WiFi", s("", True, True, True, True, 2026) == "wifi_off")
    check("missing ackcheck skips WiFi", s("net", True, False, True, True, 2026) == "ackcheck_missing")
    check("missing CA skips WiFi", s("net", True, True, True, False, 2026) == "ca_missing")
    check("clock in 2000 skips WiFi", s("net", True, True, True, True, 2000) == "clock_not_set")
    check("clock in 2025 skips WiFi", s("net", True, True, True, True, 2025) == "clock_not_set")
    check("no TLS: CA and clock not needed", s("net", True, True, False, False, 2000) is None)
    check("all good: try WiFi", s("net", True, True, True, True, 2026) is None)

    f = sendpath.fail_reason
    check("join fails", f("join", True, 2000) == "wifi_join_failed")
    check("dns fails", f("dns", False, 3000) == "dns_failed")
    check("silent address is connect_timeout", f("connect", True, 0) == "connect_timeout")
    check("refused address is connect_failed", f("connect", False, 4000) == "connect_failed")
    check("bad certificate is tls_failed", f("tls", False, 3000) == "tls_failed")
    check("no ack is no_server_ack", f("ack", True, 0) == "no_server_ack")
    check("slow MQTT login out of time is budget_exceeded", f("mqtt", True, 0) == "budget_exceeded")
    check("bad MQTT login is connect_failed", f("mqtt", False, 3000) == "connect_failed")
    for step in ("join", "dns", "connect", "tls", "mqtt", "subscribe", "publish", "ack"):
        for t in (True, False):
            for left in (0, 1000):
                if f(step, t, left) not in sendpath.REASONS:
                    check("every reason is a known word", False, step)
                    return

    o = sendpath.lora_outcome
    check("LoRa confirmed buzzes ok", o("confirmed", False) == ("lora", "confirmed", True))
    check("LoRa no ack is not_confirmed, fail buzz", o("unconfirmed", True) == ("lora", "not_confirmed", False))
    check("acks off, sent", o("sent", False) == ("lora", "sent", True))
    check("nothing left the Fob: path none", o("failed", False) == ("none", "failed", False))
    check("broker had it, radio dead: never a false confirm",
          o("failed", True) == ("wifi", "not_confirmed", False))

    line = sendpath.result_line(213, "MEDICAL", "lora", "confirmed", 6210.4, "wifi_join_failed")
    check("SEND_RESULT line format",
          line == "SEND_RESULT ctr=213 kind=MEDICAL path=lora result=confirmed ms=6210 reason=wifi_join_failed", line)
    check("empty reason prints -", sendpath.result_line(1, "STATUS", "wifi", "confirmed", 840, "").endswith("reason=-"))
    p = sendpath.parse_result_line(line)
    check("SEND_RESULT parses back", p == {"ctr": "213", "kind": "MEDICAL", "path": "lora",
                                          "result": "confirmed", "ms": "6210", "reason": "wifi_join_failed"})

    der = bytes(range(256)) * 3
    import base64
    b64 = base64.b64encode(der)
    pem = b"-----BEGIN CERTIFICATE-----\n" + b"\n".join(b64[i:i + 64] for i in range(0, len(b64), 64)) \
        + b"\n-----END CERTIFICATE-----\n"
    check("PEM turns into the same DER", sendpath.pem_to_der(pem) == der)
    check("DER comes back unchanged", sendpath.pem_to_der(der) is der)


# ---------- the MQTT client against a fake broker ----------
class StreamSocket:
    """CPython socket with MicroPython's read()/write(), which umqtt_safe uses."""

    def __init__(self, *args):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, addr):
        self.s.connect(addr)

    def settimeout(self, t):
        self.s.settimeout(t)

    def setblocking(self, flag):
        self.s.setblocking(flag)

    def read(self, n):
        return self.s.recv(n)

    def write(self, data):
        self.s.sendall(bytes(data))
        return len(data)

    def close(self):
        self.s.close()


class FakeSocketModule:
    socket = StreamSocket


umqtt_safe.socket = FakeSocketModule


def _recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise OSError("closed")
        buf += chunk
    return buf


def _read_packet(conn):
    head = _recv_exact(conn, 1)[0]
    mult, size = 1, 0
    while True:
        b = _recv_exact(conn, 1)[0]
        size += (b & 0x7F) * mult
        mult *= 128
        if not b & 0x80:
            break
    return head, _recv_exact(conn, size)


def _publish_packet(topic, payload, pid=1):
    t = topic.encode()
    body = struct.pack("!H", len(t)) + t + struct.pack("!H", pid) + payload
    return bytes([0x32, len(body)]) + body


def fake_broker(mode, ack_text, port_box, ready, log):
    """mode: "ack" = answer properly and send the ack, "noack" = never ack,
    "silent" = accept TCP and say nothing, "wrongack" = send a wrong ack first."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port_box.append(srv.getsockname()[1])
    ready.set()
    conn, _ = srv.accept()
    conn.settimeout(10)
    try:
        if mode == "silent":
            time.sleep(3)
            return
        while True:
            head, body = _read_packet(conn)
            kind = head & 0xF0
            log.append(kind)
            if kind == 0x10:                                  # CONNECT
                conn.sendall(b"\x20\x02\x00\x00")
            elif kind == 0x80:                                # SUBSCRIBE
                pid = body[:2]
                conn.sendall(b"\x90\x03" + pid + b"\x01")
            elif kind == 0x30:                                # PUBLISH from the Fob
                tlen = struct.unpack("!H", body[:2])[0]
                pid = body[2 + tlen:4 + tlen]
                conn.sendall(b"\x40\x02" + pid)
                if mode == "wrongack":
                    conn.sendall(_publish_packet("safeping/ack/FOB-T", b"ACK FOB-T 7 0000000000000000", 9))
                if mode in ("ack", "wrongack"):
                    conn.sendall(_publish_packet("safeping/ack/FOB-T", ack_text.encode()))
            elif kind == 0xE0:                                # DISCONNECT
                return
    except OSError:
        pass
    finally:
        conn.close()
        srv.close()


def run_client(mode, budget_ms=5000, ack_wait_ms=2000):
    """What wifi_send() in main.py does, minus WiFi join, DNS and TLS."""
    key = ackcheck.ack_key(b"test-secret")
    sig = "ab" * 32
    expected = ackcheck.ack_text(key, "FOB-T", 7, sig)
    port, ready, log = [], threading.Event(), []
    th = threading.Thread(target=fake_broker, args=(mode, expected, port, ready, log), daemon=True)
    th.start()
    ready.wait(5)
    got, ignored = [], []

    def on_msg(topic, msg):
        if topic == b"safeping/ack/FOB-T" and msg.strip() == expected.encode():
            got.append(1)
        else:
            ignored.append(msg)

    budget = sendpath.Budget(budget_ms)
    client = umqtt_safe.MQTTClient("FOB-T", user="safeping-fob", password="placeholder", keepalive=30)
    client.set_callback(on_msg)
    confirmed, reason, published, detail, step = sendpath.mqtt_attempt(
        client, ("127.0.0.1", port[0]), budget, None, "localhost", "safeping/ack/FOB-T",
        "safeping/alert/FOB-T", b'{"v":1}', ack_wait_ms, got, umqtt_safe.step_parts)
    outcome = "confirmed" if confirmed else reason
    return outcome, budget.used(), log, ignored


def test_client():
    outcome, ms, log, ignored = run_client("ack")
    check("fake broker: signed ack confirms", outcome == "confirmed", "{} in {} ms".format(outcome, ms))
    check("subscribe happens before publish", log[:3] == [0x10, 0x80, 0x30], str([hex(x) for x in log]))

    outcome, ms, log, ignored = run_client("wrongack")
    check("a wrong ack is ignored, the right one still confirms",
          outcome == "confirmed" and len(ignored) == 1, outcome)

    outcome, ms, log, ignored = run_client("noack", budget_ms=5000, ack_wait_ms=600)
    check("no ack: no_server_ack after the ack wait", outcome == "no_server_ack" and 500 <= ms < 1500,
          "{} after {} ms".format(outcome, ms))

    outcome, ms, log, ignored = run_client("silent", budget_ms=1200)
    check("broker never answers: gives up inside the budget", outcome in ("budget_exceeded", "connect_timeout")
          and ms < 1200 + 400, "{} after {} ms".format(outcome, ms))


def main():
    test_rules()
    test_client()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
