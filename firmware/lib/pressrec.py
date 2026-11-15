"""A press that a crash cannot lose, and a copy of the counter that a crash cannot lose.

Why: on 2026-11-13 at 12:31:30 a press stopped a retry, the Fob saved queue.json, and
the board crashed (cache error) in that save. The press had no counter yet and was
only in RAM, so after the reboot it was gone.

How: the press is written to RTC memory (machine.RTC().memory()) the moment the Fob
sees it, before any flash access. RTC memory is plain RAM that keeps its content
through a crash reset and a soft reset. It is lost when the power goes off, and the
queue file in flash covers that case. Writing it never touches flash.

RTC memory holds one JSON object after the magic text:
  "ctr"    the last counter the Fob took, written BEFORE counter.txt (counterfile.py).
           At boot the counter jumps ahead from the highest of this and the file.
  "press"  one press at a time (the newest stage wins), or null:
    "press"   a pattern not finished: taps (releases so far), down (button down now),
              hold (down for CUT_HOLD_MS or more: a hold that started)
    "kind"    the pattern is decided (STATUS, SUSPICIOUS, MEDICAL, SILENT), not signed yet
    "signed"  the message is signed: ctr, kind, payload, sig, wall
The press is cleared once the alert is confirmed, or saved in queue.json, or cancelled.

After a crash, at boot (message-format.md, "Press cut off by a restart"):
  "signed"  the same signed message goes into the retry queue (same ctr, same sig)
  "kind"    that kind is built and sent now, with a new counter and "cut": 1
  "press"   cut_kind(): 3 or more presses MEDICAL, 2 SUSPICIOUS, a hold that started
            SILENT, 1 STATUS. A press still down and not a hold counts as one more press.
            Sent with a new counter and "cut": 1
Each boot that finds a press adds 1 to its "boots". After MAX_BOOTS it is dropped, so
a press that itself crashes the Fob cannot make it restart forever.

Pure logic with an injectable store: tests/test_press_record.py runs it.
"""
import json

MAGIC = "SPP2"          # start of our data, so other RTC data is never read as a press
MAX_BOOTS = 3
KINDS = ("STATUS", "SUSPICIOUS", "MEDICAL", "SILENT")


def cut_kind(taps, down=False, hold=False):
    """The kind for a pattern a restart cut off (Edwin's rule, 2026-11-14)."""
    n = taps + (1 if down and not hold else 0)
    if n >= 3:
        return "MEDICAL"
    if n == 2:
        return "SUSPICIOUS"
    if hold:
        return "SILENT"
    return "STATUS"


class RtcStore:
    """machine.RTC().memory() on the board. Raises at start if this firmware has none."""

    def __init__(self, machine):
        self.rtc = machine.RTC()
        self.rtc.memory()                    # raises if RTC memory is not in this build

    def read(self):
        return bytes(self.rtc.memory())

    def write(self, data):
        self.rtc.memory(data)


class PressRecord:
    def __init__(self, store=None):
        self.store = store                   # None: everything is off, every call does nothing
        self.press = None                    # the press kept now (a dict), or None
        self.ctr = None                      # the last counter written here

    @property
    def stage(self):
        return None if self.press is None else self.press["stage"]

    def on(self):
        return self.store is not None

    def _save(self):
        if self.store is None:
            return
        try:
            self.store.write((MAGIC + json.dumps({"ctr": self.ctr, "press": self.press})).encode())
        except Exception as err:             # never let the record stop a send
            print("press record could not be written:", err)

    def _put(self, press):
        self.press = press
        self._save()

    # ---------- the counter copy ----------
    def counter(self, n):
        """Called with each new counter BEFORE counter.txt is written."""
        self.ctr = n
        self._save()

    # ---------- the press ----------
    def started(self, down=False):
        """The first sign of a press (the pin is low, or an edge is waiting). Writes only
        when nothing is kept, so it never wipes a tap count or a newer stage."""
        if self.press is None:
            self._put({"stage": "press", "taps": 0, "down": bool(down), "hold": False, "boots": 0})

    def pressing(self, taps):
        """The button went down, with taps releases before it."""
        if self.stage in (None, "press"):
            self._put({"stage": "press", "taps": taps, "down": True, "hold": False, "boots": 0})

    def tap(self, taps):
        """The button came up: taps releases so far."""
        if self.stage in (None, "press"):
            self._put({"stage": "press", "taps": taps, "down": False, "hold": False, "boots": 0})

    def hold(self):
        """The button has been down long enough to be a hold that started. Written once."""
        if self.stage == "press" and not self.press.get("hold"):
            p = dict(self.press)
            p["down"], p["hold"] = True, True
            self._put(p)

    def kind(self, kind):
        if self.stage != "signed":
            self._put({"stage": "kind", "kind": kind, "boots": 0})

    def signed(self, kind, ctr, payload, sig, wall=None):
        self._put({"stage": "signed", "kind": kind, "ctr": ctr, "payload": payload,
                   "sig": sig, "wall": wall, "boots": 0})

    def clear(self):
        """Forget the press. The counter copy stays."""
        if self.press is None:
            return
        self._put(None)

    # ---------- boot ----------
    def load(self):
        """At boot: reads the counter copy into self.ctr, and returns the kept press (a
        dict) or None. Counts this boot in the press. A press found MAX_BOOTS times
        already is dropped and returned with "dropped": True."""
        if self.store is None:
            return None
        try:
            raw = self.store.read()
        except Exception:
            return None
        data = parse(raw)
        if data is None:
            if raw:
                self._save()                 # not ours, or damaged: start clean
            return None
        self.ctr = data["ctr"]
        press = data["press"]
        if press is None:
            return None
        press["boots"] = int(press.get("boots") or 0) + 1
        if press["boots"] > MAX_BOOTS:
            self._put(None)
            dropped = dict(press)
            dropped["dropped"] = True
            return dropped
        self._put(press)
        return press


def parse(raw):
    """{"ctr": int or None, "press": dict or None} from raw bytes, or None if it is
    empty, not ours or damaged."""
    try:
        text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    except Exception:
        return None
    if not text.startswith(MAGIC):
        return None
    try:
        data = json.loads(text[len(MAGIC):])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    ctr = data.get("ctr")
    if ctr is not None and (not isinstance(ctr, int) or ctr < 0):
        return None
    press = data.get("press")
    if press is not None and not _press_ok(press):
        return None
    return {"ctr": ctr, "press": press}


def _press_ok(p):
    if not isinstance(p, dict):
        return False
    stage = p.get("stage")
    if stage == "press":
        return isinstance(p.get("taps"), int)
    if stage == "kind":
        return p.get("kind") in KINDS
    if stage == "signed":
        return (p.get("kind") in KINDS and isinstance(p.get("ctr"), int)
                and isinstance(p.get("payload"), str) and isinstance(p.get("sig"), str))
    return False


def resume_kind(press):
    """The kind to send now for a "press" or "kind" record."""
    if press["stage"] == "kind":
        return press["kind"]
    return cut_kind(press["taps"], press.get("down", False), press.get("hold", False))
