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
    "wifi_off", "wifi_join_failed", "dns_failed", "tls_failed", "connect_timeout",
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
