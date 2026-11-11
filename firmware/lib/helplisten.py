""""Help is coming" over WiFi (message-format.md).

After an alert is confirmed over WiFi, the Fob keeps that MQTT connection open for
HELP_LISTEN_MS and waits for the server's signed "HELP <id> <ctr> <mac>" on
safeping/help/<id>. The server sends it when staff press Acknowledge.

HelpListener never blocks the Fob's loop: step() checks the socket without waiting and
reads only when a packet is there. Pings keep the connection open. The Fob calls close()
before any other send, because there is one MQTT connection at a time.

feedback(kind) is the rule for the buzz: three slow pulses, except SILENT (nothing, ever).

Pure logic with an injectable client and poll: tests/test_help.py runs it.
"""
try:
    from time import ticks_ms, ticks_diff, ticks_add     # MicroPython
except ImportError:                                       # the laptop
    import time as _time

    def ticks_ms():
        return int(_time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

    def ticks_add(a, b):
        return a + b

try:
    import select
except ImportError:                                       # pragma: no cover
    select = None

import ackcheck

PING_EVERY_MS = 20000         # the Fob's MQTT keepalive is 30 s
READ_MS = 1500                # time for one packet once the socket says data is there


def feedback(kind):
    """What the Fob does when help is coming: "help" (three slow pulses) or None.
    SILENT never buzzes and never lights."""
    return None if kind == "SILENT" else "help"


class SocketReady:
    """ready(sock): True if the socket has data to read. Never waits.

    The poller is made once per socket, not once per loop. Before 2026-11-11 this did
    "import select" and made a new poller every 10 ms. An import inside a function looks
    on the file system first (select can be replaced by a file), so that was a flash read
    every 10 ms for the whole 2 minutes. The Fob crashed with a cache error during it."""

    def __init__(self):
        self.sock = None
        self.poller = None

    def __call__(self, sock):
        try:
            if sock is not self.sock:
                self.poller = select.poll()
                self.poller.register(sock, select.POLLIN)
                self.sock = sock
            return bool(self.poller.poll(0))
        except Exception:
            return False

    def forget(self):
        self.sock = None
        self.poller = None


class HelpListener:
    def __init__(self, device_id, help_key, listen_ms, log=print, clock=None, diff=None, add=None,
                 ready=None):
        self.device_id = device_id
        self.key = help_key
        self.listen_ms = listen_ms
        self.log = log
        self.clock = clock or ticks_ms
        self.diff = diff or ticks_diff
        self.add_ms = add or ticks_add
        self.ready = ready or SocketReady()
        self.topic = ("safeping/help/" + device_id).encode()
        self.client = None
        self.waiting = {}          # ctr -> (kind, confirmed at, ms)
        self.next_ping = 0
        self.received = []         # (ctr, kind, ms_after_confirm) not yet played. The Fob pops them.

    def active(self):
        return self.client is not None

    def listen(self, client, ctr, kind, now=None):
        """Start (or keep) listening for help for ctr on this open MQTT client."""
        now = self.clock() if now is None else now
        if self.client is not None and self.client is not client:
            self.close("new connection")
        self.client = client
        client.set_callback(self.on_message)
        client.left_ms = lambda: READ_MS
        self.waiting[ctr] = (kind, now)
        self.next_ping = self.add_ms(now, PING_EVERY_MS)
        self.log("HELP_LISTEN ctr={} kind={} ms={}".format(ctr, kind, self.listen_ms))

    def attach(self, client, now=None):
        """Use a new open client for the alerts still waiting (after a STATUS or BOOT send
        closed the old one). Closes it at once if nothing is waiting."""
        now = self.clock() if now is None else now
        self.expire(now)
        if not self.waiting:
            self.client = client
            self.close("done")
            return
        self.client = client
        client.set_callback(self.on_message)
        client.left_ms = lambda: READ_MS
        self.next_ping = self.add_ms(now, PING_EVERY_MS)
        self.log("HELP_LISTEN again for ctr {}".format(",".join(str(c) for c in self.waiting)))

    def on_message(self, topic, msg):
        """MQTT callback. Also called for any message on the alert's connection."""
        if bytes(topic) != self.topic:
            return
        now = self.clock()
        ctr, reason = ackcheck.check_help(self.key, self.device_id, msg, self.waiting)
        if reason is not None:
            self.log("HELP ignored: {} ctr={}".format(reason, "-" if ctr is None else ctr))
            return
        kind, confirmed = self.waiting.pop(ctr)
        ms = self.diff(now, confirmed)
        self.log("HELP_RECEIVED ctr={} ms_after_confirm={}".format(ctr, ms))
        self.received.append((ctr, kind, ms))

    def send_on_connection(self, topic, payload, ack_topic, expected, wait_ms, stop=None):
        """Publish one message (a BOOT report sent late) on the open listening connection
        and wait up to wait_ms for the server's ack, so listening for help never stops.
        The connection is already subscribed to the ack topic (one SUBSCRIBE for ack and
        help). Help messages that come in meanwhile are handled as usual.
        Returns "confirmed", "stopped" (stop() said so) or "failed". After "failed" the
        connection may be closed (HELP_LISTEN_END reason=connection_lost)."""
        if self.client is None:
            return "failed"
        client = self.client
        got = []
        ack_topic = ack_topic.encode() if isinstance(ack_topic, str) else ack_topic

        def on_message(t, m):
            if bytes(t) == ack_topic and bytes(m).strip() == expected:
                got.append(True)
            else:
                self.on_message(t, m)

        end = self.add_ms(self.clock(), wait_ms)

        def left():
            if stop is not None and stop():
                return 0
            return max(0, self.diff(end, self.clock()))

        client.set_callback(on_message)
        client.left_ms = left
        result = "failed"
        try:
            client.publish(topic, payload, qos=1)
            while not got:
                client.wait_msg()
            result = "confirmed"
        except Exception as err:
            if got:
                result = "confirmed"
            elif stop is not None and stop():
                result = "stopped"
            else:
                self.log("HELP connection could not carry the message: {}".format(err))
        finally:
            if self.client is client:
                client.set_callback(self.on_message)
                client.left_ms = lambda: READ_MS
        if result != "confirmed" and self.client is client:
            # A timeout can cut a packet in half, so this connection is not trusted any more.
            self.client = None
            self._forget_poller()
            try:
                client.close()
            except Exception:
                pass
            self.log("HELP_LISTEN_END reason=connection_lost")
        return result

    def _forget_poller(self):
        forget = getattr(self.ready, "forget", None)
        if forget is not None:
            forget()

    def close(self, reason="closed"):
        """Drop the connection. Alerts still waiting stay in the list until they time out,
        so a later WiFi connection can pick them up again."""
        if self.client is None:
            return
        client, self.client = self.client, None
        self._forget_poller()
        try:
            client.left_ms = lambda: 300
            client.disconnect()
        except Exception:
            pass
        self.log("HELP_LISTEN_END reason={}".format(reason))

    def expire(self, now=None):
        """Forget alerts that waited listen_ms. Returns their ctrs."""
        now = self.clock() if now is None else now
        old = [c for c, (k, t) in self.waiting.items() if self.diff(now, t) >= self.listen_ms]
        for c in old:
            del self.waiting[c]
            self.log("HELP_TIMEOUT ctr={} ms={}".format(c, self.listen_ms))
        return old

    def step(self, now=None, can_send=True):
        """Call every loop. Never waits. can_send=False while the motor runs, so the ping
        (a WiFi transmit) waits for the motor to stop."""
        now = self.clock() if now is None else now
        self.expire(now)
        if self.client is None:
            return
        if not self.waiting:
            self.close("done")
            return
        try:
            if self.ready(self.client.sock):
                self.client.left_ms = lambda: READ_MS
                self.client.wait_msg()             # one packet: help, PINGRESP or anything else
                if not self.waiting:
                    self.close("done")
                    return
            if can_send and self.diff(now, self.next_ping) >= 0:
                self.client.left_ms = lambda: READ_MS
                self.client.ping()
                self.next_ping = self.add_ms(now, PING_EVERY_MS)
        except Exception as err:
            self.log("HELP listen error: {}".format(err))
            client, self.client = self.client, None
            self._forget_poller()
            try:
                client.close()                     # already broken: no goodbye packet
            except Exception:
                pass
            self.log("HELP_LISTEN_END reason=connection_lost")
