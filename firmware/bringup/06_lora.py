"""STEP 6. Test the LoRa radio. Last, because it needs two boards.

Wire the radio (power OFF), using pins.py:
  VIN to 3V3     GND to GND
  SCK, MISO, MOSI to the SPI pins    CS, RST, G0 to the LORA pins
  ANTENNA: fit it BEFORE powering on. Sending with no antenna can damage the radio.

Part A, one board (set ROLE = "check"):
  Reads the radio's version register. It must say 0x12. If it does, the SPI wiring is
  right and the chip is alive. This is the most useful check in the whole file.

Part B, two boards (the Fob board and the Relay board):
  Set ROLE = "tx" on one and ROLE = "rx" on the other. The sender sends a short message
  every 3 seconds. The receiver prints each one with its signal strength.
  Start with the two boards on the same desk. Then walk apart and note where it drops.

Settings are 915 MHz, SF7, 125 kHz. Both sides must match (they do, from sx127x.py).
"""
import time

from machine import Pin

import hw
import pins
import sx127x

ROLE = "check"          # "check", "tx" or "rx"

spi = hw.make_spi()
cs = Pin(pins.LORA_CS, Pin.OUT, value=1)
reset = Pin(pins.LORA_RST, Pin.OUT, value=1)
radio = sx127x.SX127x(spi, cs, reset)

version = radio.begin()
print("LoRa radio found, version register = 0x{:02x} (good)".format(version))

if ROLE == "tx":
    count = 0
    while True:
        message = "SafePing test {}".format(count)
        ok = radio.send(message.encode())
        print("sent '{}'".format(message) if ok else "send FAILED")
        count += 1
        time.sleep(3)
elif ROLE == "rx":
    print("Listening. Start the other board.")
    while True:
        packet = radio.receive(timeout_ms=5000)
        if packet is None:
            print("... nothing yet")
        else:
            data, rssi, snr = packet
            print("received '{}'  signal {} dBm  snr {}".format(data.decode("ascii", "ignore"), rssi, snr))
else:
    print("Check done. Set ROLE to 'tx' or 'rx' for the two-board test.")
