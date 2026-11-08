# Sensor check for the SafePing Fob. Press Run in Thonny (do not save as main.py).
# Needs bme280.py and max17048.py saved on the board.
#
# Prints pressure, temperature and battery once a second for 40 seconds.
# Seconds 0 to 20: leave the board still on the desk (this shows the noise).
# Seconds 20 to 40: lift the board straight up about 1 m and hold it there.
# Going up 1 m should drop the pressure by about 12 Pa.

from machine import I2C  # type: ignore
import time
import bme280
import max17048

i2c = I2C(0)                 # SDA 23, SCL 24 on this board
print("I2C devices:", [hex(a) for a in i2c.scan()])

sensor = bme280.BME280(i2c)
print("BME280 chip id 0x{:02x} (0x60 = BME280)".format(sensor.chip_id))
try:
    gauge = max17048.MAX17048(i2c)
    print("MAX17048 version 0x{:04x}".format(gauge.version))
except OSError as err:
    gauge = None
    print("battery gauge not answering:", err)

first = None
print("sec  pressure_Pa  change_Pa  temp_C  battery_mV  battery_pct")
for sec in range(40):
    if sec == 20:
        print("---- lift the board about 1 m now and hold it ----")
    p, t = sensor.read()
    if first is None:
        first = p
    if gauge:
        mv, pct = gauge.millivolts(), gauge.percent()
    else:
        mv, pct = "", ""
    print("{:3d}  {:11d}  {:9d}  {:6.2f}  {:>10}  {:>11}".format(sec, p, p - first, t / 100, mv, pct))
    time.sleep_ms(1000 - 45)
print("Done")
