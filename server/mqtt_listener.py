"""Subscribes to the broker, hands every message to processor.process(), and sends the
Fob a signed ack once its alert is saved.

Topics (see message-format.md):
  safeping/alert/<id>   the Fob publishes alerts here (QoS 1)
  safeping/alerts       the old shared topic, still read (fake_fob.py uses it)
  safeping/reference    Reference readings
  safeping/ack/<id>     the server publishes "ACK <id> <ctr> <mac>" here (QoS 1),
                        only after the alert is saved, or for a duplicate of a saved one

Messages are handled one at a time on a worker thread, so a slow text (Twilio) never
holds up the MQTT connection or an ack.
"""
import os
import queue
import sys
import threading

import config
import db
import processor

# ackcheck.py is shared with the Fob and the Relay, so the ack is made by the same code.
_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib")
if _lib not in sys.path:
    sys.path.append(_lib)          # appended, so nothing in firmware/lib hides a server module
import ackcheck  # noqa: E402

try:
    import paho.mqtt.client as mqtt
except ImportError:  # lets the rest of the server run and be tested without paho installed
    mqtt = None


def _make_client(client_id):
    # paho-mqtt 2.x needs a callback API version. 1.x does not have one.
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    return mqtt.Client(client_id=client_id)


def ack_for(device_id, ctr, sig):
    """(topic, text) of the signed ack for one alert. Uses the device's secret from the DB."""
    device = db.get_device(device_id)
    if device is None:
        raise ValueError("unknown device {}".format(device_id))
    key = ackcheck.ack_key(device["secret_key"].encode())
    return config.TOPIC_ACK_PREFIX + device_id, ackcheck.ack_text(key, device_id, ctr, sig)


def start(block=False):
    if mqtt is None:
        raise RuntimeError("paho-mqtt is not installed. Run: pip install -r requirements.txt")
    if config.MQTT_CA and not os.path.isfile(config.MQTT_CA):
        raise RuntimeError("MQTT CA file not found (SAFEPING_MQTT_CA)")

    client = _make_client("safeping-server")
    if config.MQTT_USER:
        client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
    if config.MQTT_CA:
        client.tls_set(ca_certs=config.MQTT_CA)       # certificate and host name are checked
    inbox = queue.Queue()

    def send_ack(device_id, ctr, sig):
        topic, text = ack_for(device_id, ctr, sig)
        client.publish(topic, text, qos=1)
        print("[mqtt] ack sent to {} ctr {}".format(topic, ctr))

    def worker():
        while True:
            topic, payload = inbox.get()
            try:
                # "wifi" is right while the Relay uses the USB serial bridge. If the Relay
                # later republishes LoRa alerts over MQTT, those will show as wifi too.
                on_ack = None if topic == config.TOPIC_REFERENCE else send_ack
                result = processor.process(payload, source="wifi", on_ack=on_ack)
                print("[mqtt] {} -> {}".format(topic, result))
            except Exception as error:  # never let one bad message kill the listener
                print("[mqtt] error handling message: {}".format(error))

    def on_connect(client, userdata, flags, rc):
        if rc != 0:
            print("[mqtt] broker refused the connection (code {}). Check the user name and password.".format(rc))
            return
        print("[mqtt] connected to {}:{}{}".format(config.MQTT_HOST, config.MQTT_PORT,
                                                  " with TLS" if config.MQTT_CA else ""))
        client.subscribe([(config.TOPIC_ALERT_PREFIX + "+", 1), (config.TOPIC_ALERTS, 1),
                          (config.TOPIC_REFERENCE, 1)])

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            print("[mqtt] connection lost (code {}), reconnecting".format(rc))

    def on_message(client, userdata, message):
        inbox.put((message.topic, message.payload))

    threading.Thread(target=worker, name="mqtt-worker", daemon=True).start()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)

    if block:
        client.loop_forever()
    else:
        client.loop_start()
    return client


if __name__ == "__main__":
    db.init_db()
    start(block=True)
