"""Text messages through Textbelt (replaces the old SMS dry run in notify.py).

Settings (safeping.env or environment variables, see docs/how-to-run.md):
    SAFEPING_SMS               off, dry (print the text, send nothing; the default) or live
    TEXTBELT_KEY               the Textbelt key (live only)
    SAFEPING_SMS_TO            10-digit numbers, comma separated
    SAFEPING_SMS_MAX_PER_HOUR  at most this many texts in any hour, all alerts together (20)

Sent for MEDICAL, SUSPICIOUS and SILENT only, and only from processor.process() after a
new alert is saved, so a duplicate, a replay, STATUS, BOOT, REF or SURVEY never gets here.
Works the same from the MQTT listener and the serial bridge (the state is in the database).

Protecting credits:
    - one text per alert per number (sms_sent, one row per alert and number, claimed
      before the request goes out)
    - at most SAFEPING_SMS_MAX_PER_HOUR texts tried in the last hour. Over it: logged, not sent
"Reply STOP to opt out" goes only on the first text a number ever gets (sms_numbers).

The key is never printed, logged or stored. Numbers are shown as their last 2 digits, and
stored only as a hash and the last 2 digits. A failed text never stops the alert, the
ack or Pushover: it is printed and kept for Settings > Health > Text messages.
"""
import hashlib
import json
import os
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

import config
import db
import pushover

CHANNEL = "sms"
TYPES = ("MEDICAL", "SUSPICIOUS", "SILENT")
SENDER = "SafePing"
MAX_CHARS = 160               # one text (plain GSM characters)
STOP_LINE = " Reply STOP to opt out"
MAX_ERROR = 200

# Live texts are never sent while the database is a test database in the temp folder
# (every test uses one), so a TEXTBELT_KEY left in the terminal cannot text anyone during
# a test. tests/test_textbelt.py turns this on, pointed at its fake Textbelt.
ALLOW_LIVE_ON_TEST_DB = False

_said = {"announce": False, "test_db": False}


def _test_db():
    tmp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    path = os.path.normcase(os.path.realpath(config.DB_PATH))
    return path.startswith(tmp.rstrip("\\/") + os.sep)


def mode():
    """off, dry or live, as it really runs (live on a test database runs as dry)."""
    if config.SMS_MODE == "live" and _test_db() and not ALLOW_LIVE_ON_TEST_DB:
        if not _said["test_db"]:
            _said["test_db"] = True
            print("[SMS] live mode ignored: the database is a test database in the temp folder. Running as dry.")
        return "dry"
    return config.SMS_MODE


def shown(number):
    return "..." + number[-2:]


def phone_hash(number):
    return hashlib.sha256(("safeping-sms|" + number).encode()).hexdigest()


def announce():
    """One line at program start: the mode, the numbers (last 2 digits) and the cap."""
    m = mode()
    nums = ", ".join(shown(n) for n in config.SMS_TO) or "none"
    if config.SMS_MODE_GIVEN and config.SMS_MODE_GIVEN.lower() not in ("off", "dry", "live"):
        print("[SMS] SAFEPING_SMS is not off, dry or live, so it runs as dry")
    if config.SMS_TO_SKIPPED > 0:
        print("[SMS] {} entr{} in SAFEPING_SMS_TO skipped (not a 10-digit number)".format(
            config.SMS_TO_SKIPPED, "y" if config.SMS_TO_SKIPPED == 1 else "ies"))
    if m == "off":
        print("[SMS] off (SAFEPING_SMS=off)")
    elif m == "dry":
        print("[SMS] dry run: texts are printed, not sent. Numbers: {}".format(nums))
    elif not config.TEXTBELT_KEY:
        print("[SMS] live, but TEXTBELT_KEY is not set: no text will go out")
    else:
        print("[SMS] live through Textbelt. Numbers: {}. At most {} texts per hour".format(
            nums, config.SMS_MAX_PER_HOUR))
    _said["announce"] = True


# ---------- the text ----------
def _ascii(text):
    """Plain characters only, so the text stays one 160-character message."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(ch for ch in text if 32 <= ord(ch) < 127)


def _clock(ts, ref):
    """2:31 PM, with the date in front when ts is not on the same day as ref."""
    t = time.localtime(ts)
    text = time.strftime("%I:%M %p", t).lstrip("0")
    if time.strftime("%Y-%m-%d", t) != time.strftime("%Y-%m-%d", time.localtime(ref)):
        text = time.strftime("%b %d", t).replace(" 0", " ") + " " + text
    return text


def _cut(text, n):
    if len(text) <= n:
        return text
    return text[:max(0, n - 3)].rstrip() + "..." if n > 3 else text[:n]


def build(alert_type, student_name, device_id, loc, received_at, pressed_at, late, first):
    """The text, at most 160 characters. Name and place are shortened if needed."""
    head = "SafePing {}: ".format(alert_type)
    if pressed_at is not None:
        when = " Pressed {}.".format(_clock(pressed_at, received_at))
        if late:
            when = " Pressed {}, arrived late at {}.".format(_clock(pressed_at, received_at),
                                                          _clock(received_at, received_at))
    else:
        when = " Press time unknown, received {}.".format(_clock(received_at, received_at))
    stop = STOP_LINE if first else ""
    name = _ascii(student_name or "")
    dev = _ascii(device_id)
    place = _ascii(pushover.where_words(loc) or "Place unknown")
    room = MAX_CHARS - len(head) - len(when) - len(stop)
    # who is "Name (FOB-001)." and place is " Place."
    def who_text(nm):
        return "{} ({}).".format(nm, dev) if nm else "{}.".format(dev)
    place_room = room - len(who_text(name)) - 2
    if place_room < 20:                          # keep at least 20 characters of place
        name = _cut(name, max(4, len(name) - (20 - place_room)))
        place_room = room - len(who_text(name)) - 2
    body = head + who_text(name) + " " + _cut(place, max(0, place_room)) + "." + when + stop
    return body[:MAX_CHARS]


# ---------- sending ----------
def _clean(text):
    text = str(text)
    if config.TEXTBELT_KEY:
        text = text.replace(config.TEXTBELT_KEY, "(hidden)")
    for number in config.SMS_TO:
        text = text.replace(number, shown(number))
    return " ".join(text.split())[:MAX_ERROR]


def _post(number, message):
    """One request. Returns (ok, text_id, error, quota_remaining)."""
    data = urllib.parse.urlencode({"phone": number, "message": message, "sender": SENDER,
                                   "key": config.TEXTBELT_KEY}).encode()
    req = urllib.request.Request(config.TEXTBELT_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=config.TEXTBELT_TIMEOUT_S) as resp:
            reply = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as error:
        try:
            reply = json.loads(error.read().decode("utf-8", "replace") or "{}")
        except ValueError:
            return False, None, "HTTP {}".format(error.code), None
    except urllib.error.URLError as error:
        return False, None, "no connection: {}".format(error.reason), None
    except (OSError, ValueError) as error:
        return False, None, "{}: {}".format(type(error).__name__, error), None
    quota = reply.get("quotaRemaining")
    quota = quota if isinstance(quota, int) and not isinstance(quota, bool) else None
    text_id = reply.get("textId")
    if reply.get("success") is True:
        return True, None if text_id is None else str(text_id), None, quota
    return False, None, "refused: {}".format(reply.get("error") or "no success"), quota


def _record_error(alert_id, error, at):
    try:
        db.record_notify(CHANNEL, at, alert_id, error)
    except Exception as db_error:
        print("[SMS] could not save the result: {}".format(db_error))


def send(alert_id, alert_type, student_name, device_id, loc, received_at, pressed_at, late, now=None):
    """Returns None (not a type that is texted), "off", "dry_run", "sent" (at least one
    number got it), "capped", "failed" or "already" (every number had it already).
    Never raises."""
    if alert_type not in TYPES:
        return None
    now = time.time() if now is None else now
    try:
        return _send(alert_id, alert_type, student_name, device_id, loc, received_at, pressed_at, late, now)
    except Exception as unexpected:              # a text must never stop an alert
        error = _clean("{}: {}".format(type(unexpected).__name__, unexpected))
        print("[SMS failed] alert {}: {}".format(alert_id, error))
        _record_error(alert_id, error, now)
        return "failed"


def _send(alert_id, alert_type, student_name, device_id, loc, received_at, pressed_at, late, now):
    m = mode()
    if m == "off":
        return "off"
    if not config.SMS_TO:
        body = build(alert_type, student_name, device_id, loc, received_at, pressed_at, late, False)
        if m == "dry":
            print("[SMS dry run] (no SAFEPING_SMS_TO) " + body)
            return "dry_run"
        print("[SMS failed] alert {}: no numbers in SAFEPING_SMS_TO".format(alert_id))
        _record_error(alert_id, "no numbers in SAFEPING_SMS_TO", now)
        return "failed"
    results = []
    for number in config.SMS_TO:
        h = phone_hash(number)
        first = not db.sms_number_known(h)
        body = build(alert_type, student_name, device_id, loc, received_at, pressed_at, late, first)
        if m == "dry":
            print("[SMS dry run] to {}: {}".format(shown(number), body))
            results.append("dry_run")
            continue
        if not config.TEXTBELT_KEY:
            print("[SMS failed] alert {}: TEXTBELT_KEY not set".format(alert_id))
            _record_error(alert_id, "TEXTBELT_KEY not set", now)
            return "failed"
        if db.sms_count_since(now - 3600) >= config.SMS_MAX_PER_HOUR:
            error = "hourly cap of {} texts reached".format(config.SMS_MAX_PER_HOUR)
            print("[SMS] {}: alert {} not texted to {}".format(error, alert_id, shown(number)))
            _record_error(alert_id, error, now)
            results.append("capped")
            continue
        if not db.sms_claim(alert_id, h, number[-2:], now):
            results.append("already")                # this alert went to this number before
            continue
        ok, text_id, error, quota = _post(number, body)
        error = None if error is None else _clean(error)
        db.sms_result(alert_id, h, ok, text_id, error, quota)
        if quota is not None:
            db.set_notify_quota(CHANNEL, quota)
        if ok:
            db.sms_number_seen(h, now)
            db.record_notify(CHANNEL, now, alert_id)
            print("[SMS] alert {} sent to {} (text {}, {} credits left)".format(
                alert_id, shown(number), text_id or "-", "?" if quota is None else quota))
            results.append("sent")
        else:
            print("[SMS failed] alert {} to {}: {}".format(alert_id, shown(number), error))
            _record_error(alert_id, error, now)
            results.append("failed")
    for word in ("sent", "dry_run", "capped", "failed"):
        if word in results:
            return word
    return "already"


def health(now=None):
    """Settings > Health > Text messages."""
    now = time.time() if now is None else now
    row = db.notify_status(CHANNEL) or {}

    def age(key):
        return None if row.get(key) is None else max(0, round(now - row[key]))

    quota = row.get("quota")
    return {
        "mode": mode(),
        "numbers": len(config.SMS_TO),
        "key_set": bool(config.TEXTBELT_KEY),
        "max_per_hour": config.SMS_MAX_PER_HOUR,
        "tried_last_hour": db.sms_count_since(now - 3600),
        "last_send_age_s": age("last_send_at"),
        "last_send_alert": row.get("last_send_alert"),
        "last_error_age_s": age("last_error_at"),
        "last_error_alert": row.get("last_error_alert"),
        "last_error": row.get("last_error"),
        "quota_remaining": quota,
        "quota_low": quota is not None and quota < config.SMS_QUOTA_LOW,
        "failing": row.get("last_error_at") is not None
                   and (row.get("last_send_at") is None or row["last_error_at"] > row["last_send_at"]),
    }
