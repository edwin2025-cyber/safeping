"""STEP 0. Find out which header hole is which GPIO number.

Why: the schematic tells us the GPIO numbers, but the labels printed on the board
(A0, A1, ... and 5, 6, 7 ...) do not always match them in the order you would guess.
This script turns on one GPIO at a time. You find which hole is live and write it down.

What you need: one LED and a resistor (about 330 ohm) in a row, and a wire to GND.
Nothing else should be connected to the board. Do NOT run this with parts wired up.

How to read it:
  The script prints "GPIO 4 is HIGH now" and holds it for a few seconds.
  Touch the LED's long leg (through the resistor) to each header hole in turn, with the
  other end on GND. The hole that lights the LED is GPIO 4. A multimeter set to volts
  also works: the live hole shows about 3.3 V.
  Fill in the table at the bottom of docs/hardware-connections.md.

Pins that must stay unused for outside wiring are skipped (see pins.RESERVED).
"""
import time
from machine import Pin

import pins

SECONDS_PER_PIN = 5

candidates = [g for g in pins.CANDIDATE_FREE_PINS if g not in pins.RESERVED]
print("Pin walk. GPIOs to test:", candidates)
print("Each one goes HIGH for", SECONDS_PER_PIN, "seconds, one at a time.\n")

outputs = {}
for gpio in candidates:
    outputs[gpio] = Pin(gpio, Pin.OUT, value=0)

for gpio in candidates:
    print("GPIO {} is HIGH now. Find the header hole that is live.".format(gpio))
    outputs[gpio].value(1)
    time.sleep(SECONDS_PER_PIN)
    outputs[gpio].value(0)

print("\nDone. Every pin is LOW again.")
print("Write down: GPIO number -> label printed next to the hole.")
