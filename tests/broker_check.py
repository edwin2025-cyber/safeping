# broker_check.py - run on the laptop.
# Checks the cloud MQTT broker: TLS, login, publish and receive.
# Sends only a "hello" test message on a test topic. No alert data.
#
# Settings come from environment variables, so nothing secret is in this file:
#   $env:SAFEPING_MQTT_HOST = "your-deployment-address"
#   $env:SAFEPING_MQTT_USER = "safeping-server"
#   $env:SAFEPING_MQTT_PASS = "the password"
#   $env:SAFEPING_MQTT_CA   = "C:\path\to\the\ca-file.crt"
# Optional: $env:SAFEPING_MQTT_PORT (default 8883)

import os
import sys
import threading
import time

import paho.mqtt.client as mqtt

HOST = os.environ.get("SAFEPING_MQTT_HOST", "")
PORT = int(os.environ.get("SAFEPING_MQTT_PORT", "8883"))
USER = os.environ.get("SAFEPING_MQTT_USER", "")
PASS = os.environ.get("SAFEPING_MQTT_PASS", "")
CA = os.environ.get("SAFEPING_MQTT_CA", "")
TOPIC = "safeping/test/broker_check"

missing = [n for n, v in [("SAFEPING_MQTT_HOST", HOST), ("SAFEPING_MQTT_USER", USER),
                          ("SAFEPING_MQTT_PASS", PASS), ("SAFEPING_MQTT_CA", CA)] if not v]
if missing:
    print("Missing settings:", ", ".join(missing))
    sys.exit(1)
if not os.path.isfile(CA):
    print("CA file not found:", CA)
    sys.exit(1)

got = threading.Event()
sent_at = {}


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected with TLS to {}:{}".format(HOST, PORT))
        client.subscribe(TOPIC, qos=1)
    else:
        print("Connect refused:", reason_code, "(check the username and password)")
        got.set()


def on_subscribe(client, userdata, mid, reason_codes, properties):
    print("Subscribed to", TOPIC)
    sent_at["t"] = time.time()
    client.publish(TOPIC, "hello from broker_check", qos=1)
    print("Published a test message")


def on_message(client, userdata, msg):
    ms = (time.time() - sent_at.get("t", time.time())) * 1000
    print("Received it back: {!r} in {:.0f} ms".format(msg.payload.decode(), ms))
    got.set()


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="safeping-broker-check")
client.username_pw_set(USER, PASS)
client.tls_set(ca_certs=CA)
client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_message = on_message

try:
    client.connect(HOST, PORT, keepalive=30)
except Exception as e:
    print("Could not connect:", e)
    sys.exit(1)

client.loop_start()
ok = got.wait(15)
client.loop_stop()
client.disconnect()

if not ok:
    print("FAIL: no message came back within 15 s")
    sys.exit(1)
print("Done.")
