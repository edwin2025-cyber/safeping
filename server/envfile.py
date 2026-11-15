"""Reads the settings file safeping.env (NAME=value lines) into the environment.

Where it looks:
    SAFEPING_ENV_FILE, when set
    otherwise %USERPROFILE%\\Documents\\safeping-private\\safeping.env
No file: nothing happens, the settings come from the environment as before.

Rules:
    - A setting already in the environment ($env:NAME = ...) wins over the file.
    - Blank lines and lines starting with # are skipped. Comments go on their own line.
    - Spaces around = are fine. "export NAME=value" is fine.
    - Quotes around a value are removed: NAME="a b" and NAME='a b' give a b.
    - The hidden marker Notepad can put at the start of a file (UTF-8 BOM) is ignored.
    - A file inside the repo folder is refused, so it can never be committed by mistake.
    - Only names are printed, never values.

Used by server/app.py, serial_bridge.py, mqtt_listener.py, fake_fob.py and the laptop
tools in tests/ (field_log.py, broker_check.py, ref_calibrate.py, survey_analyze.py).
Each calls load() only when it runs as a program, before it reads any setting, so the
tests (which import those files) never read the real settings file.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normcase(os.path.realpath(os.path.join(HERE, "..")))
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_loaded = {}          # path -> result, so a second load() in the same program does nothing


def default_path(environ=None):
    environ = os.environ if environ is None else environ
    given = environ.get("SAFEPING_ENV_FILE")
    if given:
        return os.path.expanduser(given)
    return os.path.join(os.path.expanduser("~"), "Documents", "safeping-private", "safeping.env")


def inside_repo(path, repo=None):
    """True when path is in the repo folder (or below it)."""
    # Both sides through realpath, so a short Windows name (EDWINN~1) and the long one match.
    repo = os.path.normcase(os.path.realpath(repo or REPO))
    full = os.path.normcase(os.path.realpath(path))
    return full == repo or full.startswith(repo.rstrip("\\/") + os.sep)


def parse(text):
    """{name: value} and the numbers of the lines that were not NAME=value."""
    if text.startswith("\ufeff"):
        text = text[1:]
    values, bad = {}, []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not NAME_RE.match(name):
            bad.append(number)
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values, bad


def load(path=None, environ=None, quiet=False, repo=None):
    """Put the file's settings into the environment. Returns a dict:
    path, found, refused, loaded (names set from the file), kept (names the environment
    already had), bad_lines (line numbers). Prints one line unless quiet."""
    environ = os.environ if environ is None else environ
    path = os.path.abspath(path or default_path(environ))
    if environ is os.environ and path in _loaded:
        return _loaded[path]
    result = {"path": path, "found": False, "refused": False, "loaded": [], "kept": [], "bad_lines": []}
    say = (lambda text: None) if quiet else print
    if not os.path.isfile(path):
        say("Settings: no settings file at {}, using the environment only".format(path))
    elif inside_repo(path, repo):
        result["refused"] = True
        say("Settings: NOT read. {} is inside the repo folder, where it could be committed. "
            "Move it to Documents\\safeping-private.".format(path))
    else:
        result["found"] = True
        with open(path, encoding="utf-8", errors="replace") as f:
            values, result["bad_lines"] = parse(f.read())
        for name in sorted(values):
            if environ.get(name) not in (None, ""):
                result["kept"].append(name)
            else:
                environ[name] = values[name]
                result["loaded"].append(name)
        text = "Settings: {} names from {}".format(len(result["loaded"]), path)
        if result["loaded"]:
            text += " ({})".format(", ".join(result["loaded"]))
        if result["kept"]:
            text += ". Already set in the environment, kept: {}".format(", ".join(result["kept"]))
        if result["bad_lines"]:
            text += ". Lines skipped (not NAME=value): {}".format(", ".join(str(n) for n in result["bad_lines"]))
        say(text)
    if environ is os.environ:
        _loaded[path] = result
    return result
