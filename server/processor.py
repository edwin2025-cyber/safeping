"""The whole path a message takes once the server receives it.

Both the MQTT listener and the test scripts call process(), so what you test is
what runs."""
import time

import config
import db
import location
import notify
import validate


LINKS = ("lora", "wifi")
PRUNE_EVERY_S = 3600          # forget old seen counters at most this often
_last_prune = [0.0]


def _ack(on_ack, device, msg):
    """Call the ack hook. A failed ack never stops the alert or its text."""
    if on_ack is None:
        return
    try:
        on_ack(device["device_id"], msg["ctr"], msg["sig"])
    except Exception as error:
        print("[ack] could not send the ack: {}".format(error))


def _prune(now):
    if now - _last_prune[0] < PRUNE_EVERY_S:
        return
    _last_prune[0] = now
    try:
        db.prune_seen(now - config.SEEN_KEEP_DAYS * 86400)
    except Exception as error:          # pruning must never stop an alert
        print("[db] could not prune seen counters: {}".format(error))


def process(payload, now=None, source="unknown", on_ack=None):
    """payload is bytes or text. Returns a dict describing what happened.

    source is how the message reached the server: "lora" (serial bridge), "wifi"
    (MQTT) or "unknown". It is only stored for the dashboard. It never changes
    whether a message is accepted.

    on_ack(device_id, ctr, sig), if given, is called once the alert is safely saved
    (before any text is sent, so the ack is not held up), or when the message is a
    duplicate of one already saved. Never for a rejected message or a REF reading.

    Counter rule (validate.check_counter, message-format.md):
      duplicate  an exact copy of a saved message, any age: not stored again, logged
                 in the rejected table as "duplicate", acked again
      accepted   a counter never seen, no more than COUNTER_WINDOW below the highest,
                 with or without ts, even if a higher counter got in first
      replay     a counter already seen with a different message, or an unseen counter
                 more than COUNTER_WINDOW below the highest
    Age never rejects an alert. The result's "late" is None, "late" (ts more than
    LATE_AFTER_S old) or "over_max" (more than MAX_ALERT_AGE_S old).
    BOOT messages follow the same rule. They are stored as boot reports, never as alerts."""
    now = time.time() if now is None else now
    link = source if source in LINKS else "unknown"
    if isinstance(payload, str):
        payload = payload.encode()
    _prune(now)

    ok, reason, msg, device = validate.authenticate(payload, now)
    if not ok:
        db.log_rejected(now, validate.claimed_id(payload), reason,
                        payload.decode("utf-8", "replace")[:300])
        if reason == "duplicate":
            _ack(on_ack, device, msg)
        return {"ok": False, "reason": reason}

    if msg["type"] == validate.REF_TYPE:
        db.insert_reference(now, msg["p"], msg.get("t"))
        return {"ok": True, "kind": "reference"}

    try:
        if msg["type"] == validate.BOOT_TYPE:
            boot_id = db.insert_boot(device["device_id"], now, msg.get("ts"), msg["ctr"],
                                     msg["fail"], msg.get("wifi"), msg.get("fw"), link,
                                     reset_cause=msg.get("rst"))
        else:
            loc = location.resolve(msg, db.latest_reference(), now)
            alert_id = db.insert_alert(
                device["device_id"], msg["type"], now, msg.get("ts"), loc,
                msg.get("p"), msg.get("bat"),
                temperature=msg.get("t"), counter=msg.get("ctr"), link=link,
            )
    except Exception:
        # Not saved: give the counter back, so the Fob's resend is not a "duplicate"
        # of something the server never stored.
        db.release_counter(device["device_id"], msg["ctr"], msg["sig"])
        raise
    _ack(on_ack, device, msg)          # saved: ack before the text

    if msg["type"] == validate.BOOT_TYPE:
        return {"ok": True, "kind": "boot", "boot_id": boot_id, "fail": msg["fail"],
                "failed": validate.boot_failures(msg["fail"])}

    sms = None
    if msg["type"] != "STATUS":
        body = notify.format_alert(msg["type"], device["student_name"], device["device_id"], loc, now)
        sms = notify.send_sms(body)
        db.mark_sms(alert_id, sms == "sent")

    return {"ok": True, "kind": "alert", "alert_id": alert_id,
            "type": msg["type"], "source": loc["source"], "floor": loc["floor"], "sms": sms,
            "late": validate.age_tag(msg, now)}
