# Motor test for the SafePing Fob. Runs on the Fob board (press Run in Thonny, do not
# save it as main.py).
#
# Circuit: IO3 -> 1 k resistor -> PN2222 base. Emitter to GND. Motor between 3V3 and
# the collector. 1N4001 across the motor, stripe toward 3V3. Never wire the motor
# straight to a pin.
#
# Strength is set with PWM: the pin switches on and off 200 times a second, and the
# duty (percent of time on) sets how hard the motor buzzes.
#
# Part 1 plays 4 strengths. Part 2 plays the buzz patterns at the strength you pick
# below. Each one is printed right before it plays, with a pause after it.

from machine import Pin, PWM  # type: ignore
import time

MOTOR_PIN = 3
FREQ_HZ = 200
PATTERN_STRENGTH = 80        # percent, used for part 2. Change this and run again.
PARTS = (1, 2, 3)                 # which parts to run. (1, 2, 3) runs everything.
CHOICE_STRENGTH = 100        # percent, used for part 3


def duty(percent):
    return int(65535 * percent / 100)


motor = PWM(Pin(MOTOR_PIN), freq=FREQ_HZ, duty_u16=0)


def buzz(ms, percent):
    motor.duty_u16(duty(percent))
    time.sleep_ms(ms)
    motor.duty_u16(0)


def play(name, steps, percent):
    """steps is a list of (on 1/0, milliseconds), the same format as PATTERNS in main.py"""
    print("  ", name, steps)
    for on, ms in steps:
        motor.duty_u16(duty(percent) if on else 0)
        time.sleep_ms(ms)
    motor.duty_u16(0)
    time.sleep_ms(1500)


try:
    if 1 in PARTS:
        print("Part 1: strength, 0.5 s each, 1.5 s apart")
        for percent in (40, 60, 80, 100):
            print("  ", percent, "percent")
            buzz(500, percent)
            time.sleep_ms(1500)

    if 2 in PARTS:
        print("Part 2: patterns at", PATTERN_STRENGTH, "percent")
        play("tick (each button press)", [(1, 40)], PATTERN_STRENGTH)
        play("short (STATUS sent, SILENT hold registered)", [(1, 150)], PATTERN_STRENGTH)
        play("one (SUSPICIOUS started)", [(1, 300)], PATTERN_STRENGTH)
        play("long (not used yet)", [(1, 800)], PATTERN_STRENGTH)
        play("ok, double (alert sent)", [(1, 100), (0, 100), (1, 100)], PATTERN_STRENGTH)
        play("fail, three quick (not sent)",
             [(1, 100), (0, 100), (1, 100), (0, 100), (1, 100)], PATTERN_STRENGTH)
        play("MEDICAL steady, 2 s (today it buzzes the whole cancel window)", [(1, 2000)], PATTERN_STRENGTH)
        play("MEDICAL pulsed idea, 2 s", [(1, 200), (0, 100)] * 6 + [(1, 200)], PATTERN_STRENGTH)

    if 3 in PARTS:
        # The motor needs about 50 to 100 ms just to spin up, so 100 ms pulses feel weak.
        # These use longer pulses. "Sent" and "not sent" must feel clearly different,
        # because for SILENT the buzz is the only feedback the wearer gets.
        print("Part 3: stronger choices at", CHOICE_STRENGTH, "percent")
        print(" SENT choices")
        play("ok A: two medium", [(1, 250), (0, 150), (1, 250)], CHOICE_STRENGTH)
        play("ok B: two long", [(1, 400), (0, 200), (1, 400)], CHOICE_STRENGTH)
        print(" NOT SENT choices")
        play("fail A: three medium", [(1, 250), (0, 150)] * 2 + [(1, 250)], CHOICE_STRENGTH)
        play("fail B: one long 1.2 s", [(1, 1200)], CHOICE_STRENGTH)
        play("fail C: long, short, long", [(1, 600), (0, 150), (1, 200), (0, 150), (1, 600)], CHOICE_STRENGTH)
    print("Done")
finally:
    motor.duty_u16(0)          # always leave the motor off, even after Ctrl+C or an error
    motor.deinit()
    Pin(MOTOR_PIN, Pin.OUT, value=0)