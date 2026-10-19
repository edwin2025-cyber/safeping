"""Pretends to be a Fob (or the Reference) so you can test the server and dashboard
before any hardware arrives.

Examples:
  python fake_fob.py --id FOB-001 --key KEY --type SILENT --lat 34.7304 --lon -86.5861 --acc 8
  python fake_fob.py --id FOB-001 --key KEY --type MEDICAL --pressure 101240
  python fake_fob.py --id REF-01 --key KEY --type REF --pressure 101325

By default it publishes to the MQTT broker. Add --direct to skip the broker and
hand the message straight to the server code (the database must be the same one)."""
import argparse
import json
import os
import time
import warnings

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

    if args.direct:
        import db
        import processor
        db.init_db()
    else:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1) if hasattr(mqtt, "CallbackAPIVersion") \
            else mqtt.Client()
        if config.MQTT_USER:
            client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
        client.connect(config.MQTT_HOST, config.MQTT_PORT)
        client.loop_start()

    topic = config.TOPIC_REFERENCE if args.type == "REF" else config.TOPIC_ALERTS
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
            client.publish(topic, payload, qos=1).wait_for_publish()
            print("published to {}: {}".format(topic, payload))

    if not args.direct:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
