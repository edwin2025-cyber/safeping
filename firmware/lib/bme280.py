"""Small driver for the Bosch BME280 (pressure and temperature) over I2C.

SafePing uses it for floor detection: the server compares the Fob's pressure with the
Reference board's pressure. One floor is about 3.5 m, which is about 40 Pa.

Only pressure and temperature are read. Humidity is skipped (not needed, saves time).
The math is the integer compensation from the Bosch BME280 datasheet (section 4.2.3
and 8.2), so there are no floats and the result matches the message format:
  pressure in whole pascals (101325)
  temperature in hundredths of a degree C (2150 = 21.50 C)

Settings: forced mode (the chip sleeps between readings, good for battery), pressure
oversampling x16, temperature x2, IIR filter OFF. The filter is off on purpose: in
forced mode the filter mixes in the previous reading, which on a Fob could be minutes
old and from a different floor.

Usage:
    from machine import I2C
    import bme280
    sensor = bme280.BME280(I2C(0))       # address 0x77 (SparkFun default) or 0x76
    p, t = sensor.read()                  # (pascals, hundredths of C)
"""
import time

CHIP_ID_REG = 0xD0
CHIP_ID = 0x60          # 0x58 would be a BMP280 (no humidity, same pressure math)
RESET_REG = 0xE0
CTRL_HUM = 0xF2
STATUS = 0xF3
CTRL_MEAS = 0xF4
CONFIG = 0xF5
DATA = 0xF7

OSRS_T = 0b010          # temperature oversampling x2
OSRS_P = 0b101          # pressure oversampling x16
FORCED = 0b01


def _u16(b, i):
    return b[i] | (b[i + 1] << 8)


def _s16(b, i):
    v = _u16(b, i)
    return v - 65536 if v > 32767 else v


class BME280:
    def __init__(self, i2c, address=0x77):
        self.i2c = i2c
        self.address = address
        chip = self._read(CHIP_ID_REG, 1)[0]
        if chip not in (0x60, 0x58):
            raise OSError("BME280 not found at 0x{:02x} (chip id 0x{:02x})".format(address, chip))
        self.chip_id = chip
        self._write(RESET_REG, 0xB6)
        time.sleep_ms(5)
        c = self._read(0x88, 24)            # calibration, written at the factory
        self.T1, self.T2, self.T3 = _u16(c, 0), _s16(c, 2), _s16(c, 4)
        self.P1 = _u16(c, 6)
        self.P2, self.P3, self.P4 = _s16(c, 8), _s16(c, 10), _s16(c, 12)
        self.P5, self.P6, self.P7 = _s16(c, 14), _s16(c, 16), _s16(c, 18)
        self.P8, self.P9 = _s16(c, 20), _s16(c, 22)
        if chip == 0x60:
            self._write(CTRL_HUM, 0x00)     # humidity off (must be written before CTRL_MEAS)
        self._write(CONFIG, 0x00)           # filter off
        self._write(CTRL_MEAS, (OSRS_T << 5) | (OSRS_P << 2))   # sleep until asked

    def _read(self, reg, n):
        return self.i2c.readfrom_mem(self.address, reg, n)

    def _write(self, reg, value):
        self.i2c.writeto_mem(self.address, reg, bytes([value]))

    def read_raw(self):
        """Start one measurement, wait for it, return (adc_p, adc_t)."""
        self._write(CTRL_MEAS, (OSRS_T << 5) | (OSRS_P << 2) | FORCED)
        time.sleep_ms(45)                   # about 43 ms at these settings
        for _ in range(20):
            if not self._read(STATUS, 1)[0] & 0x08:
                break
            time.sleep_ms(5)
        d = self._read(DATA, 6)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        return adc_p, adc_t

    def compensate(self, adc_p, adc_t):
        """Datasheet integer math. Returns (pascals, hundredths of C)."""
        var1 = (((adc_t >> 3) - (self.T1 << 1)) * self.T2) >> 11
        var2 = (((((adc_t >> 4) - self.T1) * ((adc_t >> 4) - self.T1)) >> 12) * self.T3) >> 14
        t_fine = var1 + var2
        t = (t_fine * 5 + 128) >> 8

        var1 = t_fine - 128000
        var2 = var1 * var1 * self.P6
        var2 = var2 + ((var1 * self.P5) << 17)
        var2 = var2 + (self.P4 << 35)
        var1 = ((var1 * var1 * self.P3) >> 8) + ((var1 * self.P2) << 12)
        var1 = (((1 << 47) + var1) * self.P1) >> 33
        if var1 == 0:
            return None, t                  # avoids dividing by zero
        p = 1048576 - adc_p
        p = (((p << 31) - var2) * 3125) // var1
        var1 = (self.P9 * (p >> 13) * (p >> 13)) >> 25
        var2 = (self.P8 * p) >> 19
        p = ((p + var1 + var2) >> 8) + (self.P7 << 4)    # pascals times 256
        return (p + 128) >> 8, t

    def read(self, samples=1):
        """(pascals, hundredths of C). samples > 1 averages several readings."""
        ps, ts = [], []
        for _ in range(samples):
            p, t = self.compensate(*self.read_raw())
            if p is not None:
                ps.append(p)
                ts.append(t)
        if not ps:
            return None, None
        return (sum(ps) + len(ps) // 2) // len(ps), (sum(ts) + len(ts) // 2) // len(ts)
