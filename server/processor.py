"""The whole path a message takes once the server receives it.

Both the MQTT listener and the test scripts call process(), so what you test is
what runs."""
import json
import time

import config
import db
import location
import pushover
import refmatch
import textbelt
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
    try:
        db.prune_reference(now - config.REF_KEEP_DAYS * 86400)
    except Exception as error:
        print("[db] could not prune reference readings: {}".format(error))


def process(payload, now=None, source="unknown", on_ack=None):
    """payload is bytes or text. Returns a dict describing what happened.

    source is how the message reached the server: "lora" (serial bridge), "wifi"
    (MQTT) or "unknown". It is only stored for the dashboard. It never changes
    whether a message is accepted.

    on_ack(device_id, ctr, sig), if given, is called once the alert is safely saved
    (before Pushover or any text is sent, so the ack is not held up), or when the message is a
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
    BOOT messages follow the same rule. They are stored as boot reports, never as alerts.
    SURVEY messages follow it without the window. They are stored as survey points and
    acked, never alerts: no text, no Pushover, never on Live or Overview.
    An alert with pressure also stores the Reference pressure at its press time and the
    difference (refmatch.py). No floor is worked out from it yet."""
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
        db.insert_reference(now, msg["p"], msg.get("t"), device_id=device["device_id"],
                            device_ts=msg.get("ts"), pressure_dpa=msg.get("pd"),
                            samples=msg.get("n"), firmware=msg.get("fw"))
        return {"ok": True, "kind": "reference"}

    try:
        if msg["type"] == validate.BOOT_TYPE:
            boot_id = db.insert_boot(device["device_id"], now, msg.get("ts"), msg["ctr"],
                                     msg["fail"], msg.get("wifi"), msg.get("fw"), link,
                                     reset_cause=msg.get("rst"), sensor=msg.get("sensor"))
        elif msg["type"] == validate.SURVEY_TYPE:
            at = msg.get("ts") or now
            ref = refmatch.reference_at(at) if msg.get("pd") is not None else None
            survey_id = db.insert_survey(
                device["device_id"], msg["ctr"], now, msg, json.dumps(msg["aps"]),
                None if ref is None else ref["pressure"], None if ref is None else ref["time"], link)
        else:
            loc = location.resolve(msg, db.latest_reference(), now)
            ref = refmatch.for_pressure(device["device_id"], msg.get("ts") or now, msg.get("p"))
            alert_id = db.insert_alert(
                device["device_id"], msg["type"], now, msg.get("ts"), loc,
                msg.get("p"), msg.get("bat"),
                temperature=msg.get("t"), counter=msg.get("ctr"), link=link,
                cut_off=msg.get("cut") == 1, ref=ref,
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
    if msg["type"] == validate.SURVEY_TYPE:
        return {"ok": True, "kind": "survey", "survey_id": survey_id,
                "matched_reference": ref is not None}

    # Pushover, then the text: MEDICAL, SUSPICIOUS and SILENT only. Only reached for a new,
    # saved alert, so a duplicate or a replay never sends. Pushover goes first because a
    # MEDICAL there repeats until someone answers, and a slow text must not hold it up.
    late = validate.age_tag(msg, now)
    push = pushover.send(alert_id, msg["type"], device["student_name"], device["device_id"],
                         loc, now, msg.get("ts"), late)
    sms = textbelt.send(alert_id, msg["type"], device["student_name"], device["device_id"],
                        loc, now, msg.get("ts"), late)
    if sms is not None:
        try:
            db.mark_sms(alert_id, sms == "sent")
        except Exception as error:
            print("[SMS] could not mark the alert: {}".format(error))

    return {"ok": True, "kind": "alert", "alert_id": alert_id,
            "type": msg["type"], "source": loc["source"], "floor": loc["floor"], "sms": sms,
            "pushover": push, "late": late, "cut_off": msg.get("cut") == 1}
