"""Average pressure over a window, to one decimal. Shared by the Reference board (a 30 s
window, a reading every 2 s) and the Fob's survey mode (15 readings in 3 s).

Readings come from bme280.read_q8(): pascals times 256, so the fraction is kept.
The result uses the message format's whole numbers (message-format.md):
  pd   average pressure in tenths of a pascal (988124 = 98812.4 Pa)
  p    the same, rounded to whole pascals
  t    average temperature, hundredths of a degree C
  n    readings in the average

Pure code with no pins, so tests/test_ref.py and tests/test_survey.py run it.
"""


class Window:
    def __init__(self):
        self.reset()

    def reset(self):
        self.p_sum = 0
        self.n = 0
        self.t_sum = 0
        self.t_n = 0
        self.first_ms = None
        self.last_ms = None
        self.failed = 0             # readings that gave no pressure

    def add(self, p_q8, t=None, ms=None):
        """One reading. p_q8 None (a failed reading) is counted in failed, not averaged."""
        if p_q8 is None:
            self.failed += 1
            return
        self.p_sum += p_q8
        self.n += 1
        if t is not None:
            self.t_sum += t
            self.t_n += 1
        if ms is not None:
            if self.first_ms is None:
                self.first_ms = ms
            self.last_ms = ms

    def tenths(self):
        """Average in tenths of a pascal, rounded, or None with no reading."""
        if not self.n:
            return None
        return (self.p_sum * 10 + self.n * 128) // (self.n * 256)

    def result(self):
        """{"pd", "p", "t", "n"} for the message, or None with no reading. t may be None."""
        pd = self.tenths()
        if pd is None:
            return None
        t = None
        if self.t_n:
            t = (self.t_sum + self.t_n // 2) // self.t_n
        return {"pd": pd, "p": (pd + 5) // 10, "t": t, "n": self.n}

    def mid_ts(self, now_unix, now_ms, diff):
        """Unix seconds of the middle of the window, or None without a clock.
        diff is time.ticks_diff (the tick counter wraps on a board that runs for days)."""
        if now_unix is None or self.first_ms is None:
            return None
        span = diff(self.last_ms, self.first_ms)
        age_ms = diff(now_ms, self.first_ms) - span // 2
        return now_unix - (age_ms + 500) // 1000


def text(pd):
    """Tenths of a pascal as "98812.4". "-" for None."""
    if pd is None:
        return "-"
    return "{}.{}".format(pd // 10, pd % 10)
