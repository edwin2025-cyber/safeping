# Lesson 5: turn button presses into modes. Nothing is sent, it only prints.
#   1 press        -> STATUS
#   2 presses      -> SUSPICIOUS
#   3 or more      -> MEDICAL (fires on the 3rd press, no waiting)
#   hold 2 seconds -> SILENT
# After a mode fires, presses are ignored for a short cooldown. If you keep
# pressing, the cooldown starts over, so mashing the button gives one alert.
# Wire: one side of the button to IO1, the other side to GND (same as lesson 2).

from machine import Pin  # type: ignore
import time

DEBOUNCE_MS = 30            # ignore changes faster than this (the contacts bounce)
GAP_MS = 600                # quiet time after the last press that ends a pattern
HOLD_MS = 2000              # hold this long for SILENT
STATUS_COOLDOWN_MS = 1000   # cooldown after STATUS (not urgent, so short)
ALERT_COOLDOWN_MS = 3000    # cooldown after SUSPICIOUS, MEDICAL or SILENT
MEDICAL_PRESSES = 3         # this many presses is MEDICAL

button = Pin(1, Pin.IN, Pin.PULL_UP)

pressed = False         # is the button down right now?
last_change = 0         # when the button last changed (for debounce)
press_start = 0         # when the current press began
last_release = 0        # when the last press ended
count = 0               # presses so far in this pattern
silent_done = False     # SILENT already fired during this hold
ignore_press = False    # this press started during the cooldown
lockout_until = 0       # presses are ignored until this time
cooldown_ms = 0         # length of the cooldown that is running


def fire(mode, now):
    global count, lockout_until, cooldown_ms
    print("MODE:", mode)
    count = 0
    cooldown_ms = STATUS_COOLDOWN_MS if mode == "STATUS" else ALERT_COOLDOWN_MS
    lockout_until = time.ticks_add(now, cooldown_ms)


# If the button is already down at power on (stuck, or squashed in a bag),
# wait until it is let go. It must never fire an alert by itself at startup.
while button.value() == 0:
    time.sleep_ms(20)

print("Ready. Press the button.")

while True:
    now = time.ticks_ms()
    down = button.value() == 0              # 0 means pressed
    locked = time.ticks_diff(lockout_until, now) > 0

    # 1. Did the button change? (with debounce)
    if down != pressed and time.ticks_diff(now, last_change) >= DEBOUNCE_MS:
        last_change = now
        pressed = down
        if pressed:                         # button just went down
            press_start = now
            silent_done = False
            ignore_press = locked
        else:                               # button just came up
            if ignore_press:
                lockout_until = time.ticks_add(now, cooldown_ms)   # still pressing, stay locked
            elif not silent_done:
                count += 1
                last_release = now
                print("press", count)
                if count >= MEDICAL_PRESSES:
                    fire("MEDICAL", now)

    # 2. Held long enough? SILENT, right away.
    if pressed and not silent_done and time.ticks_diff(now, press_start) >= HOLD_MS:
        silent_done = True
        fire("SILENT", now)

    # 3. Quiet long enough after the last press? Decide STATUS or SUSPICIOUS.
    if count > 0 and not pressed and time.ticks_diff(now, last_release) >= GAP_MS:
        fire("STATUS" if count == 1 else "SUSPICIOUS", now)

    time.sleep_ms(10)