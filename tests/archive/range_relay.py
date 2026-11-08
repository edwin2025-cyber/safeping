# Range test, Relay side. Run it from Thonny and leave it open while the Fob walks away.
# It prints one line for every message that arrives, and tells you when some were missed.

from machine import Pin, SPI  # type: ignore
import time
import sx127x

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(8), miso=Pin(9))
cs = Pin(26, Pin.OUT, value=1)
reset = Pin(6, Pin.OUT, value=1)

radio = sx127x.SX127x(spi, cs, reset)
radio.begin()

start = time.ticks_ms()
got = 0         # messages received
missed = 0      # messages the Fob sent that never arrived
last = None     # number of the last message received

print("Listening. Start your phone stopwatch now.")
print("time_s  message  signal_dBm  snr_dB  note")

try:
    while True:
        packet = radio.receive(timeout_ms=1000)
        if packet is None:
            continue
        data, rssi, snr = packet
        t = time.ticks_diff(time.ticks_ms(), start) // 1000
        try:
            n = int(data.decode().split(" ")[1])
        except (ValueError, IndexError):
            print(t, "unreadable packet", data)
            continue
        note = ""
        if last is not None and n <= last:
            note = "Fob restarted"
        elif last is not None and n > last + 1:
            lost = n - last - 1
            missed += lost
            note = "missed {}".format(lost)
        got += 1
        last = n
        print(t, n, rssi, snr, note)
except KeyboardInterrupt:
    print("received", got, "missed", missed, "of", got + missed)