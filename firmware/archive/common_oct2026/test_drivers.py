"""Desktop test for the part drivers. No hardware needed.

  python test_drivers.py

Each driver is run against a fake part, so we can check the math and the byte handling
before any real part arrives:
  max17048.py  battery gauge   checked against the voltage and percent formulas
  bme280.py    pressure sensor checked against Bosch's own worked example
  gnss.py      GPS             checked against the pynmea2 library (if installed)
  sx127x.py    LoRa radio      checked against a software model of the chip

This file is for your laptop. Do not copy it to the board."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# MicroPython's time.sleep_ms does not exist on a laptop. Make it instant.
SLEPT = [0]


def _sleep_ms(ms):
    SLEPT[0] += ms


time.sleep_ms = _sleep_ms

import bme280      # noqa: E402
import gnss        # noqa: E402
import max17048    # noqa: E402
import sx127x      # noqa: E402

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  ok    ", name)
    else:
        failed += 1
        print("  FAIL  ", name, detail)


# ------------------------------------------------------------------ fake I2C
class FakeI2C:
    """A bus with one device. regs maps a register number to bytes. Reading n bytes from
    a register gives the bytes stored there, padded with zeros."""

    def __init__(self, regs=None):
        self.regs = regs or {}
        self.writes = []

    def readfrom_mem(self, addr, reg, n):
        data = bytes(self.regs.get(reg, b""))
        return (data + bytes(n))[:n]

    def writeto_mem(self, addr, reg, data):
        self.writes.append((reg, bytes(data)))


def test_battery():
    print("\nMAX17048 battery gauge")
    # 3.900 V is 3,900,000 microvolts / 78.125 = 49920 steps = 0xC300
    i2c = FakeI2C({0x02: b"\xC3\x00", 0x04: b"\x4B\x80", 0x08: b"\x00\x12"})
    g = max17048.MAX17048(i2c)
    check("voltage 0xC300 reads 3900 mV", g.voltage_mv() == 3900, g.voltage_mv())
    check("charge 0x4B80 reads 75 percent", g.percent() == 75, g.percent())
    check("version register reads back", g.version() == 0x0012)
    i2c.regs[0x04] = b"\x82\x00"
    check("percent never goes over 100", g.percent() == 100)
    i2c.regs[0x02] = b"\xD7\x00"     # 4.3 V, more than a LiPo should ever show
    check("4.3 V reads 4300 mV (no clamping of the raw voltage)", g.voltage_mv() == 4300, g.voltage_mv())


def _le16(v):
    v &= 0xFFFF
    return bytes([v & 0xFF, v >> 8])


def test_pressure():
    print("\nBME280 pressure sensor")
    # Bosch's worked example (BMP280 datasheet section 3.12, the BME280 uses the same math):
    # these calibration numbers and raw readings must give 25.08 C and 100653.27 Pa.
    cal = [27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000]
    cal_bytes = b"".join(_le16(v) for v in cal)
    adc_p, adc_t = 415148, 519888
    data = bytes([(adc_p >> 12) & 0xFF, (adc_p >> 4) & 0xFF, (adc_p & 0xF) << 4,
                  (adc_t >> 12) & 0xFF, (adc_t >> 4) & 0xFF, (adc_t & 0xF) << 4])
    i2c = FakeI2C({0xD0: b"\x60", 0x88: cal_bytes, 0xF3: b"\x00", 0xF7: data})
    s = bme280.BME280(i2c)
    t, p = s.read()
    check("temperature is 2508 (25.08 C)", t == 2508, t)
    check("pressure is 100653 Pa", p == 100653, p)
    check("it started a forced-mode reading", (0xF4, bytes([(2 << 5) | (5 << 2) | 1])) in i2c.writes)
    check("humidity setting was written before the measurement register",
          [r for r, _ in i2c.writes][:2] == [0xF2, 0xF4])
    # sanity of the 'c-style divide' helper
    check("divide rounds toward zero", bme280._div(-7, 2) == -3 and bme280._div(7, 2) == 3)
    try:
        bme280.BME280(FakeI2C({0xD0: b"\x00"}))
        check("wrong chip id is refused", False)
    except OSError:
        check("wrong chip id is refused", True)
    bmp = FakeI2C({0xD0: b"\x58", 0x88: cal_bytes, 0xF3: b"\x00", 0xF7: data})
    check("a BMP280 (no humidity) is accepted, since pressure still works", bme280.BME280(bmp).read()[1] == 100653)


# ------------------------------------------------------------------ GPS
def nmea(body):
    value = 0
    for ch in body:
        value ^= ord(ch)
    return "${}*{:02X}".format(body, value)


class FakeGPS:
    """Serves a text stream the way the u-blox I2C port does: a byte count in 0xFD and
    0xFE, then the bytes at 0xFF. 0xFFFF in the count means nothing is waiting."""

    def __init__(self, text=b""):
        self.stream = bytearray(text)

    def feed(self, text):
        self.stream += text

    def readfrom_mem(self, addr, reg, n):
        if reg == 0xFD:
            if not self.stream:
                return b"\xFF\xFF"
            return bytes([len(self.stream) >> 8, len(self.stream) & 0xFF])
        if reg == 0xFF:
            out = bytes(self.stream[:n])
            del self.stream[:n]
            return out
        return bytes(n)


def test_gps():
    print("\nGPS (SAM-M10Q over I2C)")
    gga = nmea("GNGGA,092750.000,5321.6802,N,00630.3372,W,1,8,1.03,61.7,M,55.2,M,,")
    rmc = nmea("GNRMC,092750.000,A,5321.6802,N,00630.3372,W,0.02,31.66,280511,,,A")
    check("checksum is accepted when right", gnss.checksum_ok(gga))
    check("checksum is refused when wrong", not gnss.checksum_ok(gga.replace("1.03", "1.04")))
    info = gnss.parse_sentence(gga)
    check("latitude 5321.6802 N is 53361337 microdegrees", info["lat"] == 53361337, info)
    check("longitude 00630.3372 W is -6505620 microdegrees", info["lon"] == -6505620, info)
    check("satellites and HDOP are read (8 sats, HDOP 1.0)", info["sats"] == 8 and info["hdop_x10"] == 10, info)
    check("south and west are negative", gnss._to_microdegrees("3400.0000", "S", 2) == -34000000
          and gnss._to_microdegrees("08600.0000", "W", 3) == -86000000)
    check("rounding is to the nearest microdegree", gnss._to_microdegrees("0000.0001", "N", 2) == 2)
    try:
        import pynmea2
        ref = pynmea2.parse(gga)
        lat_ref = round(float(ref.latitude) * 1e6)
        lon_ref = round(float(ref.longitude) * 1e6)
        check("matches the pynmea2 library", (info["lat"], info["lon"]) == (lat_ref, lon_ref), (lat_ref, lon_ref))
        worst = 0
        for deg, mins in ((34, "43.8074"), (0, "00.0001"), (89, "59.9999"), (12, "34.56789")):
            text = "{:02d}{}".format(deg, mins)
            ours = gnss._to_microdegrees(text, "N", 2)
            theirs = round((deg + float(mins) / 60) * 1e6)
            worst = max(worst, abs(ours - theirs))
        check("conversion agrees with float math to within 1 microdegree", worst <= 1, worst)
    except ImportError:
        print("  skip   pynmea2 not installed (pip install pynmea2) so the cross-check was skipped")

    # a stream with no fix, then a fix, split across reads, with junk and a corrupted line
    bus = FakeGPS()
    gps = gnss.GNSS(bus)
    gps.update()
    check("no data waiting is handled (0xFFFF count)", gps.fix() is None and gps.sentences == 0)
    nofix = nmea("GNGGA,092750.000,,,,,0,00,99.99,,,,,,")
    bus.feed((nofix + "\r\n").encode())
    gps.update()
    check("a sentence with no fix gives no position", gps.fix() is None and gps.sentences == 1)
    line = (rmc + "\r\n" + gga + "\r\n").encode()
    bus.feed(line[:50])
    gps.update()
    check("half a sentence waits for the rest", gps.fix() is None)
    bus.feed(line[50:])
    gps.update()
    fix = gps.fix()
    check("a fix gives (lat, lon, acc)", fix == (53361337, -6505620, 5), fix)
    bus.feed(b"\xff\xff\xff$GNGGA,garbage*00\r\n")
    gps.update()
    check("a corrupted line is counted and ignored", gps.bad == 1 and gps.fix() == fix, (gps.bad, gps.fix()))
    lost = nmea("GNGGA,092800.000,,,,,0,00,99.99,,,,,,")
    bus.feed((lost + "\r\n").encode())
    gps.update()
    check("losing the fix clears the position", gps.fix() is None)


# ------------------------------------------------------------------ LoRa radio
AIR = []     # packets "in the air" between two fake radios


class FakeSX1276:
    """A software model of the parts of the SX1276 that sx127x.py uses."""

    def __init__(self, version=0x12):
        self.regs = {0x42: version}
        self.fifo = bytearray(256)
        self.ptr = 0
        self.log = []                      # every register write, in order

    def write_readinto(self, out, back):
        addr = out[0] & 0x7F
        writing = bool(out[0] & 0x80)
        if addr == 0x00:                  # FIFO, burst access, pointer moves on
            self.ptr = self.regs.get(0x0D, 0)
            for i in range(1, len(out)):
                if writing:
                    self.fifo[self.ptr & 0xFF] = out[i]
                else:
                    back[i] = self.fifo[self.ptr & 0xFF]
                self.ptr += 1
            if writing:
                self.regs[0x0D] = self.ptr & 0xFF
            return
        if writing:
            self.log.append((addr, out[1]))
            if addr == 0x12:
                self.regs[0x12] = self.regs.get(0x12, 0) & ~out[1] & 0xFF   # write 1 to clear
                return
            self.regs[addr] = out[1]
            if addr == 0x01 and (out[1] & 0x07) == 0x03:                    # transmit
                length = self.regs.get(0x22, 0)
                base = self.regs.get(0x0E, 0)
                AIR.append(bytes(self.fifo[base:base + length]))
                self.regs[0x12] = self.regs.get(0x12, 0) | 0x08            # TxDone
        else:
            if addr == 0x12 and (self.regs.get(0x01, 0) & 0x07) == 0x05 and AIR:
                data = AIR.pop(0)                                          # a packet arrives
                base = self.regs.get(0x0F, 0)
                self.fifo[base:base + len(data)] = data
                self.regs[0x13] = len(data)
                self.regs[0x10] = base
                self.regs[0x1A] = 100                                      # RSSI -57 dBm
                self.regs[0x19] = 20                                       # SNR +5.0 dB
                self.regs[0x12] = self.regs.get(0x12, 0) | 0x40
            back[1] = self.regs.get(addr, 0)


class FakePin:
    def __init__(self):
        self.level = None
        self.history = []

    def value(self, v=None):
        if v is None:
            return self.level
        self.level = v
        self.history.append(v)


def make_radio(chip):
    return sx127x.SX127x(chip, FakePin(), FakePin())


def test_lora():
    print("\nLoRa radio (SX1276 / RFM95W)")
    chip = FakeSX1276()
    radio = make_radio(chip)
    version = radio.begin()
    check("version register is read and accepted (0x12)", version == 0x12)
    check("reset pin was pulsed low then high", radio.reset_pin.history == [0, 1], radio.reset_pin.history)
    check("915 MHz becomes register bytes E4 C0 00",
          (chip.regs[0x06], chip.regs[0x07], chip.regs[0x08]) == (0xE4, 0xC0, 0x00),
          (chip.regs[0x06], chip.regs[0x07], chip.regs[0x08]))
    check("modem settings are 0x72, 0x74, 0x04 (125 kHz, SF7, 4/5, CRC on)",
          (chip.regs[0x1D], chip.regs[0x1E], chip.regs[0x26]) == (0x72, 0x74, 0x04),
          [hex(chip.regs[r]) for r in (0x1D, 0x1E, 0x26)])
    check("17 dBm on the PA_BOOST pin is PaConfig 0x8F", chip.regs[0x09] == 0x8F, hex(chip.regs[0x09]))
    check("LoRa mode bit is set", chip.regs[0x01] & 0x80 == 0x80)
    check("chip select was left high (idle)", radio.cs.level == 1)

    try:
        make_radio(FakeSX1276(version=0x00)).begin()
        check("a silent radio (version 0x00) raises a clear error", False)
    except OSError as err:
        check("a silent radio (version 0x00) raises a clear error", "wiring" in str(err), err)

    # two radios, one sends and one listens
    del AIR[:]
    tx, rx = make_radio(FakeSX1276()), make_radio(FakeSX1276())
    tx.begin()
    rx.begin()
    message = b'{"v":1,"id":"FOB-001","type":"SILENT","ctr":7}'
    check("send reports success", tx.send(message) is True)
    got = rx.receive(timeout_ms=1000)
    check("the other radio receives exactly the same bytes", got is not None and got[0] == message, got)
    check("RSSI and SNR are converted (-57 dBm, +5.0 dB)", got and got[1] == -57 and got[2] == 5.0, got)
    check("nothing arrives, receive gives None after the timeout", rx.receive(timeout_ms=100) is None)
    big = bytes(range(256)) * 1
    try:
        tx.send(big)
        check("a 256-byte packet is refused", False)
    except ValueError:
        check("a 256-byte packet is refused", True)
    full = bytes([65 + i % 26 for i in range(255)])
    tx.send(full)
    check("a 255-byte packet goes through whole", rx.receive(timeout_ms=1000)[0] == full)
    # a corrupted packet is skipped
    corrupted = FakeSX1276()
    r3 = make_radio(corrupted)
    r3.begin()
    AIR.append(b"bad")
    original = corrupted.write_readinto

    def with_crc_error(out, back):
        original(out, back)
        if (out[0] & 0x7F) == 0x12 and not (out[0] & 0x80) and back[1] & 0x40 and not hasattr(corrupted, "done"):
            back[1] |= 0x20
            corrupted.done = True
    corrupted.write_readinto = with_crc_error
    check("a packet with a CRC error is skipped", r3.receive(timeout_ms=100) is None)


def main():
    test_battery()
    test_pressure()
    test_gps()
    test_lora()
    print("\n{} passed, {} failed".format(passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
