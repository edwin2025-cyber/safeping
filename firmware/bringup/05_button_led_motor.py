"""STEP 5. Test the button, the NeoPixel and the vibration motor together.

Wire these first (power OFF, USB unplugged), using the pins in pins.py:
  button     one leg to the BUTTON pin, the other leg to GND
  NeoPixel   V to 3V3, G to GND, IN (data in) to the NEOPIXEL pin
  motor      see docs/hardware-connections.md. The motor is never wired straight to a pin.
No switch yet? Touch a wire from the BUTTON pin to GND. It does the same thing.

What you should see:
  1. The NeoPixel shows red, green, blue, then white for one second each.
     If red looks green, the part uses a different color order. Tell us.
     If the colors are dim or flicker, move the NeoPixel V wire from 3V3 to VBAT.
  2. Press the button. The console prints PRESSED, the pixel turns white and the motor buzzes.
  3. Release. The console prints how long you held it. The pixel and motor turn off.
  4. Hold it for 5 seconds. The console says SILENT HOLD. This is the same timing main.py uses.
Press Ctrl+C to stop. The motor is forced off first.
"""
import time

from machine import Pin
import neopixel

import pins

BRIGHTNESS = 25     # percent. NeoPixels are very bright up close.


def scaled(rgb):
    return tuple(c * BRIGHTNESS // 100 for c in rgb)


motor = Pin(pins.MOTOR, Pin.OUT, value=0)         # off first, always
button = Pin(pins.BUTTON, Pin.IN, Pin.PULL_UP)     # pressed = 0
pixel = neopixel.NeoPixel(Pin(pins.NEOPIXEL), 1)


def show(rgb):
    pixel[0] = scaled(rgb)
    pixel.write()


try:
    for name, rgb in (("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)),
                      ("BLUE", (0, 0, 255)), ("WHITE", (255, 255, 255))):
        print("NeoPixel:", name)
        show(rgb)
        time.sleep(1)
    show((0, 0, 0))
    print("\nNow press the button.")

    last = button.value()
    pressed_at = 0
    while True:
        now = button.value()
        if now != last:
            time.sleep_ms(30)                      # let the contact settle
            now = button.value()
        if now != last:
            last = now
            if now == 0:
                pressed_at = time.ticks_ms()
                print("PRESSED")
                show((255, 255, 255))
                motor.value(1)
            else:
                held = time.ticks_diff(time.ticks_ms(), pressed_at)
                print("RELEASED after {} ms{}".format(held, "   SILENT HOLD" if held >= 5000 else ""))
                show((0, 0, 0))
                motor.value(0)
        time.sleep_ms(10)
finally:
    motor.value(0)
    show((0, 0, 0))
