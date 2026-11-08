# Range test, Fob side, with the button.
# Press the button to send one numbered message. The Relay answers with "ack", so the
# Fob can tell you whether the message got through, with no laptop needed.
#   green flash  = the Relay heard it and answered
#   red flash    = sent, but no answer came back (maybe out of range)
#   dim blue blip every few seconds = the Fob is on and waiting
#   slow red blinking = the radio was not found (check wiring, then reset the board)
# Save it on the board as main.py to run by itself on battery.

from machine import Pin, SPI  # type: ignore
import neopixel  # type: ignore
import time
import sx127x

HEARTBEAT_S = 5         # dim blue blip this often. 0 turns it off.
ACK_WAIT_MS = 1500      # how long to wait for the Relay's answer

button = Pin(1, Pin.IN, Pin.PULL_UP)        # one leg to IO1, the other to GND
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


def wait_for_ack(n):
    """Listen for 'ack n' from the Relay. Returns its signal strength, or None."""
    want = "ack {}".format(n).encode()
    deadline = time.ticks_add(time.ticks_ms(), ACK_WAIT_MS)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        left = time.ticks_diff(deadline, time.ticks_ms())
        packet = radio.receive(timeout_ms=left)
        if packet is None:
            return None
        data, rssi, snr = packet
        if data == want:                    # ignore other people's radios
            return rssi
    return None


count = 0
last_beat = time.ticks_ms()
print("Ready. Press the button to send.")

while True:
    if button.value() == 0:
        time.sleep_ms(30)                   # let the contacts settle
        if button.value() == 0:
            sent = radio.send("range {}".format(count).encode())
            rssi = wait_for_ack(count) if sent else None
            if rssi is not None:
                print("message", count, "ANSWERED, reply signal", rssi, "dBm")
                flash((0, 80, 0), 400)
            else:
                print("message", count, "sent, NO ANSWER" if sent else "SEND FAILED")
                flash((80, 0, 0), 400)
            count += 1
            while button.value() == 0:      # wait until the button is let go
                time.sleep_ms(10)
            last_beat = time.ticks_ms()

    if HEARTBEAT_S and time.ticks_diff(time.ticks_ms(), last_beat) >= HEARTBEAT_S * 1000:
        flash((0, 0, 15), 40)
        last_beat = time.ticks_ms()

    time.sleep_ms(10)
