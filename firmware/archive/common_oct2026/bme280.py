"""BME280 pressure and temperature sensor (SparkFun Qwiic breakout).

The Fob uses the pressure to work out which floor it is on. The Reference sits on the
ground floor and sends the baseline. The server subtracts the two.

What it returns, in the whole-number units that message-format.md uses:
    p = pressure in pascals          (101325 is sea level on a standard day)
    t = temperature in hundredths of a degree C   (2150 means 21.50 C)

Written with whole-number math only, the way Bosch's datasheet does it. No floats, so
the answer is the same on the board and on a laptop.

Usage:
    sensor = BME280(i2c)
    t, p = sensor.read()
"""
import time

ADDR_DEFAULT = 0x77     # SparkFun breakout default. Cutting the jumper on it makes it 0x76.
ADDR_ALT = 0x76

REG_ID = 0xD0
REG_RESET = 0xE0
REG_CTRL_HUM = 0xF2
REG_STATUS = 0xF3
REG_CTRL_MEAS = 0xF4
REG_CONFIG = 0xF5
REG_DATA = 0xF7

CHIP_BME280 = 0x60
CHIP_BMP280 = (0x56, 0x57, 0x58)   # looks the same but has no humidity. Pressure still works.


def _s16(lo, hi):
    value = (hi << 8) | lo
    return value - 65536 if value > 32767 else value


def _u16(lo, hi):
    return (hi << 8) | lo


def _div(a, b):
    """Integer divide that rounds toward zero, like C does."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


class BME280:
    def __init__(self, i2c, addr=ADDR_DEFAULT):
        self.i2c = i2c
        self.addr = addr
        self.chip_id = i2c.readfrom_mem(addr, REG_ID, 1)[0]
        if self.chip_id != CHIP_BME280 and self.chip_id not in CHIP_BMP280:
            raise OSError("not a BME280 (chip id 0x{:02x})".format(self.chip_id))
        self._load_calibration()
        self.t_fine = 0

    def _load_calibration(self):
        c = self.i2c.readfrom_mem(self.addr, 0x88, 24)
        self.T1 = _u16(c[0], c[1])
        self.T2 = _s16(c[2], c[3])
        self.T3 = _s16(c[4], c[5])
        self.P1 = _u16(c[6], c[7])
        self.P2 = _s16(c[8], c[9])
        self.P3 = _s16(c[10], c[11])
        self.P4 = _s16(c[12], c[13])
        self.P5 = _s16(c[14], c[15])
        self.P6 = _s16(c[16], c[17])
        self.P7 = _s16(c[18], c[19])
        self.P8 = _s16(c[20], c[21])
        self.P9 = _s16(c[22], c[23])

    def compensate_temperature(self, adc_t):
        """Raw 20-bit reading to hundredths of a degree C. Also sets self.t_fine."""
        var1 = (((adc_t >> 3) - (self.T1 << 1)) * self.T2) >> 11
        var2 = (((((adc_t >> 4) - self.T1) * ((adc_t >> 4) - self.T1)) >> 12) * self.T3) >> 14
        self.t_fine = var1 + var2
        return (self.t_fine * 5 + 128) >> 8

    def compensate_pressure(self, adc_p):
        """Raw 20-bit reading to pascals. Call compensate_temperature first."""
        var1 = self.t_fine - 128000
        var2 = var1 * var1 * self.P6
        var2 = var2 + ((var1 * self.P5) << 17)
        var2 = var2 + (self.P4 << 35)
        var1 = ((var1 * var1 * self.P3) >> 8) + ((var1 * self.P2) << 12)
        var1 = (((1 << 47) + var1) * self.P1) >> 33
        if var1 == 0:
            return 0
        p = 1048576 - adc_p
        p = _div((((p << 31) - var2) * 3125), var1)
        var1 = (self.P9 * (p >> 13) * (p >> 13)) >> 25
        var2 = (self.P8 * p) >> 19
        p = ((p + var1 + var2) >> 8) + (self.P7 << 4)
        return (p + 128) >> 8          # the chip gives pascals times 256, so round and shift

    def read(self):
        """Take one reading. Returns (t, p): hundredths of a degree C and pascals."""
        # humidity setting must be written before the measurement control register
        self.i2c.writeto_mem(self.addr, REG_CTRL_HUM, bytes([0x01]))
        # temperature x2, pressure x16, forced mode (take one reading, then sleep)
        self.i2c.writeto_mem(self.addr, REG_CTRL_MEAS, bytes([(2 << 5) | (5 << 2) | 1]))
        for _ in range(40):                       # wait up to about 200 ms
            if not (self.i2c.readfrom_mem(self.addr, REG_STATUS, 1)[0] & 0x08):
                break
            time.sleep_ms(5)
        d = self.i2c.readfrom_mem(self.addr, REG_DATA, 6)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        t = self.compensate_temperature(adc_t)
        p = self.compensate_pressure(adc_p)
        return t, p
