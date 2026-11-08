# Range test, Fob side. Sends a numbered message every 2 seconds.
# Save it on the board as main.py so it runs by itself on battery.
# Light on the board: blue = starting, green flash = sent, red flash = send failed,
# slow red blinking = the radio was not found (check wiring, then reset the board).

from machine import Pin, SPI  # type: ignore
import neopixel  # type: ignore
import time
import sx127x

light = neopixel.NeoPixel(Pin(27), 1)       # the RGB light built into the board


def flash(color, ms=80):
    light[0] = color
    light.write()
    time.sleep_ms(ms)
    light[0] = (0, 0, 0)
    light.write()


flash((0, 0, 60), 1500)                     # blue: starting up

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))
cs = Pin(26, Pin.OUT, value=1)
reset = Pin(6, Pin.OUT, value=1)

try:
    radio = sx127x.SX127x(spi, cs, reset)
    radio.begin()
except OSError as err:
    print("radio problem:", err)
    while True:
        flash((60, 0, 0), 300)
        time.sleep_ms(700)

count = 0
while True:
    ok = radio.send("range {}".format(count).encode())
    print("sent", count, ok)
    flash((0, 60, 0) if ok else (60, 0, 0))
    count += 1
    time.sleep(2)