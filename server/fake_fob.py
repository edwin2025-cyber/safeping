"""Pretends to be a Fob (or the Reference) so you can test the server and dashboard
before any hardware arrives.

Examples:
  python fake_fob.py --id FOB-001 --key KEY --type SILENT --lat 34.7304 --lon -86.5861 --acc 8
  python fake_fob.py --id FOB-001 --key KEY --type MEDICAL --pressure 101240
  python fake_fob.py --id REF-01 --key KEY --type REF --pressure 101325

By default it publishes to the MQTT broker, like a real Fob: to safeping/alert/<id>
(REF: safeping/ref/<id>), logged in with its own settings SAFEPING_FAKEFOB_MQTT_USER and
SAFEPING_FAKEFOB_MQTT_PASS (point them at the Fob user, safeping-fob). The broker's host
and CA come from the server settings (SAFEPING_MQTT_HOST, SAFEPING_MQTT_CA). It then
waits up to 3 s for the server's signed ack on safeping/ack/<id>.
A REF over MQTT needs the Reference user (safeping-ref): the Fob user may not publish
there. Use --direct for REF instead.

Add --direct to skip the broker and hand the message straight to the server code (the
database must be the same one)."""
import argparse
import json
import os
import threading
import time
import warnings

if __name__ == "__main__":
    # safeping.env, before any setting is read. Not when a test imports this file.
    import envfile
    envfile.load()

import config
import validate

warnings.filterwarnings("ignore", category=DeprecationWarning)   # paho 2.x says API version 1 is old

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_fob_state.json")


def next_counter(device_id):
    """Saved to a file, like the real Fob saves its counter to flash."""
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except Exception:
        state = {}
    counter = state.get(device_id, -1) + 1
    state[device_id] = counter
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    return counter


def build_message(device_id, key, msg_type, counter, lat=None, lon=None, acc=None,
                  pressure=None, temp=None, battery=None, device_ts=None):
    """Whole numbers only. lat and lon go in as microdegrees."""
    msg = {"v": 1, "id": device_id, "type": msg_type, "ctr": counter}
    if device_ts is not None:
        msg["ts"] = device_ts
    if lat is not None and lon is not None:
        msg["lat"] = int(round(lat * 1_000_000))
        msg["lon"] = int(round(lon * 1_000_000))
    if acc is not None:
        msg["acc"] = int(acc)
    if pressure is not None:
        msg["p"] = int(pressure)
    if temp is not None:
        msg["t"] = int(round(temp * 100))
    if battery is not None:
        msg["bat"] = int(battery)
    msg["sig"] = validate.sign(key, msg)
    return msg


def mqtt_topic(device_id, msg_type):
    """Where a real device publishes this message (message-format.md, "Transport")."""
    prefix = config.TOPIC_REF_PREFIX if msg_type == "REF" else config.TOPIC_ALERT_PREFIX
    return prefix + device_id


def main():
    parser = argparse.ArgumentParser(description="Fake SafePing Fob")
    parser.add_argument("--id", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--type", default="SUSPICIOUS",
                        choices=["STATUS", "SUSPICIOUS", "MEDICAL", "SILENT", "REF"])
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--acc", type=int)
    parser.add_argument("--pressure", type=int, help="pascals, such as 101325")
    parser.add_argument("--temp", type=float, help="degrees C")
    parser.add_argument("--battery", type=int, default=90)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--direct", action="store_true")
    args = parser.parse_args()

    acks = []
    got_ack = threading.Event()
    topic = mqtt_topic(args.id, args.type)
    if args.direct:
        import db
        import processor
        db.init_db()
    else:
        if not (config.FAKEFOB_MQTT_USER and config.FAKEFOB_MQTT_PASS):
            raise SystemExit("Set SAFEPING_FAKEFOB_MQTT_USER and SAFEPING_FAKEFOB_MQTT_PASS (the Fob's broker "
                             "login) in safeping.env, or use --direct.")
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="fakefob-" + args.id) \
            if hasattr(mqtt, "CallbackAPIVersion") else mqtt.Client(client_id="fakefob-" + args.id)
        client.username_pw_set(config.FAKEFOB_MQTT_USER, config.FAKEFOB_MQTT_PASS)
        if config.MQTT_CA:
            client.tls_set(ca_certs=config.MQTT_CA)

        def on_message(client, userdata, message):
            acks.append(message.payload.decode("utf-8", "replace"))
            got_ack.set()
        client.on_message = on_message
        client.connect(config.MQTT_HOST, config.MQTT_PORT)
        client.loop_start()
        if args.type != "REF":
            client.subscribe(config.TOPIC_ACK_PREFIX + args.id, qos=1)     # before publishing, like the Fob

    for _ in range(args.repeat):
        msg = build_message(
            args.id, args.key, args.type, next_counter(args.id),
            lat=args.lat, lon=args.lon, acc=args.acc, pressure=args.pressure,
            temp=args.temp, battery=None if args.type == "REF" else args.battery,
            device_ts=int(time.time()),
        )
        payload = json.dumps(msg, separators=(",", ":"))
        if args.direct:
            print(processor.process(payload))
        else:
            got_ack.clear()
            info = client.publish(topic, payload, qos=1)
            info.wait_for_publish(timeout=10)
            if not info.is_published():
                print("NOT published to {} (no PUBACK in 10 s: is the topic allowed for this user?)".format(topic))
                continue
            print("published to {}: {}".format(topic, payload))
            if args.type != "REF":
                if got_ack.wait(3):
                    print("server ack: {}".format(acks[-1]))
                else:
                    print("no server ack in 3 s (is the server running with MQTT on?)")

    if not args.direct:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
