# Radio diagnostic. Finds out whether, and where, the LoRa radio answers.
# It does not use the radio driver. Run it from Thonny with the Fob selected.

from machine import Pin, SPI  # type: ignore
import time

CANDIDATES = [0, 1, 2, 3, 4, 5, 6, 26]      # pins the radio's CS might be wired to

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))

# Hold every candidate pin high. High means "radio not selected, not in reset".
pins = {}
for n in CANDIDATES:
    pins[n] = Pin(n, Pin.OUT, value=1)
time.sleep_ms(100)


def read_version(cs):
    cs.value(0)                  # select the radio
    spi.write(bytes([0x42]))     # ask for register 0x42, the version number
    value = spi.read(1)[0]
    cs.value(1)                  # let go of the radio
    return value


print("Reading the radio's version register. A good radio answers 0x12.")
print()
found = []
for n in CANDIDATES:
    v = read_version(pins[n])
    mark = "   <-- the radio answered" if v == 0x12 else ""
    print("CS on IO{}: 0x{:02x}{}".format(n, v, mark))
    if v == 0x12:
        found.append(n)

print()
if found == [26]:
    print("RESULT: good. The radio answers on IO26, which is what the code expects.")
elif found:
    print("RESULT: the radio answers on IO{}, not IO26.".format(found[0]))
    print("The CS jumper is in the wrong socket. Move it to IO26, or tell me.")
else:
    print("RESULT: no answer on any pin. Every reading was 0xff or 0x00.")
    print("The radio has no power, or SCK, MISO or MOSI is not connected,")
    print("or the radio itself has a problem.")