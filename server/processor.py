"""The whole path a message takes once the server receives it.

Both the MQTT listener and the test scripts call process(), so what you test is
what runs."""
import time

import db
import location
import notify
import validate


def process(payload, now=None):
    """payload is bytes or text. Returns a dict describing what happened."""
    now = time.time() if now is None else now
    if isinstance(payload, str):
        payload = payload.encode()

    ok, reason, msg, device = validate.authenticate(payload)
    if not ok:
        db.log_rejected(now, validate.claimed_id(payload), reason,
                        payload.decode("utf-8", "replace")[:300])
        return {"ok": False, "reason": reason}

    if msg["type"] == validate.REF_TYPE:
        db.insert_reference(now, msg["p"], msg.get("t"))
        return {"ok": True, "kind": "reference"}

    loc = location.resolve(msg, db.latest_reference(), now)
    alert_id = db.insert_alert(
        device["device_id"], msg["type"], now, msg.get("ts"), loc,
        msg.get("p"), msg.get("bat"),
    )

    sms = None
    if msg["type"] != "STATUS":
        body = notify.format_alert(msg["type"], device["student_name"], device["device_id"], loc, now)
        sms = notify.send_sms(body)
        db.mark_sms(alert_id, sms == "sent")

    return {"ok": True, "kind": "alert", "alert_id": alert_id,
            "type": msg["type"], "source": loc["source"], "floor": loc["floor"], "sms": sms}
