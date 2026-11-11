"""Checks every incoming message. The rules are written out in message-format.md."""
import hashlib
import hmac
import json
import re
import time

import config
import db

ALERT_TYPES = {"STATUS", "SUSPICIOUS", "MEDICAL", "SILENT"}
REF_TYPE = "REF"
BOOT_TYPE = "BOOT"            # the Fob's boot report (self-check results). Never an alert.

# Order matters. The Fob signs the same fields in the same order.
SIGNED_FIELDS = ("v", "id", "type", "ctr", "ts", "lat", "lon", "acc", "p", "t", "bat")
# A BOOT message signs more fields after those, so other messages are unchanged.
# rst (the reset cause) was added on 2026-11-11. A BOOT from older firmware has no rst
# and is signed with the first three only, so it still checks out.
BOOT_FIELDS = ("fail", "wifi", "fw", "rst")
BOOT_FIELDS_OLD = ("fail", "wifi", "fw")

# machine.reset_cause() values (MicroPython ESP32 port) in plain words for the Devices page.
# 2 is a crash or a software restart. The Fob never restarts itself, so it is a crash.
RESET_WORDS = {
    1: "Power on",
    2: "Restarted after a crash",
    3: "Restarted by the watchdog",
    4: "Woke from deep sleep",
    5: "Soft reset (Thonny or Ctrl+D)",
}


def reset_words(code):
    if code is None:
        return None                          # older firmware did not report it
    return RESET_WORDS.get(code, "Unknown reason")
FW_RE = re.compile(r"^[A-Za-z0-9._-]{1,16}$")

# Bits of "fail" in a BOOT message: the required checks that failed.
BOOT_CHECKS = (
    (1, "key", "Secret key missing or the wrong length"),
    (2, "counter", "Counter file could not be read"),
    (4, "lora", "LoRa radio not answering"),
    (8, "gps", "GPS not sending data"),
    (16, "battery", "Battery gauge not reading"),
    (32, "pressure", "Pressure sensor not reading"),
)

# (low, high) allowed for each whole-number field
RANGES = {
    "v": (1, 1),
    "ctr": (0, 2**31 - 1),
    "ts": (0, 4_000_000_000),
    "lat": (-90_000_000, 90_000_000),
    "lon": (-180_000_000, 180_000_000),
    "acc": (0, 100_000),
    "p": (30_000, 110_000),
    "t": (-4_000, 8_500),
    "bat": (0, 100),
}


def signing_string(msg):
    if msg.get("type") != BOOT_TYPE:
        fields = SIGNED_FIELDS
    elif msg.get("rst") is None:
        fields = SIGNED_FIELDS + BOOT_FIELDS_OLD
    else:
        fields = SIGNED_FIELDS + BOOT_FIELDS
    return "|".join("" if msg.get(k) is None else str(msg[k]) for k in fields)


def boot_failures(mask):
    """The plain words for each failed check in a BOOT "fail" mask."""
    return [words for bit, _, words in BOOT_CHECKS if mask & bit]


def sign(secret_key, msg):
    return hmac.new(secret_key.encode(), signing_string(msg).encode(), hashlib.sha256).hexdigest()


def claimed_id(payload):
    """Best guess at who sent a payload, only used to label the rejected log."""
    try:
        data = json.loads(payload)
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            return data["id"][:32]
    except Exception:
        pass
    return None


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def parse(payload):
    """Returns (msg, reason). reason is None when the message is well formed."""
    if len(payload) > config.MAX_PAYLOAD_BYTES:
        return None, "bad_json"
    try:
        msg = json.loads(payload)
    except Exception:
        return None, "bad_json"
    if not isinstance(msg, dict):
        return None, "bad_format"

    if not isinstance(msg.get("id"), str) or not 0 < len(msg["id"]) <= 32:
        return None, "bad_format"
    if msg.get("type") not in ALERT_TYPES and msg.get("type") not in (REF_TYPE, BOOT_TYPE):
        return None, "bad_format"
    sig = msg.get("sig")
    if not isinstance(sig, str) or len(sig) != 64:
        return None, "bad_format"

    for key in ("v", "ctr"):
        if key not in msg:
            return None, "bad_format"
    for key, (low, high) in RANGES.items():
        if key in msg and msg[key] is not None:
            if not _is_int(msg[key]) or not low <= msg[key] <= high:
                return None, "bad_format"
    if (msg.get("lat") is None) != (msg.get("lon") is None):
        return None, "bad_format"
    if msg["type"] == REF_TYPE and msg.get("p") is None:
        return None, "bad_format"
    if msg["type"] == BOOT_TYPE:
        fail, wifi, fw = msg.get("fail"), msg.get("wifi"), msg.get("fw")
        if not _is_int(fail) or not 0 <= fail <= 255:
            return None, "bad_format"
        if wifi is not None and (not _is_int(wifi) or wifi not in (0, 1)):
            return None, "bad_format"
        if fw is not None and (not isinstance(fw, str) or not FW_RE.match(fw)):
            return None, "bad_format"
        rst = msg.get("rst")
        if rst is not None and (not _is_int(rst) or not 0 <= rst <= 99):
            return None, "bad_format"
    return msg, None


def authenticate(payload, now=None):
    """Run every check in order.

    Returns (ok, reason, msg, device). On success this also uses up the counter,
    so the same message can never be accepted twice. reason can be "duplicate" (an
    exact copy of a message already accepted: the caller acks it again) or "replay"."""
    now = time.time() if now is None else now
    msg, reason = parse(payload)
    if reason:
        return False, reason, None, None

    device = db.get_device(msg["id"])
    if device is None:
        return False, "unknown_device", msg, None

    wants_ref = msg["type"] == REF_TYPE
    if wants_ref != (device["role"] == "REF"):
        return False, "wrong_role", msg, device

    expected = sign(device["secret_key"], msg)
    if not hmac.compare_digest(expected, msg["sig"].lower()):
        return False, "bad_signature", msg, device

    # Only now, with a good signature, do we touch the counter.
    if wants_ref:
        # Reference readings keep the simple rule: the counter must go up.
        if not db.advance_counter(device["device_id"], msg["ctr"]):
            return False, "replay", msg, device
        return True, None, msg, device
    reason = check_counter(device, msg, now)
    return reason is None, reason, msg, device


def _seen_reason(device_id, msg):
    """For a counter that is already taken: "duplicate" if it is this exact message."""
    seen = db.seen_sig(device_id, msg["ctr"])
    return "duplicate" if seen is not None and seen == msg["sig"].lower() else "replay"


def check_counter(device, msg, now):
    """The Fob counter rule (message-format.md, "Counters, duplicates and replays").
    Returns None when the message is accepted (and claims its counter), or the reason.

      1. Counter already seen with the same signature: "duplicate" (any age).
      2. Counter already seen with a different signature: "replay".
      3. Counter never seen, and no more than COUNTER_WINDOW below the highest seen:
         accepted, even if a higher counter got in first (a late alert from the Fob's
         retry queue). With or without ts. Age never rejects an alert: an old ts only
         marks it as sent late (processor.py).
      4. Counter never seen, but more than COUNTER_WINDOW below the highest: "replay".
    Counters inside the window are never pruned (db.prune_seen), so an exact copy of
    a message inside the window is always recognised."""
    device_id, ctr = device["device_id"], msg["ctr"]
    if db.seen_sig(device_id, ctr) is not None:
        return _seen_reason(device_id, msg)

    current = db.get_device(device_id)               # fresh, another message may have raised it
    highest = current["last_counter"] if current is not None else device["last_counter"]
    if highest >= 0 and ctr < highest - config.COUNTER_WINDOW:
        return "replay"

    if not db.claim_counter(device_id, ctr, msg["sig"], now):
        return _seen_reason(device_id, msg)             # another copy got in first
    db.raise_counter(device_id, ctr)
    return None


def age_tag(msg, now):
    """How late an alert arrived, from its ts: None (on time or no ts), "late" (more than
    LATE_AFTER_S) or "over_max" (more than MAX_ALERT_AGE_S, shown as
    "Sent late (over 15 min)" with a yellow warning on Settings > Health)."""
    ts = msg.get("ts")
    if ts is None:
        return None
    gap = now - ts
    if gap > config.MAX_ALERT_AGE_S:
        return "over_max"
    if gap > config.LATE_AFTER_S:
        return "late"
    return None
