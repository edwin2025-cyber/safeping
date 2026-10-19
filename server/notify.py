"""Texts the duty phone. Without Twilio settings it prints the text instead (dry run)."""
import time

import config

LABELS = {
    "SILENT": "SILENT ALERT",
    "MEDICAL": "MEDICAL EMERGENCY",
    "SUSPICIOUS": "SUSPICIOUS PERSON",
}


def where(loc):
    if loc["source"] == "gps":
        text = "GPS {:.5f}, {:.5f}".format(loc["latitude"], loc["longitude"])
        if loc.get("accuracy") is not None:
            text += " (within {} m)".format(loc["accuracy"])
        text += " https://maps.google.com/?q={:.6f},{:.6f}".format(loc["latitude"], loc["longitude"])
        return text
    if loc["source"] == "floor":
        return "floor {}".format(loc["floor"])
    return "location unknown"


def format_alert(alert_type, student_name, device_id, loc, received_at):
    label = LABELS.get(alert_type, alert_type)
    who = "{} ({})".format(student_name, device_id) if student_name else device_id
    clock = time.strftime("%I:%M:%S %p", time.localtime(received_at)).lstrip("0")
    return "SAFEPING {}: {} at {}. {}".format(label, who, where(loc), clock)


def send_sms(body):
    """Returns 'sent', 'dry_run' or 'failed'."""
    if not (config.TWILIO_SID and config.TWILIO_TOKEN and config.TWILIO_FROM and config.DUTY_PHONES):
        print("[SMS dry run] " + body)
        return "dry_run"
    try:
        from twilio.rest import Client
        client = Client(config.TWILIO_SID, config.TWILIO_TOKEN)
        for number in config.DUTY_PHONES:
            client.messages.create(body=body, from_=config.TWILIO_FROM, to=number)
        return "sent"
    except Exception as error:  # a text failing must never stop the alert from being stored
        print("[SMS failed] {}".format(error))
        return "failed"
