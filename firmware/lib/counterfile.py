"""The Fob's message counter in flash, written so a crash cannot damage it.

Why: on 2026-11-13 the Fob crashed inside a flash write (cache error). counter.txt was
written in place, so a crash in that write could leave it empty or cut short. With no
clock, an empty file made the counter start again from 0, and the server would reject
every message as a replay.

How: the new value is written to counter.txt.tmp in full, then renamed over
counter.txt (littlefs replaces the file in one step). So counter.txt is always the old
or the new value. read() takes the higher of the two files that read as a whole
number, so a crash between the write and the rename loses nothing.

On every boot main.py also jumps the counter ahead (jump()), from the highest number
it knows about, so a lost write can never make it reuse a number
(message-format.md, "The Fob's counter").

Pure logic with injectable files: tests/test_counter.py runs it.
"""
try:
    import os
except ImportError:                                       # pragma: no cover
    os = None


class CounterFile:
    def __init__(self, path="counter.txt", files=None):
        self.path = path
        self.files = files or _Files()

    def read(self):
        """(value, state). value is the highest whole number in counter.txt and
        counter.txt.tmp, or None. state is "ok", "new" (no file at all) or "damaged"
        (a file is there, but neither reads as a whole number)."""
        best, found = None, False
        for name in (self.path, self.path + ".tmp"):
            text = self.files.read(name)
            if text is None:
                continue
            found = True
            try:
                n = int(text.strip())
            except ValueError:
                continue
            if n >= 0 and (best is None or n > best):
                best = n
        if best is not None:
            return best, "ok"
        return None, ("damaged" if found else "new")

    def write(self, n):
        tmp = self.path + ".tmp"
        self.files.write(tmp, str(n))
        self.files.replace(tmp, self.path)


def jump_base(file_value, others):
    """The highest of the file's value and every other counter we know (None is skipped),
    or -1 when there is none."""
    known = [v for v in [file_value] + list(others) if isinstance(v, int) and v >= 0]
    return max(known) if known else -1


class _Files:
    """The board's (or laptop's) files. Tests swap this for a fake."""

    def read(self, name):
        try:
            with open(name) as f:
                return f.read()
        except OSError:
            return None

    def write(self, name, text):
        with open(name, "w") as f:
            f.write(text)

    def replace(self, src, dst):
        try:
            os.rename(src, dst)              # littlefs replaces dst in one step
        except OSError:
            try:
                os.remove(dst)               # file systems that refuse to rename over a file
            except OSError:
                pass
            os.rename(src, dst)
