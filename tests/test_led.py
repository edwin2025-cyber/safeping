"""Laptop test of the Fob's LED colors (docs/led-patterns.md), on the real main.py.

Each color means one kind of thing:
  red     MEDICAL only           yellow  SUSPICIOUS only
  green   good news              orange  a problem
  blue    the Fob busy with itself (starting up, joining WiFi)
  white   STATUS only (the dim sending light)
SILENT never shows anything. Every LED call in each case is recorded, then checked.

  python tests/test_led.py"""
import contextlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard     # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


def hue(rgb, main):
    """The base color of a (maybe dimmed) color tuple, as a name."""
    if rgb == main.OFF:
        return "off"
    top = max(rgb)
    norm = tuple(round(c * 255 / top) for c in rgb)
    for name in ("RED", "YELLOW", "GREEN", "ORANGE", "BLUE", "WHITE"):
        ref = getattr(main, name)
        if all(abs(a - b) <= 12 for a, b in zip(norm, ref)):
            return name.lower()
    return str(rgb)


class Recorder:
    def __init__(self, fob, main):
        self.calls = []
        self.main = main
        real = fob.led.show

        def show(color, on_ms=0, off_ms=0, duration_ms=0):
            self.calls.append((hue(color, main), on_ms, off_ms, duration_ms, color))
            return real(color, on_ms, off_ms, duration_ms)
        fob.led.show = show

    def take(self):
        out, self.calls = self.calls, []
        return out


def setup():
    main = fakeboard.load_fob(workdir=tempfile.mkdtemp())
    fob = main.Fob()
    rec = Recorder(fob, main)
    return main, fob, rec


ALLOWED = {               # color -> the one kind of meaning it may have
    "red": "medical", "yellow": "suspicious", "green": "good news", "orange": "problem",
    "blue": "busy", "white": "status",
}


def test_colors():
    main, fob, rec = setup()
    seen = {}                                     # color -> set of meanings used

    def note(meaning, calls):
        for c in calls:
            seen.setdefault(c[0], set()).add(meaning)

    # startup: blue, blue blink while WiFi joins, then green (passed) or orange (failed)
    main.wifi_join = lambda *a, **k: (True, "-", None)
    main.ntp_sync = lambda: True
    main.dns_lookup = lambda: ("10.0.0.1", 8883)
    fob.deliver = lambda *a, **k: (True, "confirmed", "-")
    fob.self_check = lambda gps_on, t0, wifi: {k: "ok" for k in ("key", "counter", "lora", "gps", "battery", "pressure", "wifi")}
    quiet(fob.boot)
    calls = rec.take()
    check("startup: steady blue first", calls[0][:2] == ("blue", 0), str(calls[:1]))
    check("startup: blue blink 300/300 while joining WiFi", calls[1][:3] == ("blue", 300, 300), str(calls[1:2]))
    check("startup: self-check passed is green 1 s", calls[2][0] == "green" and calls[2][3] == 1000, str(calls[2:3]))
    check("startup: no other colors", len(calls) == 3, str(calls))
    note("busy", calls[:2])
    note("good news", calls[2:])

    main2, fob2, rec2 = setup()
    main2.wifi_join = lambda *a, **k: (True, "-", None)
    main2.ntp_sync = lambda: True
    main2.dns_lookup = lambda: ("10.0.0.1", 8883)
    fob2.deliver = lambda *a, **k: (True, "confirmed", "-")
    quiet(fob2.boot)                              # bare fake board: LoRa, GPS, battery, pressure fail
    calls = rec2.take()
    check("startup: self-check failed is steady orange 3 s (no red)",
          calls[-1][0] == "orange" and calls[-1][3] == 3000 and "red" not in [c[0] for c in calls], str(calls))
    note("problem", calls[-1:])

    # cancel windows
    fob.start_pending("SUSPICIOUS", 0)
    c = rec.take()
    check("SUSPICIOUS cancel window: yellow blink 500/500", c[-1][:3] == ("yellow", 500, 500), str(c))
    note("suspicious", c)
    fob.start_pending("MEDICAL", 0)
    fob.motor.stop()
    c = rec.take()
    check("MEDICAL cancel window: red blink 150/150", c[-1][:3] == ("red", 150, 150), str(c))
    note("medical", c)
    quiet(fob.cancel_pending)
    c = rec.take()
    check("cancelled: green fast blink", c[-1][:4] == ("green", 150, 150, 600), str(c))
    note("good news", c)

    # sending lights
    for kind, want, meaning in (("STATUS", "white", "status"), ("SUSPICIOUS", "yellow", "suspicious"),
                                ("MEDICAL", "red", "medical")):
        fob.show_sending(kind)
        c = rec.take()
        check("{} sending: dim {}".format(kind, want), c[-1][0] == want and max(c[-1][4]) < 60, str(c))
        note(meaning, c)
    fob.show_sending("SILENT")
    check("SILENT sending: nothing", rec.take() == [])

    # results
    for kind in ("STATUS", "SUSPICIOUS", "MEDICAL"):
        quiet(fob.show_result, kind, True)
        c = rec.take()
        check("{} confirmed: green".format(kind), [x[0] for x in c] == ["green"], str(c))
        note("good news", c)
        quiet(fob.show_result, kind, False)
        c = rec.take()
        check("{} not confirmed: orange".format(kind), [x[0] for x in c] == ["orange"], str(c))
        note("problem", c)
    for ok in (True, False):
        quiet(fob.show_result, "SILENT", ok)
        check("SILENT {}: no light".format("confirmed" if ok else "not confirmed"), rec.take() == [])

    # help is coming: the slow blink is kept
    class Help:
        received = [(5, "MEDICAL", 1000)]

        def step(self, now, can_send=True):
            pass

        def active(self):
            return False
    fob.help = Help()
    fob.state = main.IDLE
    fob.motor.stop()
    quiet(fob.help_step, 0)
    c = rec.take()
    check("help is coming: green slow blink 400/400 for 2 s", c[-1][:4] == ("green", 400, 400, 2000), str(c))
    note("good news", c)
    Help.received = [(6, "SILENT", 1000)]
    fob.motor.stop()
    quiet(fob.help_step, 0)
    check("help for SILENT: no light", rec.take() == [])

    # the rule: each color has one kind of meaning, and only the allowed one
    for color, meanings in sorted(seen.items()):
        check("{} means one kind of thing ({})".format(color, ", ".join(sorted(meanings))),
              meanings == {ALLOWED.get(color)}, str(meanings))
    check("all six colors were seen", set(seen) == set(ALLOWED), str(sorted(seen)))
    check("orange no longer looks like yellow (green part under half of yellow's)",
          main.ORANGE[1] * 2 < main.YELLOW[1], str(main.ORANGE))


def main():
    test_colors()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
