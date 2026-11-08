# Range test, Relay side, with answers. Run it from Thonny and leave it open.
# It prints one line for every message that arrives, tells you when some were missed,
# and answers each one with "ack" so the Fob knows it got through.
# If the Fob has GPS, each line also shows where the Fob was (nogps if it had no fix).
# Every line is also saved to relay_log.txt on the board, so nothing is lost if the
# laptop sleeps or Thonny disconnects. Running the script again starts a new file.
# To read the file back in the Thonny shell:  print(open("relay_log.txt").read())

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
logfile = open("relay_log.txt", "w")


def say(line):
    """Print a line and save it to the file right away."""
    print(line)
    logfile.write(line + "\n")
    logfile.flush()


say("Listening. Start your phone stopwatch now.")
say("time_s  message  signal_dBm  snr_dB  fob_lat  fob_lon  note")

try:
    while True:
        packet = radio.receive(timeout_ms=1000)
        if packet is None:
            continue
        data, rssi, snr = packet
        t = time.ticks_diff(time.ticks_ms(), start) // 1000
        try:
            text = data.decode()
            if not text.startswith("range "):
                raise ValueError
            words = text.split(" ")
            n = int(words[1])
            # A Fob with GPS adds its position after the number: "range 5 34.7254 -86.6555"
            where = "{} {}".format(words[2], words[3]) if len(words) >= 4 else "nogps nogps"
        except (ValueError, IndexError):
            say("{} ignored a packet that is not ours".format(t))
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
        say("{} {} {} {} {} {}".format(t, n, rssi, snr, where, note).rstrip())
        time.sleep_ms(150)                  # give the Fob time to start listening
        radio.send("ack {}".format(n).encode())
except KeyboardInterrupt:
    say("received {} missed {} of {}".format(got, missed, got + missed))
    logfile.close()
