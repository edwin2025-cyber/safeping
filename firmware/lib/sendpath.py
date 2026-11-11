"""The Fob's send rules as small pure functions, so they can be tested on the laptop
(tests/test_sendpath.py) as well as run on the board. No pins, no radio, no WiFi here.

  Budget          the time limit for the whole WiFi attempt
  skip_reason()   should this press skip WiFi, and why
  fail_reason()   turn a failed WiFi step into one short reason word
  lora_outcome()  turn the LoRa result into path, result and "ok" for the buzz
  result_line()   the one SEND_RESULT line printed after every send
  pem_to_der()    the CA certificate as DER, if the board's ssl wants DER
"""
import binascii

try:
    from time import ticks_ms, ticks_diff             # MicroPython
except ImportError:                                    # the laptop
    import time as _time

    def ticks_ms():
        return int(_time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

# Every reason a SEND_RESULT line can give. "-" means WiFi worked.
REASONS = (
    "wifi_off", "wifi_join_failed", "wifi_state_error", "dns_failed", "tls_failed", "connect_timeout",
    "connect_failed", "no_server_ack", "clock_not_set", "ca_missing", "ackcheck_missing",
    "budget_exceeded", "-",
)
MIN_YEAR = 2026            # a clock before this has not been set (TLS needs the date)


class Budget:
    """A time limit that starts now. clock() returns milliseconds (injectable for tests)."""

    def __init__(self, total_ms, clock=None, diff=None):
        self.clock = clock or ticks_ms
        self.diff = diff or ticks_diff
        self.start = self.clock()
        self.total = total_ms

    def used(self):
        return self.diff(self.clock(), self.start)

    def left(self, cap=None):
        """Milliseconds left, never below 0. cap limits it further (one step's own limit)."""
        left = max(0, self.total - self.used())
        return left if cap is None else max(0, min(left, cap))


def wifi_off(ssid):
    return not ssid or str(ssid).strip().lower() == "none"


def skip_reason(ssid, have_mqtt, have_ackcheck, tls, ca_present, year):
    """Why this press goes straight to LoRa, or None to try WiFi.
    Checked in this order, cheapest and most certain first."""
    if wifi_off(ssid):
        return "wifi_off"
    if not have_ackcheck:
        return "ackcheck_missing"          # without it a WiFi send can never be confirmed
    if not have_mqtt:
        return "connect_failed"            # umqtt_safe.py is not on the board
    if tls and not ca_present:
        return "ca_missing"
    if tls and (year is None or year < MIN_YEAR):
        return "clock_not_set"
    return None


def fail_reason(step, timed_out, budget_left_ms):
    """One reason word for a failed WiFi step.
    step is "join", "dns", "connect", "tls", "mqtt", "subscribe", "publish" or "ack".
    The step's own reason wins (a silent broker address is connect_timeout even though
    it used up the budget). budget_exceeded is for the later MQTT steps running out."""
    if step == "join":
        return "wifi_join_failed"
    if step == "dns":
        return "dns_failed"
    if step == "tls":
        return "tls_failed"
    if step == "ack":
        return "no_server_ack"
    if step == "connect":
        return "connect_timeout" if timed_out else "connect_failed"
    # mqtt login, subscribe or publish
    if timed_out:
        return "budget_exceeded" if budget_left_ms <= 0 else "connect_timeout"
    return "connect_failed"


def is_timeout(err):
    """True if an error means time ran out (MicroPython or laptop)."""
    if isinstance(err, OSError) and err.args:
        if err.args[0] in (110, 116, 11, "timed out"):    # ETIMEDOUT, ETIMEDOUT (lwIP), EAGAIN
            return True
    return "timed out" in str(err).lower()


def classify_error(step, err, step_parts=None):
    """Which step really failed, whether it timed out, and the detail, for an error caught
    during the WiFi attempt. step is the step main.py was on. step_parts is
    umqtt_safe.step_parts (it reads a StepError's args). Returns (step, timed_out, detail).
    A StepError from the client's own connect or TLS step wins over main.py's step."""
    parts = step_parts(err) if step_parts is not None else None
    if parts is not None:
        inner_step, detail, timed_out = parts
        if inner_step in ("connect", "tls"):
            step = inner_step
        return step, bool(timed_out), detail
    return step, is_timeout(err), err


# Plain words for each reason, printed when WiFi was not used or failed.
PLAIN = {
    "wifi_off": "WiFi is switched off in config.py (WIFI_SSID is none)",
    "wifi_join_failed": "could not join the WiFi network (wrong name or password, or out of range)",
    "wifi_state_error": "the WiFi chip was stuck (Wifi Internal State Error), and a reset did not fix it in time",
    "dns_failed": "could not look up the broker's address (DNS)",
    "tls_failed": "the secure connection to the broker failed (CA file, certificate or clock)",
    "connect_timeout": "the broker did not answer in time",
    "connect_failed": "the broker could not be reached or refused the connection or login",
    "no_server_ack": "the broker took the alert, but the server did not confirm it in time",
    "clock_not_set": "the clock is not set yet, and the secure connection needs the date",
    "ca_missing": "the broker's CA file is missing on the Fob",
    "ackcheck_missing": "ackcheck.py is missing, so a WiFi send could never be confirmed",
    "budget_exceeded": "the WiFi attempt ran out of time",
}

# Plain words for common error numbers (lwIP and mbedTLS on the board, Linux on the laptop).
ERRNO_WORDS = {
    11: "no answer yet (timed out)",
    104: "the broker reset the connection",
    110: "timed out",
    111: "the broker refused the connection",
    113: "no route to the broker",
    116: "timed out",
    118: "no route to the broker",
    119: "still connecting when time ran out",
    -9984: "the broker's certificate did not check out (CA file or clock)",
    -29312: "the broker closed the secure connection",
    -30592: "the secure handshake failed",
}


def plain_error(detail):
    """A short plain description of an error or message, with the original kept in brackets."""
    if isinstance(detail, OSError) and detail.args and detail.args[0] in ERRNO_WORDS:
        return "{} ({})".format(ERRNO_WORDS[detail.args[0]], detail)
    return str(detail)


def plain_reason(reason, detail=None):
    text = PLAIN.get(reason, reason)
    if detail is not None and str(detail):
        text += ": " + plain_error(detail)
    return text


MIN_JOIN_AFTER_RESET_MS = 1000     # a reset is only worth it if a join still fits after it


def is_wifi_state_error(err):
    """The ESP32 WiFi driver's "Wifi Internal State Error" (seen 2026-11-11 after several
    failed joins in a row). MicroPython raises it as OSError with that text."""
    return "internal state error" in str(err).lower()


def join_wifi(budget, join_ms, start, wait, reset, reset_ms, log=None):
    """Join WiFi inside the budget, with one reset if the driver is stuck.

    start()     starts a join (may raise)
    wait(ms)    waits up to ms, True if connected
    reset()     disconnect, radio off, short wait, radio on (may raise)
    reset_ms    how long reset() takes
    Returns (connected, reason, detail).

    A state error is fixed by one reset and one more try, but only if the reset and a
    join still fit in the budget. If the press ends without WiFi after a state error,
    the reason is wifi_state_error, so it shows in SEND_RESULT."""
    state_error = None
    for attempt in (1, 2):
        try:
            start()
        except Exception as err:
            if not is_wifi_state_error(err):
                return False, "wifi_join_failed", err
            state_error = err
            if attempt == 2:
                return False, "wifi_state_error", err
            if budget.left() < reset_ms + MIN_JOIN_AFTER_RESET_MS:
                if log:
                    log("WiFi state error, no time left for a WiFi reset")
                return False, "wifi_state_error", err
            if log:
                log("WiFi state error, resetting WiFi and trying once more")
            try:
                reset()
            except Exception as err2:
                return False, "wifi_state_error", err2
            continue
        if wait(budget.left(join_ms)):
            return True, "-", None
        if state_error is not None:
            return False, "wifi_state_error", "the join after the WiFi reset did not connect"
        return False, "wifi_join_failed", None
    return False, "wifi_state_error", state_error


def mqtt_attempt(client, addr, budget, ssl_context, host, ack_topic, alert_topic, payload,
                 ack_wait_ms, got, step_parts=None, help_topic=None, keep_open=None, stop=None):
    """The MQTT half of a WiFi send, after the WiFi join and DNS: TCP connect, TLS, login,
    subscribe to the ack topic, publish, then wait for the server's ack.

    client is an umqtt_safe.MQTTClient whose callback appends to got when the right ack
    arrives. Every error is turned into a reason here, so the board and the laptop test
    run the same code. Disconnects, except as below.

    help_topic: also subscribe to it, in the same packet as the ack topic. If the broker
    refuses only that topic, the alert still goes out (the Fob just cannot hear "help").
    keep_open: a list. When given, the help topic was granted and the alert is confirmed,
    the client is left connected and appended to it (the caller then owns it).
    stop: a function. While it returns True, the time left is 0, so the attempt ends at
    its next step (a button press during a retry).
    Returns (confirmed, reason, published, detail, step)."""
    step = "connect"
    published = False
    ack_total = 0
    help_ok = False
    open_after = False
    left = budget.left
    if stop is not None:
        left = lambda cap=None: 0 if stop() else budget.left(cap)    # noqa: E731
    try:
        client.open(addr, left, ssl_context, host)              # TCP, then TLS
        step = "mqtt"
        client.connect()
        step = "subscribe"
        if help_topic is None:
            client.subscribe(ack_topic, qos=1)                 # subscribe BEFORE publishing
        else:
            codes = client.subscribe_many([ack_topic, help_topic], qos=1)
            if not codes or codes[0] == 0x80:
                raise ValueError("broker refused the subscription")
            help_ok = len(codes) > 1 and codes[1] != 0x80
            if not help_ok:
                print("help topic refused by the broker (EMQX permission), no help buzz this time")
        step = "publish"
        client.publish(alert_topic, payload, qos=1)            # returns at the broker's PUBACK
        published = True
        step = "ack"
        ack_budget = Budget(budget.left(ack_wait_ms))
        ack_total = ack_budget.total
        client.left_ms = ack_budget.left if stop is None else (
            lambda: 0 if stop() else ack_budget.left())
        while not got:
            client.wait_msg()                                  # raises when the wait is over
        open_after = help_ok and keep_open is not None
        return True, "-", True, None, step
    except Exception as err:
        if got:                     # the ack came in, then something failed: still confirmed
            return True, "-", True, None, step
        step, timed_out, detail = classify_error(step, err, step_parts)
        if step == "ack":
            detail = "no ack from server within {} ms".format(ack_total)
        return False, fail_reason(step, timed_out, budget.left()), published, detail, step
    finally:
        if open_after:
            keep_open.append(client)
        else:
            try:
                client.disconnect()
            except Exception:
                pass


def lora_outcome(lora_result, wifi_published):
    """lora_result is what lora_send_confirmed() returned.
    wifi_published is True if the broker took the message but the server never acked.
    Returns (path, result, ok). ok decides the buzz: True only when confirmed, or when
    acks are switched off and it was sent (the old behavior)."""
    if lora_result == "confirmed":
        return "lora", "confirmed", True
    if lora_result == "sent":
        return "lora", "sent", True
    if lora_result == "unconfirmed":
        return "lora", "not_confirmed", False
    # the radio could not send at all
    if wifi_published:
        return "wifi", "not_confirmed", False
    return "none", "failed", False


def result_line(ctr, kind, path, result, ms, reason):
    return "SEND_RESULT ctr={} kind={} path={} result={} ms={} reason={}".format(
        ctr, kind, path, result, int(ms), reason or "-")


def parse_result_line(line):
    """The fields of a SEND_RESULT line as a dict, or None. Used by tests/field_log.py."""
    if not line.startswith("SEND_RESULT "):
        return None
    out = {}
    for part in line.split()[1:]:
        if "=" in part:
            name, value = part.split("=", 1)
            out[name] = value
    return out


def pem_to_der(data):
    """The first certificate in a PEM file as DER bytes. DER input comes back unchanged."""
    begin = b"-----BEGIN CERTIFICATE-----"
    end = b"-----END CERTIFICATE-----"
    start = data.find(begin)
    if start < 0:
        return data
    stop = data.find(end, start)
    if stop < 0:
        raise ValueError("PEM file has no END line")
    body = data[start + len(begin):stop]
    body = b"".join(body.split())                      # drop line breaks and spaces
    return binascii.a2b_base64(body)
