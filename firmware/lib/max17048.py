"""Small driver for the MAX17048 battery fuel gauge built into the SparkFun Thing Plus
ESP32-C5 (I2C address 0x36, on the same bus as the Qwiic port: SDA 23, SCL 24).

It measures the LiPo's voltage and estimates the charge in percent.
Only meaningful when a LiPo is plugged into the board's JST socket. While USB is also
plugged in, the battery is charging, so the voltage reads a little high.

Usage:
    from machine import I2C
    import max17048
    gauge = max17048.MAX17048(I2C(0))
    gauge.millivolts()      # 3700 = 3.70 V
    gauge.percent()         # 0 to 100
"""
VCELL = 0x02
SOC = 0x04
VERSION = 0x08


class MAX17048:
    def __init__(self, i2c, address=0x36):
        self.i2c = i2c
        self.address = address
        self.version = self._read16(VERSION)     # raises OSError if the chip does not answer

    def _read16(self, reg):
        b = self.i2c.readfrom_mem(self.address, reg, 2)
        return (b[0] << 8) | b[1]

    def millivolts(self):
        """Battery voltage. 78.125 microvolts per step (datasheet)."""
        return self._read16(VCELL) * 78125 // 1000000

    def percent(self):
        """State of charge, whole percent, kept between 0 and 100.
        Right after a full charge it can read a bit over 100, so it is capped."""
        raw = self._read16(SOC)
        pct = (raw + 128) >> 8                   # high byte is percent, low byte is 1/256
        return max(0, min(100, pct))
