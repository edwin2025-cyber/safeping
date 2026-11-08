# Lesson 4a: send a short message every 3 seconds. Run this on the Fob (breakout).

from machine import Pin, SPI  # type: ignore
import time
import sx127x

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))
cs = Pin(26, Pin.OUT, value=1)
reset = Pin(6, Pin.OUT, value=1)

radio = sx127x.SX127x(spi, cs, reset)
radio.begin()
print("radio ready")

count = 0
while True:
    message = "hello {}".format(count)
    ok = radio.send(message.encode())
    print("sent:", message, ok)
    count += 1
    time.sleep(3)