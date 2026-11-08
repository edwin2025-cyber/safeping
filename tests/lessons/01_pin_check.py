# Lesson 1: which header hole is which GPIO?
# Wire: free end of 220 ohm resistor -> LED long leg -> LED short leg -> GND.
# Run this, then touch the free end of the resistor to one header hole at a time.
# When the LED lights, the hole is the GPIO printed in the console.

from machine import Pin
import time

pins = [0, 1, 2, 3, 4, 5, 6]

for p in pins:
    led = Pin(p, Pin.OUT)
    print("GPIO", p, "is ON for 3 seconds")
    led.value(1)
    time.sleep(3)
    led.value(0)