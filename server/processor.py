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


def _ack(on_ack, device, msg):
    """Call the ack hook. A failed ack never stops the alert or its text."""
    if on_ack is None:
        return
    try:
        on_ack(device["device_id"], msg["ctr"], msg["sig"])
    except Exception as error:
        print("[ack] could not send the ack: {}".format(error))


def process(payload, now=None, source="unknown", on_ack=None):
    """payload is bytes or text. Returns a dict describing what happened.

    source is how the message reached the server: "lora" (serial bridge), "wifi"
    (MQTT) or "unknown". It is only stored for the dashboard. It never changes
    whether a message is accepted.

    on_ack(device_id, ctr, sig), if given, is called once the alert is safely saved
    (before any text is sent, so the ack is not held up), or when the message is a
    duplicate of an alert already saved. Never for a rejected message or a REF reading.

    Duplicate rule: an alert identical to one accepted in the last DUPLICATE_WINDOW_S
    seconds (same id, ctr and sig) fails the counter check like a replay, but it is a
    Fob resend (WiFi first, then LoRa). It is not stored again, it is logged in the
    rejected table as "duplicate", and it is acked again. Anything else with an old
    counter stays "replay"."""
    now = time.time() if now is None else now
    link = source if source in LINKS else "unknown"
    if isinstance(payload, str):
        payload = payload.encode()

    ok, reason, msg, device = validate.authenticate(payload)
    if not ok:
        duplicate = (reason == "replay" and msg["type"] != validate.REF_TYPE
                     and db.is_recent_duplicate(device["device_id"], msg["ctr"], msg["sig"],
                                                now - config.DUPLICATE_WINDOW_S))
        if duplicate:
            reason = "duplicate"
        db.log_rejected(now, validate.claimed_id(payload), reason,
                        payload.decode("utf-8", "replace")[:300])
        if duplicate:
            _ack(on_ack, device, msg)
        return {"ok": False, "reason": reason}

    if msg["type"] == validate.REF_TYPE:
        db.insert_reference(now, msg["p"], msg.get("t"))
        return {"ok": True, "kind": "reference"}

    loc = location.resolve(msg, db.latest_reference(), now)
    alert_id = db.insert_alert(
        device["device_id"], msg["type"], now, msg.get("ts"), loc,
        msg.get("p"), msg.get("bat"),
        temperature=msg.get("t"), counter=msg.get("ctr"), link=link,
    )
    db.record_accepted(device["device_id"], msg["ctr"], msg["sig"], now)
    _ack(on_ack, device, msg)          # saved: ack before the text

    sms = None
    if msg["type"] != "STATUS":
        body = notify.format_alert(msg["type"], device["student_name"], device["device_id"], loc, now)
        sms = notify.send_sms(body)
        db.mark_sms(alert_id, sms == "sent")

    return {"ok": True, "kind": "alert", "alert_id": alert_id,
            "type": msg["type"], "source": loc["source"], "floor": loc["floor"], "sms": sms}
