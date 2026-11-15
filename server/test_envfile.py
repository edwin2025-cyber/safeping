"""The settings file loader (server/envfile.py), with fake files only.

  - comments, blank lines, spaces around =, quotes, "export", the hidden marker (BOM)
  - a value may hold = and #
  - a missing file changes nothing
  - a setting already in the environment wins over the file
  - a file inside the repo folder is refused
  - only names are printed, never values
  - importing the server programs (as the tests do) never reads the settings file,
    and every program calls the loader when it runs
  - .gitignore keeps every *.env file out of git

  python test_envfile.py"""
import contextlib
import importlib
import io
import os
import subprocess
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["SAFEPING_DB"] = os.path.join(_tmp, "test.db")

import envfile  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + str(detail) if detail and not passed else ""))


def write(text, name="safeping.env", folder=None, bom=False):
    folder = folder or tempfile.mkdtemp()
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        f.write(text)
    return path


def load(path, environ, repo=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = envfile.load(path, environ=environ, repo=repo)
    return result, out.getvalue()


SAMPLE = (
    "# SafePing settings\n"
    "\n"
    "SAFEPING_MQTT_HOST=example-broker.invalid\n"
    "  SAFEPING_MQTT_USER  =  safeping-server  \n"
    'SAFEPING_MQTT_PASS="placeholder pass with spaces"\n'
    "CARTO_KEY='placeholder-carto'\n"
    "export PA_PER_FLOOR=55\n"
    "TEXTBELT_KEY=placeholder=with#signs\n"
    "this line is not a setting\n"
    "   # an indented comment\n"
    "SAFEPING_SMS=\n"
    "2BAD=x\n"
)


def test_parse():
    values, bad = envfile.parse(SAMPLE)
    check("plain NAME=value", values.get("SAFEPING_MQTT_HOST") == "example-broker.invalid")
    check("spaces around the name, = and value", values.get("SAFEPING_MQTT_USER") == "safeping-server")
    check("double quotes removed, spaces inside kept", values.get("SAFEPING_MQTT_PASS") == "placeholder pass with spaces")
    check("single quotes removed", values.get("CARTO_KEY") == "placeholder-carto")
    check("export NAME=value", values.get("PA_PER_FLOOR") == "55")
    check("a value may hold = and #", values.get("TEXTBELT_KEY") == "placeholder=with#signs")
    check("an empty value is allowed", values.get("SAFEPING_SMS") == "")
    check("comments and blank lines skipped", not any(k.startswith("#") for k in values))
    check("lines that are not NAME=value are reported by number", bad == [9, 12], bad)
    values2, bad2 = envfile.parse("\ufeffSAFEPING_MQTT_HOST=x\r\nPORT = 8883\r\n")
    check("the hidden marker (BOM) at the start is ignored",
          values2 == {"SAFEPING_MQTT_HOST": "x", "PORT": "8883"} and bad2 == [], (values2, bad2))
    values3, _ = envfile.parse('A="unclosed\nB="x"y"\n')
    check("quotes only removed when they match at both ends", values3 == {"A": '"unclosed', "B": 'x"y'}, values3)


def test_load():
    path = write(SAMPLE, bom=True)
    env = {"SAFEPING_MQTT_USER": "already-set-in-terminal"}
    result, out = load(path, env)
    check("file found and read (written by Notepad with a BOM)", result["found"] and not result["refused"])
    check("names from the file are set", env.get("SAFEPING_MQTT_HOST") == "example-broker.invalid"
          and env.get("PA_PER_FLOOR") == "55")
    check("a setting already in the environment wins", env["SAFEPING_MQTT_USER"] == "already-set-in-terminal"
          and "SAFEPING_MQTT_USER" in result["kept"])
    check("the printed line counts the names and names the file",
          out.startswith("Settings: {} names from {}".format(len(result["loaded"]), path)), out)
    check("names are printed", "SAFEPING_MQTT_HOST" in out and "TEXTBELT_KEY" in out)
    for value in ("example-broker.invalid", "placeholder pass with spaces", "placeholder-carto",
                  "placeholder=with#signs", "already-set-in-terminal"):
        check("value never printed: " + value[:12], value not in out)
    check("skipped lines reported by number only", "Lines skipped (not NAME=value): 9, 12" in out
          and "this line is not" not in out, out)
    env2 = {"SAFEPING_SMS": ""}
    load(write("SAFEPING_SMS=live\n"), env2)
    check("an empty environment value counts as not set (the file fills it)", env2["SAFEPING_SMS"] == "live")

    missing = os.path.join(tempfile.mkdtemp(), "nothing-here.env")
    env3 = {"X": "1"}
    result, out = load(missing, env3)
    check("missing file: nothing changes, carries on", not result["found"] and env3 == {"X": "1"}
          and "no settings file" in out, out)

    folder = tempfile.mkdtemp()                # stands in for the repo folder
    sub = os.path.join(folder, "server")
    os.makedirs(sub)
    inside = write("SECRET_THING=1\n", folder=sub)
    env4 = {}
    result, out = load(inside, env4, repo=folder)
    check("a file inside the repo folder is refused", result["refused"] and env4 == {} and "NOT read" in out, out)
    check("the real repo folder is recognized", envfile.inside_repo(os.path.join(REPO, "server", "safeping.env"))
          and not envfile.inside_repo(os.path.join(os.path.expanduser("~"), "Documents", "safeping-private", "safeping.env")))
    check("default place: Documents\\safeping-private\\safeping.env",
          envfile.default_path({}).endswith(os.path.join("Documents", "safeping-private", "safeping.env")))
    check("SAFEPING_ENV_FILE overrides the place", envfile.default_path({"SAFEPING_ENV_FILE": "C:\\x\\y.env"}) == "C:\\x\\y.env")


def test_programs():
    marker = write("SAFEPING_TEST_MARKER_FROM_FILE=1\n")
    os.environ["SAFEPING_ENV_FILE"] = marker
    sys.path.insert(0, os.path.join(REPO, "tests"))
    with contextlib.redirect_stdout(io.StringIO()):
        for name in ("app", "serial_bridge", "mqtt_listener", "fake_fob", "field_log", "ref_calibrate", "survey_analyze"):
            importlib.import_module(name)
    check("importing the programs (as tests do) never reads the settings file",
          "SAFEPING_TEST_MARKER_FROM_FILE" not in os.environ)
    os.environ.pop("SAFEPING_ENV_FILE", None)
    files = {
        "server/app.py": "envfile.load()", "server/serial_bridge.py": "envfile.load()",
        "server/mqtt_listener.py": "envfile.load()", "server/fake_fob.py": "envfile.load()",
        "tests/broker_check.py": "envfile.load()", "tests/field_log.py": "load_settings()",
        "tests/ref_calibrate.py": "load_settings()", "tests/survey_analyze.py": "load_settings()",
    }
    for rel, call in files.items():
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            check("{} loads the settings file when it runs".format(rel), call in f.read())


def test_gitignore():
    for name in ("safeping.env", "server/safeping.env", "tests/local.env", "safeping.env.bak", ".env"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=REPO, capture_output=True)
        check(".gitignore keeps {} out of git".format(name), r.returncode == 0, r.returncode)


def main():
    test_parse()
    test_load()
    test_programs()
    test_gitignore()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
