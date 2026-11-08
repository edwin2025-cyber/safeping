# GPS check. Run it OUTSIDE with the GPS wing stacked on the Fob board and the
# wing's flat antenna facing the sky. It prints one line a second for 3 minutes.
# The first fix can take 30 seconds or much longer. Indoors it will not get one.

import time
from gps import GPS

gps = GPS()
print("Waiting for GPS data. Stay outside with a clear view of the sky.")

start = time.ticks_ms()
last = 0
while time.ticks_diff(time.ticks_ms(), start) < 180000:
    gps.update()
    now = time.ticks_ms()
    if time.ticks_diff(now, last) >= 1000:
        last = now
        t = time.ticks_diff(now, start) // 1000
        if gps.bytes_seen == 0:
            print(t, "s: no data from the wing at all. Check it is stacked, or try uart_id=0 in gps.py")
        elif gps.has_fix:
            print(t, "s: FIX", gps.lat_text(), gps.lon_text(), "satellites", gps.sats, "hdop", gps.hdop)
        else:
            print(t, "s: no fix yet, satellites", gps.sats, "good lines", gps.sentences, "bad lines", gps.bad)
    time.sleep_ms(20)
print("done")
