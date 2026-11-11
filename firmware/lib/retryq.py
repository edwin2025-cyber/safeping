"""The Fob's retry queue (message-format.md, "Retry queue").

An alert that ends NOT confirmed on both paths is kept here and sent again, as the
exact same signed message, every every_ms for for_ms. Then the Fob gives up.

  add()        queue one alert (drops by type when full, see below)
  expired()    entries past for_ms: give up on them
  next_due()   the entry to try now, or None
  tried()      a try failed: next one in every_ms
  stopped()    a button press stopped the try: try again soon
  done()       it got through
  save() / load()   kept in flash (written to a .tmp file first, so a power cut in the
                    middle of a write cannot damage the queue)

Drop order when full: the oldest STATUS first, then the oldest SUSPICIOUS, then SILENT.
A MEDICAL is never dropped to make room for a lower type. All MEDICAL: the oldest is
dropped. In general: never drop a higher type for a lower one, so a new STATUS is not
queued when the queue is full of alerts.

Pure logic with injectable clock and files: tests/test_retry_queue.py runs it.
"""
import json

try:
    from time import ticks_ms, ticks_diff, ticks_add     # MicroPython
except ImportError:                                       # the laptop
    import time as _time

    def ticks_ms():
        return int(_time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

    def ticks_add(a, b):
        return a + b

try:
    import os
except ImportError:                                       # pragma: no cover
    os = None

RANK = {"STATUS": 0, "SUSPICIOUS": 1, "SILENT": 2, "MEDICAL": 3}
STOPPED_RETRY_MS = 5000      # after a button press stops a try, try again this soon


def line(tag, **fields):
    """One log line like 'RETRY_TRY ctr=5 kind=MEDICAL try=2'. Keys in a fixed order.
    try is passed as try_no, because try is a Python word."""
    order = ("ctr", "kind", "try_no", "age_s", "path", "result", "reason", "queue", "dropped")
    parts = [tag]
    for key in order:
        if key in fields:
            value = fields[key]
            name = "try" if key == "try_no" else key
            parts.append("{}={}".format(name, "-" if value is None or value == "" else value))
    return " ".join(parts)


class RetryQueue:
    def __init__(self, path="queue.json", max_n=5, every_ms=30000, for_ms=600000,
                 clock=None, diff=None, add=None, files=None):
        self.path = path
        self.max_n = max_n
        self.every_ms = every_ms
        self.for_ms = for_ms
        self.clock = clock or ticks_ms
        self.diff = diff or ticks_diff
        self.add_ms = add or ticks_add
        self.files = files or _Files()
        self.entries = []      # oldest first. Each: ctr, kind, payload, sig, wall, start, next, tries

    def __len__(self):
        return len(self.entries)

    def age_ms(self, entry, now=None):
        return self.diff(self.clock() if now is None else now, entry["start"])

    # ---------- adding ----------
    def add(self, ctr, kind, payload, sig, wall=None, now=None):
        """Queue one alert. Returns (queued, dropped). dropped is the entry thrown out to
        make room (or the new one, if it was not queued), else None."""
        now = self.clock() if now is None else now
        for e in self.entries:
            if e["ctr"] == ctr:
                return False, None                 # already waiting
        new = {"ctr": ctr, "kind": kind, "payload": payload, "sig": sig, "wall": wall,
               "start": now, "next": self.add_ms(now, self.every_ms), "tries": 0}
        dropped = None
        if len(self.entries) >= self.max_n:
            victim = self._victim(new)
            if victim is new:
                return False, new
            self.entries.remove(victim)
            dropped = victim
        self.entries.append(new)
        return True, dropped

    def _victim(self, new):
        """The oldest entry of the lowest type among the queue and the new one.
        The new one only loses when its type is lower than everything queued."""
        low = min(RANK.get(e["kind"], 0) for e in self.entries)
        if RANK.get(new["kind"], 0) < low:
            return new
        for e in self.entries:                     # oldest first
            if RANK.get(e["kind"], 0) == low:
                return e
        return new                                 # pragma: no cover

    # ---------- trying ----------
    def expired(self, now=None):
        """Remove and return the entries that have been waiting for_ms or more."""
        now = self.clock() if now is None else now
        old = [e for e in self.entries if self.age_ms(e, now) >= self.for_ms]
        for e in old:
            self.entries.remove(e)
        return old

    def next_due(self, now=None):
        """The entry to try now: the highest type first, then the oldest. None if none is due."""
        now = self.clock() if now is None else now
        due = [e for e in self.entries if self.diff(now, e["next"]) >= 0
               and self.age_ms(e, now) < self.for_ms]
        if not due:
            return None
        best = due[0]
        for e in due[1:]:
            if RANK.get(e["kind"], 0) > RANK.get(best["kind"], 0):
                best = e
        return best

    def tried(self, entry, now=None):
        now = self.clock() if now is None else now
        entry["tries"] += 1
        entry["next"] = self.add_ms(now, self.every_ms)

    def stopped(self, entry, now=None):
        """A button press stopped this try. It does not count as a try."""
        now = self.clock() if now is None else now
        entry["next"] = self.add_ms(now, min(self.every_ms, STOPPED_RETRY_MS))

    def done(self, entry):
        if entry in self.entries:
            self.entries.remove(entry)

    # ---------- flash ----------
    def save(self, now=None):
        """Write the queue to flash. The .tmp file is written in full first, then renamed
        over the real file, so the real file is always either the old or the new queue."""
        now = self.clock() if now is None else now
        data = {"v": 1, "entries": [
            {"ctr": e["ctr"], "kind": e["kind"], "payload": e["payload"], "sig": e["sig"],
             "wall": e["wall"], "age_ms": self.age_ms(e, now), "tries": e["tries"]}
            for e in self.entries]}
        tmp = self.path + ".tmp"
        self.files.write(tmp, json.dumps(data))
        self.files.replace(tmp, self.path)

    def load(self, unix_now=None, now=None):
        """Read the queue after a reboot. Returns (resumed, gave_up), both lists of entries.

        How old an entry is: with the clock set now and a press time (wall) saved,
        unix_now - wall. Otherwise the age saved at the last write (the time the Fob was
        off is unknown, so this can be too young). Entries for_ms or older are given up."""
        now = self.clock() if now is None else now
        data = None
        # A .tmp file that reads in full is newer (the power went off before the rename).
        # A half-written one fails to parse, and the real file is used.
        for name in (self.path + ".tmp", self.path):
            text = self.files.read(name)
            if text is None:
                continue
            try:
                data = json.loads(text)
                if isinstance(data, dict) and isinstance(data.get("entries"), list):
                    break
            except ValueError:
                pass
            data = None
        self.entries = []
        resumed, gave_up = [], []
        if data is None:
            return resumed, gave_up
        for raw in data["entries"]:
            try:
                age = int(raw.get("age_ms") or 0)
                wall = raw.get("wall")
                if wall is not None and unix_now is not None:
                    age = max(age, int((unix_now - wall) * 1000))
                e = {"ctr": int(raw["ctr"]), "kind": str(raw["kind"]), "payload": str(raw["payload"]),
                     "sig": str(raw["sig"]), "wall": wall, "tries": int(raw.get("tries") or 0),
                     "start": self.add_ms(now, -age), "next": now}
            except (KeyError, TypeError, ValueError):
                continue                            # one bad entry never stops the rest
            if age >= self.for_ms:
                gave_up.append(e)
            elif len(self.entries) < self.max_n:
                self.entries.append(e)
                resumed.append(e)
        return resumed, gave_up


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
