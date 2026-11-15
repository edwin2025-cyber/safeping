"""Pushover phone notifications, sent before the text message (textbelt.py).

Settings (environment variables, see docs/how-to-run.md):
    SAFEPING_PUSHOVER_USER    the user or group key
    SAFEPING_PUSHOVER_TOKEN   the application token
    SAFEPING_PUBLIC_URL       optional, the dashboard address, for a link to the alert
If either Pushover value is missing, the server logs "Pushover off" once and keeps going.

Sent for MEDICAL, SUSPICIOUS and SILENT only. Never STATUS or BOOT.
processor.process() calls send() only after a new alert is saved, so a duplicate or a
replay never reaches it.
    MEDICAL     emergency priority: repeats every 60 s until someone acknowledges it
                in the Pushover app, for at most 30 minutes
    SUSPICIOUS  high priority
    SILENT      normal priority, no sound

The last send and the last error are kept in the database (notify_status) for
Settings > Health. The keys are never printed, logged or stored."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import db
import places
import stats

CHANNEL = "pushover"
TYPES = ("MEDICAL", "SUSPICIOUS", "SILENT")
EMERGENCY_RETRY_S = 60
EMERGENCY_EXPIRE_S = 30 * 60
MAX_MESSAGE = 1024           # Pushover's limit
MAX_ERROR = 200              # longest error text kept for Health

_said_off = [False]


def enabled():
    return bool(config.PUSHOVER_USER and config.PUSHOVER_TOKEN)


def announce():
    """One line at program start. "Pushover off" is printed at most once per program."""
    if enabled():
        print("[Pushover] on" + ("" if config.PUBLIC_URL else " (no SAFEPING_PUBLIC_URL, so no dashboard link)"))
    elif not _said_off[0]:
        _said_off[0] = True
        print("[Pushover] Pushover off (SAFEPING_PUSHOVER_USER or SAFEPING_PUSHOVER_TOKEN not set)")


def _clock(ts, ref):
    """2:31:05 PM, with the date in front when ts is not on the same day as ref."""
    t = time.localtime(ts)
    text = time.strftime("%I:%M:%S %p", t).lstrip("0")
    if time.strftime("%Y-%m-%d", t) != time.strftime("%Y-%m-%d", time.localtime(ref)):
        text = time.strftime("%b %d", t).replace(" 0", " ") + ", " + text
    return text


def where_words(loc):
    """The location the way the dashboard says it, or None when it is not known."""
    if loc.get("source") == "gps":
        named = stats._place(places.describe({"latitude": loc["latitude"], "longitude": loc["longitude"]}))
        if named:
            return named
        text = "GPS {:.5f}, {:.5f}".format(loc["latitude"], loc["longitude"])
        if loc.get("accuracy") is not None:
            text += ", about {} m".format(loc["accuracy"])
        return text
    if loc.get("source") == "floor" and loc.get("floor") is not None:
        return "Indoors, floor {}".format(loc["floor"])
    return None


def build(alert_id, alert_type, student_name, device_id, loc, received_at, pressed_at, late):
    """The Pushover request fields, without the keys. late is validate.age_tag()."""
    lines = ["{} ({})".format(student_name, device_id) if student_name else device_id]
    place = where_words(loc)
    if place:
        lines.append(place)
    if pressed_at is not None:
        lines.append("Pressed " + _clock(pressed_at, received_at))
        if late:
            lines.append("Arrived late at " + _clock(received_at, received_at))
    else:
        lines.append("Press time unknown (Fob clock not set). Received " + _clock(received_at, received_at))

    fields = {
        "title": "SafePing " + alert_type,
        "message": "\n".join(lines)[:MAX_MESSAGE],
    }
    if alert_type == "MEDICAL":
        fields.update(priority=2, retry=EMERGENCY_RETRY_S, expire=EMERGENCY_EXPIRE_S)
    elif alert_type == "SUSPICIOUS":
        fields["priority"] = 1
    else:
        fields.update(priority=0, sound="none")
    if config.PUBLIC_URL and alert_id is not None:
        fields["url"] = "{}/#/alert/{}".format(config.PUBLIC_URL, alert_id)
        fields["url_title"] = "Open in SafePing"
    return fields


def _clean(text):
    """An error text that is safe to print and store: never the keys."""
    text = str(text)
    for secret in (config.PUSHOVER_TOKEN, config.PUSHOVER_USER):
        if secret:
            text = text.replace(secret, "(hidden)")
    return " ".join(text.split())[:MAX_ERROR]


def _post(fields):
    """Sends one request. Returns None when Pushover accepted it, else the reason."""
    data = dict(fields, token=config.PUSHOVER_TOKEN, user=config.PUSHOVER_USER)
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(config.PUSHOVER_API_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=config.PUSHOVER_TIMEOUT_S) as resp:
            reply = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as error:
        # Pushover answers 4xx with {"status": 0, "errors": [...]}
        try:
            reply = json.loads(error.read().decode("utf-8", "replace") or "{}")
            reasons = reply.get("errors") or []
        except ValueError:
            reasons = []
        return "HTTP {}{}".format(error.code, ": " + "; ".join(str(r) for r in reasons) if reasons else "")
    except urllib.error.URLError as error:
        return "no connection: {}".format(error.reason)
    except (OSError, ValueError) as error:
        return "{}: {}".format(type(error).__name__, error)
    if reply.get("status") != 1:
        return "refused: " + "; ".join(str(r) for r in reply.get("errors") or ["no status 1"])
    return None


def send(alert_id, alert_type, student_name, device_id, loc, received_at, pressed_at, late):
    """Returns None (not a type that is sent), "off", "sent" or "failed".
    A failure never stops the alert: it is printed and kept for Health."""
    if alert_type not in TYPES:
        return None
    if not enabled():
        announce()
        return "off"
    try:
        error = _post(build(alert_id, alert_type, student_name, device_id, loc,
                            received_at, pressed_at, late))
    except Exception as unexpected:          # never let a notification stop an alert
        error = "{}: {}".format(type(unexpected).__name__, unexpected)
    try:
        if error is None:
            db.record_notify(CHANNEL, time.time(), alert_id)
        else:
            error = _clean(error)
            print("[Pushover failed] alert {}: {}".format(alert_id, error))
            db.record_notify(CHANNEL, time.time(), alert_id, error)
    except Exception as db_error:
        print("[Pushover] could not save the send result: {}".format(db_error))
    return "sent" if error is None else "failed"


def health(now=None):
    """Settings > Health: on or off, and how long ago the last send and the last error were."""
    now = time.time() if now is None else now
    row = db.notify_status(CHANNEL) or {}

    def age(key):
        return None if row.get(key) is None else max(0, round(now - row[key]))

    return {
        "enabled": enabled(),
        "link": bool(config.PUBLIC_URL),
        "last_send_age_s": age("last_send_at"),
        "last_send_alert": row.get("last_send_alert"),
        "last_error_age_s": age("last_error_at"),
        "last_error_alert": row.get("last_error_alert"),
        "last_error": row.get("last_error"),
        # True when the newest attempt failed (an error and no send after it)
        "failing": row.get("last_error_at") is not None
                   and (row.get("last_send_at") is None or row["last_error_at"] > row["last_send_at"]),
    }
