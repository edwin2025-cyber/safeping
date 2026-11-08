"""STEP 3. Read pressure and temperature, and check that pressure follows height.

Floor detection works because pressure falls as you go up. About 12 Pa per meter, so
about 42 Pa per floor (the default PA_PER_FLOOR on the server). Press Ctrl+C to stop.

What you should see:
  chip id   0x60 (BME280). 0x58 is a BMP280, which still works for pressure.
  pressure  about 98000 to 102000 Pa in Huntsville. It drifts a few Pa with the weather.
  temp      room temperature, as hundredths of a degree (2150 means 21.50 C)

The height test (this is the real proof the sensor is useful):
  1. Keep the board still for the first few seconds. It records a baseline, then prints a line every second.
  2. Lift the board slowly from the floor to above your head (about 2 m).
  3. The "change" column should go down by about 20 to 25 Pa. Lower it and it comes back.
  4. Later, carry it up a flight of stairs. About 40 Pa per floor.
Numbers wobble by 1 or 2 Pa, so each line is an average of 5 readings.
"""
import time

import hw
import bme280

i2c = hw.make_i2c()
found = i2c.scan()
address = bme280.ADDR_DEFAULT if bme280.ADDR_DEFAULT in found else bme280.ADDR_ALT
if address not in found:
    raise OSError("No BME280 at 0x77 or 0x76. Run 01_i2c_scan.py to see what is connected.")

sensor = bme280.BME280(i2c, address)
print("chip id: 0x{:02x}  address: 0x{:02x}".format(sensor.chip_id, address))


def averaged(count):
    t_total = p_total = 0
    for _ in range(count):
        t, p = sensor.read()
        t_total += t
        p_total += p
    return t_total // count, p_total // count


print("Recording the baseline for a few seconds. Keep the board still.")
base_t, base_p = averaged(10)
print("baseline: {} Pa, {} (hundredths of C)".format(base_p, base_t))

while True:
    t, p = averaged(5)
    print("pressure {} Pa   temp {}   change {:+d} Pa".format(p, t, p - base_p))
    time.sleep(1)
