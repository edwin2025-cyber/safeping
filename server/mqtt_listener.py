"""Subscribes to the broker and hands every message to processor.process()."""
import config
import processor

try:
    import paho.mqtt.client as mqtt
except ImportError:  # lets the rest of the server run and be tested without paho installed
    mqtt = None


def _make_client(client_id):
    # paho-mqtt 2.x needs a callback API version. 1.x does not have one.
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    return mqtt.Client(client_id=client_id)


def start(block=False):
    if mqtt is None:
        raise RuntimeError("paho-mqtt is not installed. Run: pip install -r requirements.txt")

    client = _make_client("safeping-server")
    if config.MQTT_USER:
        client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)

    def on_connect(client, userdata, flags, rc):
        print("[mqtt] connected to {}:{} (code {})".format(config.MQTT_HOST, config.MQTT_PORT, rc))
        client.subscribe([(config.TOPIC_ALERTS, 1), (config.TOPIC_REFERENCE, 1)])

    def on_message(client, userdata, message):
        try:
            result = processor.process(message.payload)
            print("[mqtt] {} -> {}".format(message.topic, result))
        except Exception as error:  # never let one bad message kill the listener
            print("[mqtt] error handling message: {}".format(error))

    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)

    if block:
        client.loop_forever()
    else:
        client.loop_start()
    return client


if __name__ == "__main__":
    import db
    db.init_db()
    start(block=True)
