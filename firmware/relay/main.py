# Relay test: listen for real SafePing alerts that a Fob sends over LoRa.
# Each alert is printed as one line starting with SAFEPING_MSG, the same line the Fob
# prints on its own console, followed by who sent it and how strong the signal was.
#
# Every new alert is first stored in queue.txt on this board's flash, then answered
# with a signed ack "ACK <id> <ctr> <mac>" (see ackcheck.py). So an ack means "the
# Relay has it saved", and a future forwarder can send queue.txt on to the server.
# The Fob waits for the ack and resends the same message if it does not come.
# A resent message (same id and ctr) is acked again but printed only as a duplicate,
# so it is never stored or forwarded twice.
#
# The Relay needs its own config.py (never in git) with one ack key per Fob:
#     ACK_KEYS = {"FOB-001": "<64 hex characters>"}
# Make the key on the Fob in Thonny:  import ackcheck, config
#                                      ackcheck.ack_key_hex(config.SECRET_KEY)
# The Relay never holds the Fob's real secret key, only this ack key.
# Run it from Thonny on the Relay board and leave it open. Ctrl+C stops it.

from machine import Pin, SPI  # type: ignore
import binascii
import json
import time
import sx127x
import ackcheck

try:
    import config
    ACK_KEYS = getattr(config, "ACK_KEYS", {})
except ImportError:
    ACK_KEYS = {}
QUEUE_FILE = "queue.txt"

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))
cs = Pin(26, Pin.OUT, value=1)
reset = Pin(6, Pin.OUT, value=1)

radio = sx127x.SX127x(spi, cs, reset)
radio.begin()

got = 0
recent = []                  # (id, ctr) of the last alerts, to spot resends
print("Listening for SafePing alerts. Press Ctrl+C to stop.")
print("Ack keys for:", ", ".join(sorted(ACK_KEYS)) if ACK_KEYS else "nobody (no acks will be sent)")

try:
    while True:
        # Long window on purpose. Each time receive() times out it switches the radio
        # off for a moment, which would cut a packet that is still arriving.
        try:
            packet = radio.receive(timeout_ms=60000)
        except OSError as err:
            # The radio reset or stopped answering. Set it up again and keep listening.
            print("Relay radio problem:", err)
            print("Setting the Relay radio up again")
            time.sleep_ms(500)
            try:
                radio.begin()
                print("Relay radio OK again")
            except OSError as err2:
                print("Relay radio still not answering:", err2)
            continue
        if packet is None:
            continue
        data, rssi, snr = packet
        try:
            text = data.decode()
            msg = json.loads(text)
            if not isinstance(msg, dict) or "sig" not in msg or "id" not in msg or "ctr" not in msg:
                raise ValueError
        except (ValueError, UnicodeError):
            print("ignored a packet that is not a SafePing alert")
            continue
        key = (msg["id"], msg["ctr"])
        duplicate = key in recent
        stored = duplicate                   # a resend was already stored the first time
        if not duplicate:
            # Store BEFORE acking, so the ack means "saved", not just "heard".
            try:
                with open(QUEUE_FILE, "a") as f:
                    f.write(text + "\n")
                stored = True
            except OSError as err:
                print("Relay could not store the alert:", err, "(no ack, the Fob will resend)")
        # Ack before any printing, so the Fob hears it inside its wait window.
        # The short pause makes sure the Fob has switched from sending to listening.
        hexkey = ACK_KEYS.get(msg["id"])
        acked = False
        if stored and hexkey is None:
            print("no ack key for", msg["id"], "so no ack sent")
        elif stored:
            time.sleep_ms(20)
            ack = ackcheck.ack_text(binascii.unhexlify(hexkey), msg["id"], msg["ctr"], msg["sig"])
            try:
                acked = radio.send(ack.encode())
                if not acked:
                    print("Relay could not send the ack (timeout)")
            except OSError as err:
                print("Relay could not send the ack:", err)
        if duplicate:
            print("  duplicate of", msg["id"], "ctr", msg["ctr"], "(acked again)" if acked else "(not acked)")
            continue
        if not stored:
            continue
        recent.append(key)
        if len(recent) > 20:
            recent.pop(0)
        got += 1
        print("SAFEPING_MSG " + text)
        print("  from", msg.get("id"), "type", msg.get("type"), "ctr", msg.get("ctr"),
              "signal", rssi, "dBm, snr", snr)
except KeyboardInterrupt:
    print("received", got, "alerts")