"""STEP 2. Read the battery gauge that is already on the board.

Plug the LiPo battery into the JST connector first. With no battery, the numbers mean
nothing. Press Ctrl+C to stop.

What you should see:
  version   0x0010 to 0x001F          (proves the gauge answered)
  voltage   about 3300 to 4200 mV     (a LiPo: 4200 is full, 3300 is nearly empty)
  charge    0 to 100 percent
Plug in USB while it runs. The voltage should rise a little and the yellow CHG light
should come on. That proves the charger and the gauge both work.

main.py will send the percent as the "bat" field of every message.
"""
import time

import hw
import max17048

i2c = hw.make_i2c()
gauge = max17048.MAX17048(i2c)
print("gauge version: 0x{:04x}".format(gauge.version()))

while True:
    print("battery {} mV  {} %".format(gauge.voltage_mv(), gauge.percent()))
    time.sleep(1)
