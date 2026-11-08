"""STEP 4. Prove the GPS is sending data, then wait for a position.

The GPS needs to see the sky. Hold it at a window or go outside. The first fix after a
cold start takes about 30 seconds to a few minutes. Indoors it may never get one. That
is normal, and it is why the Fob also uses pressure for floors. Press Ctrl+C to stop.

Two separate things to check:
  1. "sentences" goes up every second.  Data is flowing over the wire. Even with no
     sky view this must work. If it stays at 0, the cable or the connection is the
     problem (run 01_i2c_scan.py, you should see 0x42).
  2. "fix" turns into numbers.            This needs sky. lat and lon print in
     microdegrees, the unit message-format.md uses. 34730123 means 34.730123 degrees.

Check it on a map: type the decimal numbers into a maps site. You should be within
about 10 meters of where you stand. "acc" is a rough guess in meters (HDOP x 5).
"""
import time

import gnss
import hw

i2c = hw.make_i2c()
if gnss.ADDR not in i2c.scan():
    raise OSError("No GPS at 0x42. Run 01_i2c_scan.py to see what is connected.")

gps = gnss.GNSS(i2c)


def decimal(micro):
    """microdegrees to a text like 34.730123, without using floats"""
    sign = "-" if micro < 0 else ""
    micro = abs(micro)
    return "{}{}.{:06d}".format(sign, micro // 1000000, micro % 1000000)


print("Reading the GPS. Hold it where it can see the sky.")
started = time.time()
while True:
    for _ in range(4):
        gps.update()
        time.sleep(0.25)
    fix = gps.fix()
    waited = int(time.time() - started)
    head = "{:>3}s  sentences {:>4}  bad {}  satellites {:>2}".format(
        waited, gps.sentences, gps.bad, gps.sats)
    if fix is None:
        print(head + "  fix: none yet")
    else:
        lat, lon, acc = fix
        print(head + "  FIX  lat {} lon {}  acc {} m   ({}, {})".format(
            lat, lon, acc, decimal(lat), decimal(lon)))
