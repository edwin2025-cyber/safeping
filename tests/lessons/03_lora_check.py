# Lesson 3: is the LoRa radio alive?
# This only reads one register from the radio. It sends nothing.
# A good RFM95W answers 0x12 when you ask for its version.

from machine import Pin, SPI  # type: ignore
import time

cs = Pin(26, Pin.OUT, value=1)
reset = Pin(6, Pin.OUT, value=1)

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))

# Reset the radio: pull RST low briefly, then release it.
reset.value(0)
time.sleep_ms(10)
reset.value(1)
time.sleep_ms(10)

# Read register 0x42 (the version number).
cs.value(0)                        # start talking to the radio
spi.write(bytes([0x42]))           # which register we want
version = spi.read(1)[0]           # read one byte back
cs.value(1)                        # stop talking

print("version register = 0x{:02x}".format(version))
if version == 0x12:
    print("GOOD: the radio answered")
else:
    print("NOT GOOD: expected 0x12. Check SCK, MISO, MOSI, CS wires.")