"""Laptop test: no firmware module imports inside a function, and nothing touches flash
while the Fob listens for "help is coming".

Why: on 2026-11-11 the Fob crashed (Guru Meditation, Cache error) 5.8 s into
HELP_LISTEN. helplisten.py did "import select" inside a function that ran every 10 ms.
select is a built-in that a file of the same name can replace, so each import looked
on the file system first: a flash read every 10 ms, with WiFi busy. The crash dump held
the text "/lib/select".

  1. source check: every import in firmware/fob, firmware/lib and firmware/relay is at
     module level (a try/except at the top is fine), never inside a def or lambda
  2. the button interrupt handler (presslog.EdgeLog.irq) calls nothing that can reach
     flash or allocate: no open, print, import or new objects
  3. the real main.py on a fake board: 2 minutes of HELP_LISTEN make no file system call
     at all, a new press closes the listener before the counter is written, and a retry
     queue save waits until listening ends

  python tests/test_imports.py"""
import ast
import builtins
import contextlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, "..", "firmware")
FOLDERS = ("fob", "lib", "relay")          # what runs on the boards. bringup/ and archive/ are bench scripts
sys.path.insert(0, HERE)

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


# ---------- 1. imports ----------
class ImportFinder(ast.NodeVisitor):
    def __init__(self):
        self.depth = 0
        self.bad = []

    def _inside(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_FunctionDef = _inside
    visit_AsyncFunctionDef = _inside
    visit_Lambda = _inside

    def _import(self, node):
        if self.depth:
            names = ", ".join(a.name for a in node.names)
            if isinstance(node, ast.ImportFrom):
                names = "from {} import {}".format(node.module, names)
            self.bad.append("line {}: {}".format(node.lineno, names))

    visit_Import = _import
    visit_ImportFrom = _import


def firmware_files():
    for folder in FOLDERS:
        path = os.path.join(FIRMWARE, folder)
        for name in sorted(os.listdir(path)):
            if name.endswith(".py") and name != "config.example.py":
                yield folder + "/" + name, os.path.join(path, name)


def bad_imports(source, name="x"):
    finder = ImportFinder()
    finder.visit(ast.parse(source, name))
    return finder.bad


def test_imports():
    # the checker itself catches what it should
    check("checker: an import in a def is caught",
          bad_imports("def f():\n    import select\n") == ["line 2: select"])
    check("checker: a top-level try/except import is fine",
          bad_imports("try:\n    import select\nexcept ImportError:\n    select = None\n") == [])
    check("checker: an import in a method is caught",
          len(bad_imports("class A:\n    def m(self):\n        from machine import SPI\n")) == 1)
    files = list(firmware_files())
    check("found the firmware files", len(files) >= 10, str(len(files)))
    for rel, path in files:
        with open(path, encoding="utf-8") as f:
            bad = bad_imports(f.read(), rel)
        check("{}: no import inside a function".format(rel), not bad, "; ".join(bad))


# ---------- 2. the interrupt handler ----------
def test_irq_handler():
    with open(os.path.join(FIRMWARE, "lib", "presslog.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    irq = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "irq":
            irq = node
    calls = []
    for node in ast.walk(irq):
        if isinstance(node, ast.Call):
            f = node.func
            calls.append(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "?"))
    allowed = {"clock", "value"}             # ticks_ms() and pin.value(): no flash, no allocation
    check("button irq handler only calls the clock and pin.value()", set(calls) <= allowed, str(calls))
    makes = [type(n).__name__ for n in ast.walk(irq)
             if isinstance(n, (ast.List, ast.Dict, ast.Tuple, ast.Set, ast.JoinedStr, ast.ListComp))]
    check("button irq handler makes no new objects", makes == [], str(makes))


# ---------- 3. no flash during HELP_LISTEN ----------
class FsSpy:
    """Counts every file system call while active."""

    def __init__(self):
        self.calls = []
        self.on = False
        self._open, self._stat = builtins.open, os.stat
        self._rename, self._remove = os.rename, os.remove

    def _wrap(self, name, real):
        def spy(*a, **k):
            if self.on:
                self.calls.append((name, str(a[0]) if a else ""))
            return real(*a, **k)
        return spy

    def __enter__(self):
        builtins.open = self._wrap("open", self._open)
        os.stat = self._wrap("stat", self._stat)
        os.rename = self._wrap("rename", self._rename)
        os.remove = self._wrap("remove", self._remove)
        return self

    def __exit__(self, *exc):
        builtins.open, os.stat = self._open, self._stat
        os.rename, os.remove = self._rename, self._remove


class FakeClient:
    def __init__(self):
        self.inbox = []
        self.sock = object()
        self.cb = None
        self.left_ms = lambda: 1000

    def set_callback(self, cb):
        self.cb = cb

    def wait_msg(self):
        topic, msg = self.inbox.pop(0)
        self.cb(topic, msg)

    def ping(self):
        pass

    def disconnect(self):
        pass

    def close(self):
        pass


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


def test_no_flash_while_listening():
    import fakeboard
    main = fakeboard.load_fob(workdir=tempfile.mkdtemp())
    fob = main.Fob()
    clients = []

    def wifi_ok(payload, ctr, sig, budget, service=None, keep_open=None, stop=None):
        c = FakeClient()
        clients.append(c)
        if keep_open is not None:
            keep_open.append(c)
        return True, "-", True, None
    main.wifi_send = wifi_ok
    fob.help.ready = lambda sock: False
    fob.state = main.IDLE
    quiet(fob.send, "SUSPICIOUS")
    check("listening after the confirm", fob.help.active())

    with FsSpy() as spy:
        spy.on = True
        for _ in range(12000):                     # 2 minutes of 10 ms loops
            fakeboard.clock[0] += 10
            quiet(fob.step, fakeboard.clock[0])
        spy.on = False
    check("2 minutes of HELP_LISTEN: no file system call at all", spy.calls == [], str(spy.calls[:5]))
    check("listening ended on time", not fob.help.active())

    # a press while listening: the listener is closed BEFORE the counter is written
    fob.state = main.IDLE
    quiet(fob.send, "MEDICAL")
    order = []
    real_close = fob.help.close
    fob.help.close = lambda reason="closed": order.append(("close", fob.help.active())) or real_close(reason)
    real_next = main.next_counter
    main.next_counter = lambda: order.append(("counter", fob.help.active())) or real_next()
    fob.state = main.IDLE
    quiet(fob.send, "SILENT")
    main.next_counter = real_next
    fob.help.close = real_close
    check("a press while listening: listener closed before the counter write",
          order[:2] == [("close", True), ("counter", False)], str(order))

    # a retry that gets through while help is waiting: the queue save waits
    fob.queue.add(900, "SUSPICIOUS", '{"ctr": 900}', "s", None)
    fob.queue.entries[0]["next"] = fakeboard.clock[0]
    with FsSpy() as spy:
        spy.on = True
        quiet(fob.run_retries)
        listening = fob.help.active()
        spy.on = False
    writes = [c for c in spy.calls if c[0] in ("open", "rename")]
    check("retry confirmed while help is waiting: no flash write while listening",
          listening and writes == [] and fob.queue_dirty, "{} {}".format(listening, writes))
    with FsSpy() as spy:
        spy.on = True
        for _ in range(13000):
            fakeboard.clock[0] += 10
            quiet(fob.step, fakeboard.clock[0])
        spy.on = False
    check("the waiting save happens once listening ends",
          not fob.queue_dirty and any(c[0] == "rename" for c in spy.calls), str(spy.calls[:4]))

    # the CA file is checked once (boot_wifi does the first check), not on every send
    main.ca_present()
    with FsSpy() as spy:
        spy.on = True
        main.ca_present()
        main.ca_present()
        spy.on = False
    check("CA file presence is remembered (no stat per send)", spy.calls == [], str(spy.calls))


def main():
    test_imports()
    test_irq_handler()
    test_no_flash_while_listening()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
