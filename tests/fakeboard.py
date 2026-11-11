"""Stand-ins for the board's modules (machine, network, neopixel, ntptime) so the real
firmware/fob/main.py can be imported and driven on the laptop. No pins, no radio.

  import fakeboard
  main = fakeboard.load_fob()          # main.py with a fake clock and a fake button
  fakeboard.clock[0] += 500            # move time on
  fakeboard.button.level = 0           # press (pull-up: 0 = pressed)

Used by tests/test_retry_queue.py and tests/test_help.py.
"""
import importlib
import os
import sys
import tempfile
import time as _time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, "..", "firmware")
for sub in ("lib", "fob"):
    path = os.path.join(FIRMWARE, sub)
    if path not in sys.path:
        sys.path.insert(0, path)

clock = [100000]                 # fake ticks_ms
reset_cause = [1]                # what machine.reset_cause() returns (1 power on, 2 crash)


class FakePin:
    IN, OUT, PULL_UP = 1, 2, 3
    IRQ_FALLING, IRQ_RISING = 1, 2

    def __init__(self, num=None, mode=None, pull=None, value=None):
        self.num = num
        self.level = 1 if value is None else value
        self.handler = None

    def value(self, v=None):
        if v is None:
            return self.level
        self.level = v

    def irq(self, handler=None, trigger=None, hard=False):
        self.handler = handler


class Button(FakePin):
    """The Fob's button pin. press() and release() also fire the interrupt."""

    def set(self, level):
        self.level = level
        if self.handler:
            self.handler(self)

    def press(self):
        self.set(0)

    def release(self):
        self.set(1)


button = Button()


def _pin(num=None, *args, **kw):
    if num == 1:                 # BUTTON_PIN on the bench Fob
        return button
    return FakePin(num, *args, **kw)


_pin.IN, _pin.OUT, _pin.PULL_UP = FakePin.IN, FakePin.OUT, FakePin.PULL_UP
_pin.IRQ_FALLING, _pin.IRQ_RISING = FakePin.IRQ_FALLING, FakePin.IRQ_RISING


class FakePWM:
    def __init__(self, pin, freq=None, duty_u16=0):
        self.duty = duty_u16

    def duty_u16(self, v):
        self.duty = v


class FakeNeoPixel:
    def __init__(self, pin, n):
        self.px = [(0, 0, 0)] * n

    def __setitem__(self, i, v):
        self.px[i] = v

    def __getitem__(self, i):
        return self.px[i]

    def write(self):
        pass


def _install():
    machine = types.ModuleType("machine")
    machine.Pin = _pin
    machine.PWM = FakePWM
    machine.disable_irq = lambda: None
    machine.enable_irq = lambda state: None
    machine.reset_cause = lambda: reset_cause[0]
    machine.PWRON_RESET, machine.HARD_RESET, machine.WDT_RESET = 1, 2, 3

    class WDT:
        def __init__(self, timeout=0):
            pass

        def feed(self):
            pass
    machine.WDT = WDT

    class SPI:
        def __init__(self, *a, **k):
            pass
    machine.SPI = SPI

    class I2C:
        def __init__(self, *a, **k):
            raise OSError("no I2C on the laptop")
    machine.I2C = I2C
    sys.modules["machine"] = machine

    network = types.ModuleType("network")
    network.STA_IF = 0
    network.STAT_CONNECTING = 1001

    class WLAN:
        def __init__(self, i):
            self._active = False

        def active(self, v=None):
            if v is None:
                return self._active
            self._active = v

        def isconnected(self):
            return False

        def status(self):
            return 0

        def connect(self, *a):
            pass

        def disconnect(self):
            pass

        def config(self, **k):
            pass
    network.WLAN = WLAN
    sys.modules["network"] = network

    neo = types.ModuleType("neopixel")
    neo.NeoPixel = FakeNeoPixel
    sys.modules["neopixel"] = neo


def _patch_time():
    """MicroPython's time functions, on the fake clock."""
    t = _time
    t.ticks_ms = lambda: clock[0]
    t.ticks_diff = lambda a, b: a - b
    t.ticks_add = lambda a, b: a + b

    def sleep_ms(ms):
        clock[0] += ms
    t.sleep_ms = sleep_ms


def load_fob(config_values=None, workdir=None):
    """Import firmware/fob/main.py fresh, with a fake config. Runs in its own folder so
    counter.txt and queue.json never touch the real ones."""
    _install()
    _patch_time()
    os.chdir(workdir or tempfile.mkdtemp())
    cfg = types.ModuleType("config")
    values = {"DEVICE_ID": "FOB-T", "SECRET_KEY": "f" * 32,          # test key, not a real one
              "WIFI_SSID": "test-net", "BUTTON_PIN": 1, "LED_TYPE": "neopixel", "NEOPIXEL_PIN": 27,
              "MOTOR_PIN": 3, "HOLD_MS": 2000, "CANCEL_MS": 2000}
    values.update(config_values or {})
    for k, v in values.items():
        setattr(cfg, k, v)
    sys.modules["config"] = cfg
    for name in ("main", "presslog", "retryq", "helplisten", "selfcheck", "sendpath"):
        sys.modules.pop(name, None)
    button.level = 1
    button.handler = None
    return importlib.import_module("main")
