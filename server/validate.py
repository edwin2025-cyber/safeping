"""Checks every incoming message. The rules are written out in message-format.md."""
import hashlib
import hmac
import json

import config
import db

ALERT_TYPES = {"STATUS", "SUSPICIOUS", "MEDICAL", "SILENT"}
REF_TYPE = "REF"

# Order matters. The Fob signs the same fields in the same order.
SIGNED_FIELDS = ("v", "id", "type", "ctr", "ts", "lat", "lon", "acc", "p", "t", "bat")

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
    return "|".join("" if msg.get(k) is None else str(msg[k]) for k in SIGNED_FIELDS)


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
    if msg.get("type") not in ALERT_TYPES and msg.get("type") != REF_TYPE:
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
    return msg, None


def authenticate(payload):
    """Run every check in order.

    Returns (ok, reason, msg, device). On success this also uses up the counter,
    so the same message can never be accepted twice."""
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
    if not db.advance_counter(device["device_id"], msg["ctr"]):
        return False, "replay", msg, device

    return True, None, msg, device
