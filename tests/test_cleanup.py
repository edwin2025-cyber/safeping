"""Laptop test for the 2026-11-15 Fob fixes (docs/env-sms-cleanup-changes.md). No board.

  1. A BOOT report that fails on both paths goes in the retry queue as the lowest kind:
     dropped first when the queue is full, tried after every alert, no light or buzz
     when it gets through. Also when it was stopped by a press and sent later.
  2. The external NeoPixel (LED_PIN_EXTERNAL): the same colors and patterns as the board
     LED, at LED_BRIGHTNESS_EXTERNAL percent. A pin already in use is refused.
  3. MicroPython 1.28 and later can write TLS errors as text ("MBEDTLS_ERR_SSL_TIMEOUT").
     The timeout check and the plain words still work, in sendpath.py and umqtt_safe.py.

  python tests/test_cleanup.py"""
import contextlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard       # noqa: E402
import retryq          # noqa: E402
import sendpath        # noqa: E402
import umqtt_safe      # noqa: E402

results = []
CHECKS_OK = {"key": "ok", "counter": "ok", "lora": "ok", "gps": "ok", "battery": "ok", "pressure": "ok", "wifi": "fail"}


def check(name, passed, detail=""):
    passed = bool(passed)
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + str(detail) if detail and not passed else ""))


def quiet(fn, *args, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args, **kw)
    return value, out.getvalue()


# ---------- 1. BOOT in the retry queue ----------
def test_queue_rank():
    clock = [0]
    q = retryq.RetryQueue(max_n=3, clock=lambda: clock[0], diff=lambda a, b: a - b, add=lambda a, b: a + b,
                          files=None)
    for i, kind in enumerate(["STATUS", "STATUS", "STATUS"]):
        q.add(i, kind, "p", "s")
    queued, dropped = q.add(10, "BOOT", "p", "s")
    check("queue full of STATUS: a new BOOT report is not queued (lowest of all)", not queued and dropped["ctr"] == 10)
    q2 = retryq.RetryQueue(max_n=2, clock=lambda: clock[0], diff=lambda a, b: a - b, add=lambda a, b: a + b)
    q2.add(1, "BOOT", "p", "s")
    q2.add(2, "SUSPICIOUS", "p", "s")
    queued, dropped = q2.add(3, "STATUS", "p", "s")
    check("queue full: the BOOT report is dropped first, even for a STATUS", queued and dropped["ctr"] == 1)
    q3 = retryq.RetryQueue(max_n=5, clock=lambda: clock[0], diff=lambda a, b: a - b, add=lambda a, b: a + b)
    q3.add(1, "BOOT", "p", "s")
    q3.add(2, "STATUS", "p", "s")
    clock[0] = 10 ** 6 // 10
    check("an alert is tried before the BOOT report", q3.next_due()["kind"] == "STATUS")


def test_fob_boot_retry():
    main = fakeboard.load_fob(workdir=tempfile.mkdtemp())
    fob = main.Fob()
    fob.help = None
    calls = []

    def fail(kind, payload, ctr, sig, budget=None, stop=None, try_no=None):
        calls.append((kind, ctr, try_no))
        return False, "not_confirmed", "wifi_join_failed"
    fob.deliver = fail
    _, log = quiet(fob.send_boot_report, CHECKS_OK)
    entries = fob.queue.entries
    check("BOOT report failed on both paths: it is in the retry queue", len(entries) == 1
          and entries[0]["kind"] == "BOOT", entries)
    msg = json.loads(entries[0]["payload"])
    check("the queued BOOT is the same signed message", msg["type"] == "BOOT" and msg["ctr"] == entries[0]["ctr"]
          and msg["sig"] == entries[0]["sig"])
    check("RETRY_QUEUED line for the BOOT report", "RETRY_QUEUED ctr={} kind=BOOT".format(msg["ctr"]) in log, log)
    with open("queue.json") as f:
        check("kept in flash (queue.json) like an alert", json.load(f)["entries"][0]["kind"] == "BOOT")

    shown = []
    fob.show_result = lambda kind, ok: shown.append(kind)
    fob.deliver = lambda kind, payload, ctr, sig, budget=None, stop=None, try_no=None: (True, "confirmed", "-")
    entries[0]["next"] = fakeboard.clock[0]
    _, log = quiet(fob.run_retries)
    check("the retry gets through: RETRY_DONE", "RETRY_DONE ctr={} kind=BOOT".format(msg["ctr"]) in log, log)
    check("no light or buzz for a BOOT report that got through", shown == [], shown)
    check("queue empty after", len(fob.queue) == 0)

    # stopped by a press, sent later, fails again: queued too
    fob.deliver = fail
    fob.boot_pending = ('{"v": 1, "type": "BOOT", "ctr": 77, "ts": 1794754800}', 77, "f" * 64)
    _, log = quiet(fob.resend_boot)
    check("a BOOT report sent later that fails is queued too",
          any(e["ctr"] == 77 and e["kind"] == "BOOT" and e["wall"] == 1794754800 for e in fob.queue.entries),
          fob.queue.entries)

    # a full queue of alerts: the BOOT report is not queued, alerts are untouched
    main2 = fakeboard.load_fob({"RETRY_MAX": 2}, workdir=tempfile.mkdtemp())
    fob2 = main2.Fob()
    fob2.help = None
    fob2.queue.add(500, "MEDICAL", "{}", "s")
    fob2.queue.add(501, "SILENT", "{}", "s")
    fob2.deliver = fail
    _, log = quiet(fob2.send_boot_report, CHECKS_OK)
    check("queue full of alerts: the BOOT report gives way, alerts stay",
          [e["ctr"] for e in fob2.queue.entries] == [500, 501] and "RETRY_GAVE_UP" in log, log)


# ---------- 2. the external NeoPixel ----------
def test_external_led():
    main = fakeboard.load_fob({"LED_PIN_EXTERNAL": 4, "LED_BRIGHTNESS_EXTERNAL": 30}, workdir=tempfile.mkdtemp())
    led = main.Led()
    check("external pixel set up on its pin", led.external is not None)
    led.show(main.GREEN)
    check("same color as the board LED, at 30 percent",
          led.pixel[0] == (0, 255, 0) and led.external[0] == (0, 76, 0), (led.pixel[0], led.external[0]))
    led.show(main.ORANGE, 150, 150)
    seen = set()
    for t in range(0, 600, 50):
        led.update(fakeboard.clock[0] + t)
        seen.add(led.external[0])
    check("blink patterns run on the external pixel too", (0, 0, 0) in seen and (76, 13, 0) in seen, seen)
    led.scale = 40                                  # low battery dims both
    led.shown = None
    led.show(main.WHITE)
    check("low battery dims the external pixel too", led.external[0] == (30, 30, 30), led.external[0])
    led.off()
    check("off is off on both", led.pixel[0] == (0, 0, 0) and led.external[0] == (0, 0, 0))

    main2 = fakeboard.load_fob({"LED_PIN_EXTERNAL": 3}, workdir=tempfile.mkdtemp())
    led2, log = quiet(main2.Led)
    check("a pin already in use (the motor) is refused", led2.external is None
          and "LED_PIN_EXTERNAL 3 is already the motor" in log, log)
    main3 = fakeboard.load_fob(workdir=tempfile.mkdtemp())
    check("not set: no external pixel, the board LED works as before",
          main3.LED_PIN_EXTERNAL is None and main3.Led().external is None)


# ---------- 3. TLS errors as text (MicroPython 1.28 and later) ----------
def test_tls_error_text():
    cases = [
        (OSError(-26624, "MBEDTLS_ERR_SSL_TIMEOUT"), True),
        (OSError("MBEDTLS_ERR_SSL_TIMEOUT"), True),
        (OSError(-26624), True),
        (OSError(110), True),
        (OSError("timed out"), True),
        (OSError(-9984, "MBEDTLS_ERR_X509_CERT_VERIFY_FAILED"), False),
        (OSError(104), False),
    ]
    for err, want in cases:
        check("sendpath.is_timeout({!r}) is {}".format(err.args, want), sendpath.is_timeout(err) == want)
        check("umqtt_safe._is_timeout({!r}) is {}".format(err.args, want), umqtt_safe._is_timeout(err) == want)
    check("plain words for a certificate error given as number and text",
          sendpath.plain_error(OSError(-9984, "MBEDTLS_ERR_X509_CERT_VERIFY_FAILED")).startswith(
              "the broker's certificate did not check out"))
    check("plain words for a certificate error given as text only",
          sendpath.plain_error(OSError("MBEDTLS_ERR_X509_CERT_VERIFY_FAILED")).startswith(
              "the broker's certificate did not check out"))
    check("plain words for a TLS timeout given as text",
          sendpath.plain_error(OSError("MBEDTLS_ERR_SSL_TIMEOUT")).startswith("the secure connection timed out"))
    check("the old number-only errors read the same as before",
          sendpath.plain_error(OSError(111)).startswith("the broker refused the connection"))
    step, timed_out, _ = sendpath.classify_error("tls", OSError("MBEDTLS_ERR_SSL_TIMEOUT"))
    check("a TLS timeout given as text counts as timed out, reason tls_failed",
          timed_out is True and sendpath.fail_reason(step, timed_out, 1000) == "tls_failed")


def main():
    test_queue_rank()
    test_fob_boot_retry()
    test_external_led()
    test_tls_error_text()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
