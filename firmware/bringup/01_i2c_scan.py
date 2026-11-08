"""STEP 1. Find out which wires carry I2C and which parts answer on them.

I2C is the two-wire bus on the Qwiic connector. The BME280 pressure sensor, the GPS and
the board's battery gauge all share it. Each part answers to its own address.

The board's schematic says the bus is on GPIO 23 and 24. SparkFun's web page says 6 and 7.
This script tries both and tells you which one is real.

What you should see with the BME280 and GPS plugged into the Qwiic connector:
  0x36  battery gauge (MAX17048, always there, soldered on the board)
  0x42  GPS (SAM-M10Q)
  0x77  pressure sensor (BME280). It shows 0x76 if the jumper on it was cut.
If you only see 0x36, the board is fine and the Qwiic cable or the part is the problem.
"""
from machine import I2C, Pin

import pins

NAMES = {
    0x36: "battery gauge (MAX17048, on the board)",
    0x42: "GPS (SAM-M10Q)",
    0x76: "pressure sensor (BME280, alternate address)",
    0x77: "pressure sensor (BME280)",
}

attempts = [
    (pins.I2C_SDA, pins.I2C_SCL),
    (pins.I2C_ALT[0], pins.I2C_ALT[1]),
    (pins.I2C_ALT[1], pins.I2C_ALT[0]),
]

working = None
for sda, scl in attempts:
    print("Trying SDA = GPIO {}, SCL = GPIO {} ...".format(sda, scl))
    try:
        bus = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=pins.I2C_FREQ)
        found = bus.scan()
    except Exception as err:
        print("   could not start the bus:", err)
        continue
    if not found:
        print("   nothing answered")
        continue
    for address in found:
        print("   0x{:02x}  {}".format(address, NAMES.get(address, "unknown part")))
    if 0x36 in found and working is None:
        working = (sda, scl)

print()
if working:
    print("RESULT: the I2C bus is on SDA = GPIO {}, SCL = GPIO {}.".format(*working))
    if working != (pins.I2C_SDA, pins.I2C_SCL):
        print("That is different from pins.py. Change I2C_SDA and I2C_SCL there.")
    else:
        print("That matches pins.py. Nothing to change.")
else:
    print("RESULT: no battery gauge found on any pair. Check the board and the USB cable.")
