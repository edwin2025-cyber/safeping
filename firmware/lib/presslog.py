"""Button presses that are never lost, even while the Fob is busy.

Why: the Fob read the button only in its main loop, every 10 ms. Anything that blocks
the loop (an NTP or DNS call in the idle upkeep, a TLS handshake in a retry) stopped
the reading. A tap that started and ended inside the block was lost, and a hold looked
shorter than it was. That is the "upkeep can block a tap for about 2 s" problem:
ntptime.settime() does a DNS lookup plus a 1 s socket wait.

How: a hardware interrupt writes every edge of the button pin (time and level) into a
small ring buffer (EdgeLog). The main loop reads the buffer and runs the edges through
the same debounce rule as before (Debouncer), so it gets each press and release with
the time it really happened, even if it reads them seconds later.

Without interrupts (or in Wokwi), EdgeLog stays empty and the Debouncer falls back to
reading the pin each loop, exactly like the old code.

Pure logic, no pins: tests/test_presslog.py runs it on the laptop.
"""

try:
    from time import ticks_ms, ticks_diff               # MicroPython
except ImportError:                                      # the laptop
    import time as _time

    def ticks_ms():
        return int(_time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

try:
    from array import array
except ImportError:                                      # pragma: no cover
    array = None


class EdgeLog:
    """Ring buffer of pin edges, filled by irq(). irq() allocates no memory, so it is
    safe as a hard interrupt handler. take() returns the new edges, oldest first."""

    def __init__(self, size=128, clock=None, irq_off=None, irq_on=None):
        self.size = size
        self.t = array("i", [0] * size)
        self.v = array("b", [0] * size)
        self.n = 0                 # edges ever written
        self.read = 0              # edges ever taken
        self.lost = 0              # edges dropped because the buffer was full
        self.clock = clock or ticks_ms
        self.irq_off = irq_off     # machine.disable_irq on the board
        self.irq_on = irq_on       # machine.enable_irq

    def irq(self, pin):
        i = self.n % self.size
        self.t[i] = self.clock()
        self.v[i] = pin.value()
        self.n += 1

    def add(self, t, level):
        """For tests: one edge at time t."""
        i = self.n % self.size
        self.t[i] = t
        self.v[i] = level
        self.n += 1

    def pending(self):
        return self.n != self.read

    def take(self):
        state = self.irq_off() if self.irq_off else None
        try:
            n = self.n
            start = self.read
            if n - start > self.size:              # overran: keep the newest edges
                self.lost += n - start - self.size
                start = n - self.size
            out = [(self.t[i % self.size], self.v[i % self.size]) for i in range(start, n)]
            self.read = n
        finally:
            if self.irq_on:
                self.irq_on(state)
        return out


class Debouncer:
    """Turns edges (and the pin level now) into clean presses and releases.

    A level counts once it has held for debounce_ms with no further edge. The time of a
    press or release is the time of the last edge before it settled.
    feed() returns [(time, pressed)], oldest first. pressed is True for a press."""

    def __init__(self, debounce_ms, diff=None):
        self.debounce_ms = debounce_ms
        self.diff = diff or ticks_diff
        self.stable = False          # True while the button is held (after debounce)
        self.cand = None             # (time, pressed) waiting to be confirmed
        self.cand_from_pin = False   # the candidate came from reading the pin, not an edge

    def busy(self):
        """True while a change is waiting to be confirmed."""
        return self.cand is not None

    def _confirm(self, out):
        t, pressed = self.cand
        self.cand = None
        if pressed != self.stable:
            self.stable = pressed
            out.append((t, pressed))

    def feed(self, edges, now, pin_pressed):
        out = []
        for t, level in edges:
            pressed = level == 0                  # pull-up: pressed reads 0
            if self.cand is not None and self.diff(t, self.cand[0]) >= self.debounce_ms:
                self._confirm(out)
            self.cand = (t, pressed)
            self.cand_from_pin = False
        if edges:
            return out + self._settle(now, pin_pressed)
        # No edges: read the pin like the old loop did (no interrupts, or edges missed).
        if self.cand is not None and self.cand_from_pin and self.cand[1] != pin_pressed:
            self.cand = None                      # it bounced back: no change
        if self.cand is None and pin_pressed != self.stable:
            self.cand = (now, pin_pressed)
            self.cand_from_pin = True
        return out + self._settle(now, pin_pressed)

    def _settle(self, now, pin_pressed):
        out = []
        if self.cand is not None and self.diff(now, self.cand[0]) >= self.debounce_ms:
            self._confirm(out)
        return out
