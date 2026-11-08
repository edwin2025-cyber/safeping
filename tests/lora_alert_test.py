"""Sends one fake alert over LoRa, the same way main.py does, and times it.
Run on the Fob. Needs sx127x.py on the board. Relay runs relay_alert_listen.py."""
import time
from machine import Pin, SPI
import sx127x

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))
radio = sx127x.SX127x(spi, Pin(26, Pin.OUT, value=1), Pin(6, Pin.OUT, value=1))
radio.begin()
print("radio ready")

msg = '{"v": 1, "id": "FOB-001", "type": "STATUS", "ctr": 999, "sig": "test"}'
for n in range(3):
    start = time.ticks_ms()
    ok = radio.send(msg.encode())
    print("send", n + 1, "ok" if ok else "TIMEOUT", time.ticks_diff(time.ticks_ms(), start), "ms")
    time.sleep(2)

print("Now the same thing with WiFi switched on")
import network
sta = network.WLAN(network.STA_IF)
sta.active(True)
for n in range(3):
    start = time.ticks_ms()
    ok = radio.send(msg.encode())
    print("send", n + 1, "ok" if ok else "TIMEOUT", time.ticks_diff(time.ticks_ms(), start), "ms")
    time.sleep(2)
