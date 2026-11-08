# Lesson 4b: listen for LoRa messages. Run this on the Relay (wing) first.

from machine import Pin, SPI  # type: ignore
import sx127x

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))
cs = Pin(26, Pin.OUT, value=1)
reset = Pin(6, Pin.OUT, value=1)

radio = sx127x.SX127x(spi, cs, reset)
radio.begin()
print("listening")

while True:
    packet = radio.receive(timeout_ms=5000)
    if packet is None:
        print("nothing yet")
    else:
        data, rssi, snr = packet
        print("got:", data.decode(), " signal:", rssi, "dBm")