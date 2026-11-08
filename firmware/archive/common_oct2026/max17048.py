"""MAX17048 battery fuel gauge (already on the SparkFun Thing Plus board).

It sits on the I2C bus at address 0x36 and reports the battery voltage and the charge
percent. main.py will use percent() for the "bat" field of every message.

Usage:
    from machine import I2C, Pin
    i2c = I2C(0, sda=Pin(23), scl=Pin(24), freq=100000)
    gauge = MAX17048(i2c)
    print(gauge.voltage_mv(), gauge.percent())
"""

ADDR = 0x36
REG_VCELL = 0x02      # battery voltage, 78.125 microvolts per step
REG_SOC = 0x04        # charge: high byte = whole percent, low byte = 1/256 percent
REG_VERSION = 0x08    # chip version, the top byte is 0x00 and the low byte starts with 1


class MAX17048:
    def __init__(self, i2c, addr=ADDR):
        self.i2c = i2c
        self.addr = addr

    def _read16(self, reg):
        data = self.i2c.readfrom_mem(self.addr, reg, 2)
        return (data[0] << 8) | data[1]

    def version(self):
        """Should read 0x0010 to 0x001F. Anything else means this is not a MAX17048."""
        return self._read16(REG_VERSION)

    def voltage_mv(self):
        """Battery voltage in millivolts, whole number."""
        raw = self._read16(REG_VCELL)
        return raw * 78125 // 1000000

    def percent(self):
        """Charge as a whole number from 0 to 100. This is what goes in the "bat" field."""
        high = self.i2c.readfrom_mem(self.addr, REG_SOC, 2)[0]
        return max(0, min(100, high))
