"""Laptop test: the Fob's counter survives a crash in its own write, and never reuses
a number.

Why: counter.txt used to be written in place. A crash in that write (the cache error of
2026-11-13 happens inside flash writes) could leave it empty, and with no clock the
counter restarted from 0: the server would reject every message as a replay.
Now (counterfile.py): write counter.txt.tmp, then rename it over counter.txt, keep a
copy in RTC memory first, and jump 8 ahead on every boot (message-format.md).

  1. counterfile.py: read the higher of the two files, damaged and missing files
  2. a crash at every point of the write (before the .tmp, half-way through the .tmp,
     after the .tmp, during the rename): counter.txt is always the old or the new
     value, and after the reboot the next counter is higher than any number used
  3. the real main.py: boot jump by 8, the jump uses the RTC copy, a signed press and
     the queue, a damaged file with no clock uses the RTC copy

  python tests/test_counter.py"""
import contextlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakeboard                       # noqa: E402  (puts firmware/lib on the path)
import counterfile                     # noqa: E402
import pressrec                        # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


class Crash(BaseException):
    """Like a Guru Meditation: nothing catches it."""


class FakeFiles:
    """A file system where a write can crash at a chosen point."""

    def __init__(self):
        self.data = {}
        self.crash_at = None        # "write_start", "write_half", "after_write", "rename"

    def read(self, name):
        return self.data.get(name)

    def write(self, name, text):
        if self.crash_at == "write_start":
            self.data[name] = ""                     # created, nothing written yet
            raise Crash()
        if self.crash_at == "write_half":
            self.data[name] = text[:len(text) // 2]  # cut short
            raise Crash()
        self.data[name] = text
        if self.crash_at == "after_write":
            raise Crash()

    def replace(self, src, dst):
        if self.crash_at == "rename":
            raise Crash()                            # littlefs: dst is still the old file
        self.data[dst] = self.data.pop(src)


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


# ---------- 1. counterfile.py ----------
def test_file():
    f = FakeFiles()
    c = counterfile.CounterFile("counter.txt", f)
    check("no file: new", c.read() == (None, "new"))
    c.write(41)
    check("write then read", c.read() == (41, "ok") and "counter.txt.tmp" not in f.data, str(f.data))
    f.data["counter.txt.tmp"] = "57"
    check("a whole .tmp left by a crash before the rename wins when higher", c.read() == (57, "ok"))
    f.data["counter.txt.tmp"] = "4"
    check("a cut-short .tmp (lower) never wins", c.read() == (41, "ok"))
    f.data["counter.txt"] = ""
    f.data["counter.txt.tmp"] = ""
    check("both empty: damaged", c.read() == (None, "damaged"))
    check("jump_base: highest known, None skipped", counterfile.jump_base(5, [None, 9, 3]) == 9
          and counterfile.jump_base(None, [None]) == -1)


# ---------- 2. a crash at every point of the write ----------
def test_crash_points():
    for point in ("write_start", "write_half", "after_write", "rename"):
        f = FakeFiles()
        c = counterfile.CounterFile("counter.txt", f)
        rec = pressrec.PressRecord(_Mem())
        c.write(1234)                                # the old value
        rec.counter(1234)
        f.crash_at = point
        new = 1235
        rec.counter(new)                             # main._counter_save: RTC first
        try:
            c.write(new)
            crashed = False
        except Crash:
            crashed = True
        f.crash_at = None
        main_file = f.data.get("counter.txt")
        value, state = c.read()
        # the reboot: the same rule as main.jump_counter
        rec2 = pressrec.PressRecord(rec.store)
        rec2.load()
        base = counterfile.jump_base(value, [rec2.ctr])
        nxt = base + 8 + 1
        check("crash at {}: counter.txt is the old or the new value".format(point),
              crashed and main_file in ("1234", "1235"), repr(main_file))
        check("crash at {}: the next counter after the reboot is above every number used".format(point),
              state == "ok" and nxt > new, "read {} next {}".format(value, nxt))


class _Mem:
    def __init__(self):
        self.data = b""

    def read(self):
        return self.data

    def write(self, data):
        self.data = bytes(data)


# ---------- 3. the real main.py ----------
def test_main():
    fakeboard.rtc_memory[0] = b""
    workdir = tempfile.mkdtemp()
    main = fakeboard.load_fob(workdir=workdir)
    fob = main.Fob()
    fob.help = None
    check("first boot: jump from -1 to 7", quiet(main.jump_counter, [None])[0] == (-1, 7))
    check("next counter after the jump is 8", main.next_counter() == 8)
    with open(os.path.join(workdir, "counter.txt")) as f:
        check("counter.txt holds 8, no .tmp left", f.read() == "8"
              and not os.path.exists(os.path.join(workdir, "counter.txt.tmp")))
    check("the RTC copy follows every counter", pressrec.parse(fakeboard.rtc_memory[0])["ctr"] == 8)

    # a reboot: the jump takes the highest of the file, the RTC copy and the queue
    fob.queue.add(30, "MEDICAL", '{"ctr": 30}', "s", None)
    fob.queue.save()
    main = fakeboard.load_fob(workdir=workdir)
    fob = main.Fob()
    fob.help = None
    quiet(fob.resume_queue)
    fob.rec_found = fob.rec.load()
    _, log = quiet(fob.boot_counter_jump)
    check("reboot: jump starts from the highest known (the queued 30)", "COUNTER_JUMP from=30 to=38" in log, log)

    # the file lost (damaged), no clock: the RTC copy keeps the counter going up
    with open(os.path.join(workdir, "counter.txt"), "w") as f:
        f.write("")
    main = fakeboard.load_fob(workdir=workdir)
    main.unix_time = lambda: None
    fob = main.Fob()
    fob.help = None
    fob.rec_found = fob.rec.load()
    _, log = quiet(fob.boot_counter_jump)
    check("damaged file, no clock: jump from the RTC copy (38), not from 0",
          "COUNTER_JUMP from=38 to=46" in log, log)
    check("the file itself was damaged (the self-check reports it)",
          main.selfcheck.counter_state("") == "fail")

    # a signed press in RTC memory higher than everything else
    rec = pressrec.PressRecord(pressrec.RtcStore(main.machine))
    rec.load()
    rec.signed("SILENT", 60, '{"ctr": 60}', "s", None)
    main = fakeboard.load_fob(workdir=workdir)
    fob = main.Fob()
    fob.help = None
    fob.rec_found = fob.rec.load()
    _, log = quiet(fob.boot_counter_jump)
    check("a signed press's counter is part of the jump (60 -> 68)", "COUNTER_JUMP from=60 to=68" in log, log)


def main():
    test_file()
    test_crash_points()
    test_main()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
