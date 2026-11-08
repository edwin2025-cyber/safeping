"""Desktop smoke test for the bring-up scripts. No hardware needed.

  python test_scripts.py

It runs each script in this folder against fake parts (a fake I2C bus with a battery
gauge, a GPS and a pressure sensor on it, a fake LoRa chip, a fake button) and checks that
the script runs to the end and prints what its header says it will. This catches typos
and wrong names now, so that on the day the parts arrive, any problem is the wiring.

This file is for your laptop. Do not copy it to the board."""
import io
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
COMMON = os.path.join(HERE, "..", "common")
sys.path.insert(0, COMMON)

import test_drivers as drv   # noqa: E402  (fake chips and sample data live there)

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  ok    ", name)
    else:
        failed += 1
        print("  FAIL  ", name, detail)


class StopRun(Exception):
    """Raised by the fake clock to end a script that would run forever."""


# ------------------------------------------------------------------ the fake world
class World:
    def __init__(self):
        self.reset()

    def reset(self, stop_after_ms=20000):
        self.clock = 0
        self.stop_after = stop_after_ms
        self.pins = {}                  # gpio number -> FakePin (last one created)
        self.i2c_working = {(23, 24)}   # which (sda, scl) pairs carry the bus
        self.i2c_devices = {}
        self.button_down = lambda ms: False
        self.neo = []
        self.lora_chip = None


W = World()


def advance(ms):
    W.clock += ms
    if W.clock > W.stop_after:
        raise StopRun()


class FakePin:
    IN, OUT, PULL_UP = 0, 1, 2

    def __init__(self, number, mode=None, pull=None, value=None):
        self.number, self.mode, self.level = number, mode, value
        self.history = [] if value is None else [value]
        W.pins[number] = self

    def value(self, v=None):
        if v is None:
            if self.mode == FakePin.IN and self.number == W_BUTTON[0]:
                return 0 if W.button_down(W.clock) else 1
            return self.level
        self.level = v
        self.history.append(v)


W_BUTTON = [1]          # which gpio the test treats as the button


class FakeI2C:
    def __init__(self, id, sda=None, scl=None, freq=400000):
        self.pair = (sda.number, scl.number)

    def scan(self):
        return sorted(W.i2c_devices) if self.pair in W.i2c_working else []

    def readfrom_mem(self, addr, reg, n):
        return W.i2c_devices[addr].readfrom_mem(addr, reg, n)

    def writeto_mem(self, addr, reg, data):
        W.i2c_devices[addr].writeto_mem(addr, reg, data)


class FakeSPI:
    def __new__(cls, *args, **kwargs):
        return W.lora_chip


class FakeNeoPixel:
    def __init__(self, pin, n):
        self.buf = [(0, 0, 0)] * n

    def __setitem__(self, i, rgb):
        self.buf[i] = rgb

    def write(self):
        W.neo.append((W.clock, tuple(self.buf[0])))


machine = types.ModuleType("machine")
machine.Pin = FakePin
machine.I2C = FakeI2C
machine.SoftI2C = FakeI2C
machine.SPI = FakeSPI
machine.SoftSPI = FakeSPI
sys.modules["machine"] = machine
neopixel = types.ModuleType("neopixel")
neopixel.NeoPixel = FakeNeoPixel
sys.modules["neopixel"] = neopixel

time.sleep = lambda s: advance(int(s * 1000))
time.sleep_ms = lambda ms: advance(ms)
time.ticks_ms = lambda: W.clock
time.ticks_diff = lambda a, b: a - b
time.ticks_add = lambda a, b: a + b
_real_time = time.time
time.time = lambda: W.clock / 1000.0


def make_devices():
    """A battery gauge, a GPS with a fix and a pressure sensor, all on one bus."""
    cal = [27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000]
    cal_bytes = b"".join(drv._le16(v) for v in cal)
    adc_p, adc_t = 415148, 519888
    data = bytes([(adc_p >> 12) & 0xFF, (adc_p >> 4) & 0xFF, (adc_p & 0xF) << 4,
                  (adc_t >> 12) & 0xFF, (adc_t >> 4) & 0xFF, (adc_t & 0xF) << 4])
    gps = drv.FakeGPS()
    gga = drv.nmea("GNGGA,092750.000,5321.6802,N,00630.3372,W,1,8,1.03,61.7,M,55.2,M,,")
    gps_feed = (gga + "\r\n").encode()

    class RepeatingGPS(drv.FakeGPS):
        def readfrom_mem(self, addr, reg, n):
            if reg == 0xFD and not self.stream:
                self.stream += gps_feed            # a new sentence arrives every second
            return super().readfrom_mem(addr, reg, n)

    return {
        0x36: drv.FakeI2C({0x02: b"\xC3\x00", 0x04: b"\x4B\x80", 0x08: b"\x00\x12"}),
        0x42: RepeatingGPS(),
        0x77: drv.FakeI2C({0xD0: b"\x60", 0x88: cal_bytes, 0xF3: b"\x00", 0xF7: data}),
    }


def run_script(name, stop_after_ms=20000, edits=()):
    """Run one bring-up script. Returns (printed text, error or None)."""
    W.stop_after = stop_after_ms
    W.clock = 0
    W.neo = []
    path = os.path.join(HERE, name)
    source = open(path, encoding="utf-8").read()
    for old, new in edits:
        assert old in source, "edit target missing: " + old
        source = source.replace(old, new)
    for module in ("hw", "pins", "max17048", "bme280", "gnss", "sx127x"):
        if module in sys.modules and module == "hw":
            del sys.modules["hw"]
    out = io.StringIO()
    real = sys.stdout
    sys.stdout = out
    error = None
    try:
        exec(compile(source, path, "exec"), {"__name__": "__main__", "__file__": path})
    except StopRun:
        pass
    except Exception as err:       # noqa: BLE001
        error = err
    finally:
        sys.stdout = real
    return out.getvalue(), error


def main():
    import pins

    print("\n00_pin_walk.py")
    W.reset()
    text, err = run_script("00_pin_walk.py", stop_after_ms=60000)
    check("runs to the end with no error", err is None and "Done. Every pin is LOW again." in text, err)
    check("announces every free GPIO in turn", "GPIO 4 is HIGH now" in text and "GPIO 0 is HIGH now" in text, text[:300])
    check("never drives a reserved pin", not any("GPIO {} is HIGH".format(g) in text for g in pins.RESERVED))
    check("each pin is raised and then lowered",
          all(W.pins[g].history[-2:] == [1, 0] for g in pins.CANDIDATE_FREE_PINS if g not in pins.RESERVED))

    print("\n01_i2c_scan.py")
    W.reset()
    W.i2c_devices = make_devices()
    text, err = run_script("01_i2c_scan.py")
    check("runs with no error", err is None, err)
    check("finds all three parts with names",
          "0x36  battery gauge" in text and "0x42  GPS" in text and "0x77  pressure sensor" in text, text)
    check("says the bus matches pins.py", "SDA = GPIO 23, SCL = GPIO 24" in text and "Nothing to change" in text, text)
    W.reset()
    W.i2c_devices = make_devices()
    W.i2c_working = {(7, 6)}
    text, err = run_script("01_i2c_scan.py")
    check("finds the alternate pair and says to change pins.py",
          "SDA = GPIO 7, SCL = GPIO 6" in text and "Change I2C_SDA and I2C_SCL" in text, text)
    W.reset()
    W.i2c_devices = make_devices()
    W.i2c_working = set()
    text, err = run_script("01_i2c_scan.py")
    check("no bus gives a clear message", "no battery gauge found" in text, text)

    print("\n02_battery.py")
    W.reset()
    W.i2c_devices = make_devices()
    text, err = run_script("02_battery.py", stop_after_ms=3500)
    check("prints version, voltage and percent", "version: 0x0012" in text and "battery 3900 mV  75 %" in text, text)

    print("\n03_bme280.py")
    W.reset()
    W.i2c_devices = make_devices()
    text, err = run_script("03_bme280.py", stop_after_ms=3500)
    check("reads the sensor and shows pressure, temperature and change",
          "chip id: 0x60" in text and "pressure 100653 Pa" in text and "temp 2508" in text and "change +0 Pa" in text, text)
    W.reset()
    W.i2c_devices = {0x36: make_devices()[0x36]}
    text, err = run_script("03_bme280.py")
    check("a missing sensor gives a clear error", isinstance(err, OSError) and "01_i2c_scan.py" in str(err), (err, text))

    print("\n04_gps.py")
    W.reset()
    W.i2c_devices = make_devices()
    text, err = run_script("04_gps.py", stop_after_ms=6000)
    check("shows sentences arriving and a fix in microdegrees",
          "FIX  lat 53361337 lon -6505620" in text and "(53.361337, -6.505620)" in text, text[-400:])
    W.reset()
    W.i2c_devices = {0x36: make_devices()[0x36]}
    text, err = run_script("04_gps.py")
    check("a missing GPS gives a clear error", isinstance(err, OSError) and "0x42" in str(err), (err, text))

    print("\n05_button_led_motor.py")
    W.reset()
    W_BUTTON[0] = pins.BUTTON
    # a 300 ms tap at 6.0 s, then a 5.2 s hold at 8.0 s
    W.button_down = lambda ms: 6000 <= ms < 6300 or 8000 <= ms < 13200
    text, err = run_script("05_button_led_motor.py", stop_after_ms=15000)
    check("cycles the four colors", [c for _, c in W.neo[:4]] == [(63, 0, 0), (0, 63, 0), (0, 0, 63), (63, 63, 63)],
          [c for _, c in W.neo[:8]])
    check("reports presses and releases", "PRESSED" in text and "RELEASED after" in text, text)
    check("flags the 5 second hold as SILENT HOLD", "SILENT HOLD" in text, text)
    check("the motor was on during a press and is off at the end",
          W.pins[pins.MOTOR].history[0] == 0 and 1 in W.pins[pins.MOTOR].history and W.pins[pins.MOTOR].level == 0,
          W.pins[pins.MOTOR].history)
    check("the pixel is dark at the end", W.neo[-1][1] == (0, 0, 0))

    print("\n06_lora.py")
    for role in ("check", "tx", "rx"):
        W.reset()
        del drv.AIR[:]
        W.lora_chip = drv.FakeSX1276()
        edits = [('ROLE = "check"', 'ROLE = "{}"'.format(role))]
        if role == "rx":
            drv.AIR.append(b"SafePing test 0")
        text, err = run_script("06_lora.py", stop_after_ms=9000, edits=edits)
        check("{}: finds the radio".format(role), "version register = 0x12 (good)" in text, (err, text))
        if role == "check":
            check("check: ends with the next-step message", "Check done" in text, text)
        if role == "tx":
            check("tx: sends numbered messages", "sent 'SafePing test 0'" in text and "sent 'SafePing test 1'" in text, text)
        if role == "rx":
            check("rx: prints the message and the signal strength",
                  "received 'SafePing test 0'  signal -57 dBm  snr 5.0" in text, text)
    W.reset()
    W.lora_chip = drv.FakeSX1276(version=0x00)
    text, err = run_script("06_lora.py")
    check("no radio gives the wiring error", isinstance(err, OSError) and "Check wiring" in str(err), (err, text))

    print("\n{} passed, {} failed".format(passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
