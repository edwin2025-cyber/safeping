# umqtt_safe.py: a small MQTT client for the SafePing Fob, with a timeout on every step.
#
# Based on umqtt.simple from micropython-lib (https://github.com/micropython/micropython-lib).
# Changes for SafePing:
#   - Every socket step has a timeout taken from a time budget (left_ms), so the Fob can
#     never hang on WiFi: TCP connect, the TLS handshake, every read and every write.
#   - TCP connect is non-blocking with poll(), so an address that never answers still
#     gives up on time.
#   - Errors say which step failed (StepError args), so the Fob can print a clear reason.
#   - Only what the Fob needs: connect, subscribe, publish (QoS 0 or 1), wait_msg, disconnect.
#
# Original license (micropython-lib, MIT):
#
# The MIT License (MIT)
#
# Copyright (c) 2013-2014 micropython-lib contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import socket
import struct

try:
    import select
except ImportError:
    select = None

EINPROGRESS = (115, 119)        # Linux and lwIP (ESP32) numbers for "connect still running"


class MQTTException(Exception):
    pass


class StepError(Exception):
    """Raised as StepError(step, detail, timed_out).
    step is "connect", "tls", "mqtt" or "io". detail is a message or the original error.
    timed_out is True when time ran out.
    No __init__ on purpose: MicroPython 1.27 has no Exception.__init__ to call, and it
    crashed the first press on 2026-11-10. Everything lives in err.args instead."""
    pass


def _fail(step, detail, timed_out=False):
    return StepError(step, detail, bool(timed_out))


def step_parts(err):
    """(step, detail, timed_out) of a StepError, or None for any other error."""
    if isinstance(err, StepError) and len(err.args) >= 3:
        return err.args[0], err.args[1], err.args[2]
    return None


def _is_timeout(err):
    parts = step_parts(err)
    if parts is not None:
        return parts[2]
    if isinstance(err, OSError) and err.args:
        return err.args[0] in (110, 116, 11, "timed out")    # ETIMEDOUT, ETIMEDOUT (lwIP), EAGAIN
    return "timed out" in str(err)


class MQTTClient:
    def __init__(self, client_id, user=None, password=None, keepalive=0):
        self.client_id = client_id
        self.user = user
        self.pswd = password
        self.keepalive = keepalive
        self.raw = None             # the TCP socket
        self.sock = None            # the TCP socket, or the TLS socket on top of it
        self.pid = 0
        self.cb = None
        self.left_ms = lambda: 5000

    # ---------- timeouts ----------
    def _timeout(self):
        """Set the socket timeout to what is left of the budget. No time left: stop here."""
        ms = self.left_ms()
        if ms <= 0:
            raise _fail("io", "time budget used up", True)
        seconds = ms / 1000
        for s in (self.raw, self.sock):
            if s is not None and hasattr(s, "settimeout"):
                try:
                    s.settimeout(seconds)
                except Exception:
                    pass

    def _read(self, n):
        """Read exactly n bytes, with a timeout before every read."""
        buf = b""
        while len(buf) < n:
            self._timeout()
            chunk = self.sock.read(n - len(buf))
            if chunk is None:
                continue
            if chunk == b"":
                raise _fail("io", "connection closed")
            buf += chunk
        return buf

    def _write(self, data, length=None):
        self._timeout()
        if length is not None:
            data = memoryview(data)[:length]
        self.sock.write(data)

    def _send_str(self, s):
        if isinstance(s, str):
            s = s.encode()
        self._write(struct.pack("!H", len(s)))
        self._write(s)

    def _recv_len(self):
        n = 0
        sh = 0
        while 1:
            b = self._read(1)[0]
            n |= (b & 0x7F) << sh
            if not b & 0x80:
                return n
            sh += 7

    # ---------- connect ----------
    def _tcp_connect(self, addr):
        self.raw = socket.socket()
        ms = self.left_ms()
        if ms <= 0:
            raise _fail("connect", "time budget used up", True)
        if select is None or not hasattr(select, "poll") or not hasattr(self.raw, "setblocking"):
            self._timeout()                         # before connect
            self.raw.connect(addr)
            return
        # Non-blocking connect + poll, so a silent address cannot hold us past the budget.
        self.raw.setblocking(False)
        try:
            self.raw.connect(addr)
        except OSError as err:
            if not err.args or err.args[0] not in EINPROGRESS:
                raise
        poller = select.poll()
        poller.register(self.raw, select.POLLOUT | select.POLLERR | select.POLLHUP)
        events = poller.poll(max(1, self.left_ms()))
        if not events:
            raise _fail("connect", "no answer", True)
        flags = events[0][1]
        if flags & (select.POLLERR | select.POLLHUP):
            raise _fail("connect", "refused or unreachable")
        self.raw.setblocking(True)
        self._timeout()

    def open(self, addr, left_ms, ssl_context=None, server_hostname=None):
        """TCP connect, then TLS if ssl_context is given. left_ms() gives the budget left."""
        self.left_ms = left_ms
        try:
            self._tcp_connect(addr)
        except StepError:
            self.close()
            raise
        except Exception as err:
            self.close()
            raise _fail("connect", err, _is_timeout(err))
        if ssl_context is None:
            self.sock = self.raw
            return
        try:
            self._timeout()                         # the handshake reads use this timeout
            self.sock = ssl_context.wrap_socket(self.raw, server_hostname=server_hostname)
            self._timeout()                         # after the TLS wrap
        except Exception as err:
            self.close()
            raise _fail("tls", err, _is_timeout(err))

    def connect(self, clean_session=True):
        """MQTT CONNECT and wait for CONNACK. open() first."""
        try:
            premsg = bytearray(b"\x10\0\0\0\0\0")
            msg = bytearray(b"\x04MQTT\x04\x02\0\0")
            sz = 10 + 2 + len(self.client_id)
            msg[6] = clean_session << 1
            if self.user:
                sz += 2 + len(self.user) + 2 + len(self.pswd)
                msg[6] |= 0xC0
            if self.keepalive:
                msg[7] |= self.keepalive >> 8
                msg[8] |= self.keepalive & 0x00FF
            i = 1
            while sz > 0x7F:
                premsg[i] = (sz & 0x7F) | 0x80
                sz >>= 7
                i += 1
            premsg[i] = sz
            self._write(premsg, i + 2)
            self._write(msg)
            self._send_str(self.client_id)
            if self.user:
                self._send_str(self.user)
                self._send_str(self.pswd)
            resp = self._read(4)
        except StepError as err:
            parts = step_parts(err)
            raise _fail("mqtt", parts[1], parts[2])
        except Exception as err:
            raise _fail("mqtt", err, _is_timeout(err))
        if resp[0] != 0x20 or resp[1] != 0x02:
            raise _fail("mqtt", "not an MQTT broker")
        if resp[3] != 0:
            # 4 = bad user name or password, 5 = not authorized
            raise _fail("mqtt", "broker refused the login (code {})".format(resp[3]))
        return resp[2] & 1

    def close(self):
        for s in (self.sock, self.raw):
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
        self.sock = None
        self.raw = None

    def disconnect(self):
        try:
            if self.sock is not None and self.left_ms() > 0:
                self._write(b"\xe0\0")
        except Exception:
            pass
        self.close()

    # ---------- messages ----------
    def set_callback(self, f):
        self.cb = f

    def publish(self, topic, msg, retain=False, qos=0):
        if isinstance(topic, str):
            topic = topic.encode()
        if isinstance(msg, str):
            msg = msg.encode()
        pkt = bytearray(b"\x30\0\0\0")
        pkt[0] |= qos << 1 | retain
        sz = 2 + len(topic) + len(msg)
        if qos > 0:
            sz += 2
        assert sz < 2097152
        i = 1
        while sz > 0x7F:
            pkt[i] = (sz & 0x7F) | 0x80
            sz >>= 7
            i += 1
        pkt[i] = sz
        self._write(pkt, i + 1)
        self._send_str(topic)
        if qos > 0:
            self.pid += 1
            pid = self.pid
            struct.pack_into("!H", pkt, 0, pid)
            self._write(pkt, 2)
        self._write(msg)
        if qos == 1:
            while 1:                              # wait for PUBACK, handling anything else
                op = self.wait_msg()
                if op == 0x40:
                    sz = self._read(1)
                    if sz != b"\x02":
                        raise _fail("mqtt", "bad PUBACK")
                    rcv_pid = self._read(2)
                    rcv_pid = rcv_pid[0] << 8 | rcv_pid[1]
                    if pid == rcv_pid:
                        return
        elif qos == 2:
            raise MQTTException("QoS 2 not supported")

    def subscribe(self, topic, qos=0):
        if isinstance(topic, str):
            topic = topic.encode()
        pkt = bytearray(b"\x82\0\0\0")
        self.pid += 1
        struct.pack_into("!BH", pkt, 1, 2 + 2 + len(topic) + 1, self.pid)
        self._write(pkt)
        self._send_str(topic)
        self._write(bytes([qos]))
        while 1:                                  # wait for SUBACK
            op = self.wait_msg()
            if op == 0x90:
                resp = self._read(4)
                if resp[1] != pkt[2] or resp[2] != pkt[3]:
                    raise _fail("mqtt", "bad SUBACK")
                if resp[3] == 0x80:
                    raise _fail("mqtt", "broker refused the subscription")
                return

    def subscribe_many(self, topics, qos=0):
        """Subscribe to several topics in ONE packet (no extra round trip). Returns the
        broker's answer for each topic: 0 or 1 = granted, 0x80 = refused. A refused topic
        does not raise here, so the caller decides which ones it really needs."""
        topics = [t.encode() if isinstance(t, str) else t for t in topics]
        self.pid += 1
        size = 2 + sum(2 + len(t) + 1 for t in topics)
        pkt = bytearray(b"\x82\0\0\0\0")
        i = 1
        while size > 0x7F:
            pkt[i] = (size & 0x7F) | 0x80
            size >>= 7
            i += 1
        pkt[i] = size
        struct.pack_into("!H", pkt, i + 1, self.pid)
        self._write(pkt, i + 3)
        for t in topics:
            self._send_str(t)
            self._write(bytes([qos]))
        while 1:                                  # wait for SUBACK
            op = self.wait_msg()
            if op == 0x90:
                n = self._recv_len()
                resp = self._read(n)
                if (resp[0] << 8 | resp[1]) != self.pid:
                    raise _fail("mqtt", "bad SUBACK")
                return list(resp[2:])

    def ping(self):
        """PINGREQ. The PINGRESP is read later by wait_msg()."""
        self._write(b"\xc0\0")

    def wait_msg(self):
        """Read one packet. A PUBLISH goes to the callback. Returns the packet type byte.
        Raises on timeout (from the budget) or a closed connection."""
        res = self._read(1)
        if res == b"\xd0":                        # PINGRESP
            self._read(1)
            return None
        op = res[0]
        if op & 0xF0 != 0x30:
            return op
        sz = self._recv_len()
        topic_len = self._read(2)
        topic_len = (topic_len[0] << 8) | topic_len[1]
        topic = self._read(topic_len)
        sz -= topic_len + 2
        pid = 0
        if op & 6:
            pid = self._read(2)
            pid = pid[0] << 8 | pid[1]
            sz -= 2
        msg = self._read(sz)
        if self.cb:
            self.cb(topic, msg)
        if op & 6 == 2:                           # QoS 1: say we got it
            pkt = bytearray(b"\x40\x02\0\0")
            struct.pack_into("!H", pkt, 2, pid)
            self._write(pkt)
        elif op & 6 == 4:
            raise MQTTException("QoS 2 not supported")
        return op
