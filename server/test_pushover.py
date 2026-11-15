"""Pushover notifications (server/pushover.py) against a fake Pushover endpoint.

The fake endpoint runs on 127.0.0.1 inside this script and records every request.
Nothing is sent to the real Pushover. Runs against a throwaway database and a
throwaway places.json, so it never touches real data. The Fob key is made fresh
on each run.

  python test_pushover.py"""
import contextlib
import io
import json
import os
import secrets
import socket
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# Throwaway database and places file. This must happen before config is imported.
_tmp = tempfile.mkdtemp()
os.environ["SAFEPING_DB"] = os.path.join(_tmp, "test.db")
os.environ["SAFEPING_PLACES"] = os.path.join(_tmp, "places.json")
for _name in ("SAFEPING_PUSHOVER_USER", "SAFEPING_PUSHOVER_TOKEN", "SAFEPING_PUBLIC_URL"):
    os.environ.pop(_name, None)
with open(os.environ["SAFEPING_PLACES"], "w", encoding="utf-8") as _f:
    json.dump([{"name": "the front gate", "lat": 40.0, "lon": -74.0}], _f)

import config      # noqa: E402
import db          # noqa: E402
import fake_fob    # noqa: E402
import processor   # noqa: E402
import pushover    # noqa: E402
import validate    # noqa: E402

KEY = secrets.token_hex(16)               # made fresh, never written down
FAKE_USER = "fake-user-for-tests"         # placeholders, not real Pushover values
FAKE_TOKEN = "fake-token-for-tests"
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


# ---------- the fake Pushover endpoint ----------

class Fake:
    requests = []                 # parsed form fields of every request
    reply = (200, {"status": 1, "request": "fake"})


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        Fake.requests.append({k: v[0] for k, v in urllib.parse.parse_qs(body).items()})
        code, reply = Fake.reply
        data = json.dumps(reply).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):     # keep the test output clean
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------- helpers ----------

counter = [0]


def alert(msg_type, device="FOB-P1", ts="now", **kw):
    """Signs and processes one new message. Returns (result, the message, new requests, printed text)."""
    counter[0] += 1
    if ts == "now":
        ts = int(time.time())
    msg = fake_fob.build_message(device, KEY, msg_type, counter[0], device_ts=ts, **kw)
    return run(msg)


def run(msg):
    before = len(Fake.requests)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = processor.process(json.dumps(msg), source="wifi")
    return r, msg, Fake.requests[before:], out.getvalue()


def turn_on(url):
    config.PUSHOVER_USER = FAKE_USER
    config.PUSHOVER_TOKEN = FAKE_TOKEN
    config.PUSHOVER_API_URL = url


def main():
    db.init_db()
    db.add_device("FOB-P1", "FOB", "Test Student", KEY)
    db.add_device("FOB-P2", "FOB", None, KEY)

    port = free_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake_url = "http://127.0.0.1:{}/1/messages.json".format(port)

    # ---- the real endpoint is the default, and it is not read from the environment ----
    check("default endpoint is Pushover over HTTPS",
          config.PUSHOVER_API_URL == "https://api.pushover.net/1/messages.json")
    config.PUSHOVER_API_URL = fake_url

    # ---- off: either value missing ----
    check("off with no variables", not pushover.enabled())
    r, _m, reqs, out = alert("MEDICAL")
    check("off: alert still stored", r["ok"] and r["kind"] == "alert", str(r))
    check("off: result says 'off'", r["pushover"] == "off", str(r))
    check("off: nothing sent", reqs == [])
    check("off: logs 'Pushover off'", "Pushover off" in out, out.strip())
    r, _m, reqs, out = alert("SUSPICIOUS")
    check("off: 'Pushover off' logged only once", "Pushover off" not in out, out.strip())
    config.PUSHOVER_USER = FAKE_USER
    check("off with only the user set", not pushover.enabled())
    config.PUSHOVER_USER, config.PUSHOVER_TOKEN = None, FAKE_TOKEN
    check("off with only the token set", not pushover.enabled())
    config.PUSHOVER_TOKEN = None
    check("Health says off", pushover.health()["enabled"] is False)

    # ---- on ----
    turn_on(fake_url)
    config.PUBLIC_URL = "http://dash.test:5000"
    check("on with both variables", pushover.enabled())

    # MEDICAL, GPS 10 m from a named place, on time
    r, msg, reqs, out = alert("MEDICAL", lat=40.00009, lon=-74.0, acc=8)
    check("MEDICAL sends one notification", len(reqs) == 1, str(len(reqs)))
    p = reqs[0] if reqs else {}
    check("MEDICAL result says 'sent'", r.get("pushover") == "sent", str(r))
    check("title 'SafePing MEDICAL'", p.get("title") == "SafePing MEDICAL", p.get("title"))
    check("MEDICAL emergency priority 2", p.get("priority") == "2")
    check("MEDICAL retry 60 s", p.get("retry") == "60")
    check("MEDICAL expire 30 min", p.get("expire") == "1800")
    body = p.get("message", "")
    check("body has the student name and device id", "Test Student (FOB-P1)" in body, body)
    check("body has the place in words", "Near the front gate" in body, body)
    check("body has the press time", "Pressed " + pushover._clock(msg["ts"], time.time()) in body, body)
    check("on time: no 'Arrived late'", "Arrived late" not in body, body)
    check("link to the alert on the dashboard",
          p.get("url") == "http://dash.test:5000/#/alert/{}".format(r["alert_id"]), p.get("url"))
    check("link has a title", p.get("url_title") == "Open in SafePing")
    check("keys go in the request", p.get("token") == FAKE_TOKEN and p.get("user") == FAKE_USER)
    check("keys never printed", FAKE_TOKEN not in out and FAKE_USER not in out, out.strip())
    medical = msg

    # SUSPICIOUS
    r, _m, reqs, _o = alert("SUSPICIOUS")
    p = reqs[0] if reqs else {}
    check("SUSPICIOUS sends one", len(reqs) == 1)
    check("title 'SafePing SUSPICIOUS'", p.get("title") == "SafePing SUSPICIOUS")
    check("SUSPICIOUS high priority 1", p.get("priority") == "1")
    check("SUSPICIOUS has no retry or expire", "retry" not in p and "expire" not in p)
    check("SUSPICIOUS keeps the sound", "sound" not in p)
    check("no location: no location line", p.get("message", "").split("\n")[1].startswith("Pressed"), p.get("message"))

    # SILENT
    r, _m, reqs, _o = alert("SILENT")
    p = reqs[0] if reqs else {}
    check("SILENT sends one", len(reqs) == 1)
    check("title 'SafePing SILENT'", p.get("title") == "SafePing SILENT")
    check("SILENT normal priority 0", p.get("priority") == "0")
    check("SILENT has no sound", p.get("sound") == "none")

    # STATUS and BOOT never send
    r, _m, reqs, _o = alert("STATUS", battery=90)
    check("STATUS stored", r["ok"] and r["type"] == "STATUS")
    check("STATUS never sends", reqs == [] and r["pushover"] is None, str(r))
    counter[0] += 1
    boot = {"v": 1, "id": "FOB-P1", "type": "BOOT", "ctr": counter[0], "ts": int(time.time()),
            "fail": 0, "wifi": 1, "fw": "2026.11.14"}
    boot["sig"] = validate.sign(KEY, boot)
    r, _m, reqs, _o = run(boot)
    check("BOOT stored as a boot report", r.get("kind") == "boot", str(r))
    check("BOOT never sends", reqs == [])

    # Late: pressed 5 minutes before it arrived
    r, msg, reqs, _o = alert("SUSPICIOUS", ts=int(time.time()) - 300)
    body = reqs[0]["message"] if reqs else ""
    check("late alert tagged late", r.get("late") == "late", str(r))
    check("late: press time in the body", "Pressed " + pushover._clock(msg["ts"], time.time()) in body, body)
    check("late: 'Arrived late at' in the body", "Arrived late at " in body, body)

    # No Fob clock
    r, _m, reqs, _o = alert("SILENT", ts=None)
    body = reqs[0]["message"] if reqs else ""
    check("no clock: says press time unknown", "Press time unknown" in body and "Received " in body, body)

    # GPS far from every place: coordinates instead
    r, _m, reqs, _o = alert("SUSPICIOUS", lat=40.01, lon=-74.01, acc=12)
    body = reqs[0]["message"] if reqs else ""
    check("GPS with no named place: coordinates", "GPS 40.01000, -74.01000, about 12 m" in body, body)

    # GPS 100 m north of the place
    r, _m, reqs, _o = alert("SUSPICIOUS", lat=40.0009, lon=-74.0)
    body = reqs[0]["message"] if reqs else ""
    check("GPS 100 m away: distance and direction", "100 m N of the front gate" in body, body)

    # Floor from the reference sensor
    db.insert_reference(time.time(), 101325, 2000)
    r, _m, reqs, _o = alert("MEDICAL", pressure=101325 - int(config.PA_PER_FLOOR))
    body = reqs[0]["message"] if reqs else ""
    check("floor in words", "Indoors, floor 2" in body, body)

    # A Fob with no student name
    r, _m, reqs, _o = alert("SILENT", device="FOB-P2")
    body = reqs[0]["message"] if reqs else ""
    check("no student name: device id only", body.split("\n")[0] == "FOB-P2", body)

    # ---- duplicates and replays never send ----
    r, _m, reqs, _o = run(medical)
    check("exact copy is 'duplicate'", r == {"ok": False, "reason": "duplicate"}, str(r))
    check("duplicate never sends", reqs == [])
    replay = dict(medical, type="SILENT")
    replay.pop("sig")
    replay["sig"] = validate.sign(KEY, replay)
    r, _m, reqs, _o = run(replay)
    check("used counter, different message is 'replay'", r.get("reason") == "replay", str(r))
    check("replay never sends", reqs == [])
    counter[0] += config.COUNTER_WINDOW + 5
    alert("SUSPICIOUS")
    old = fake_fob.build_message("FOB-P1", KEY, "MEDICAL", counter[0] - config.COUNTER_WINDOW - 3,
                                 device_ts=int(time.time()))
    r, _m, reqs, _o = run(old)
    check("counter below the window is 'replay'", r.get("reason") == "replay", str(r))
    check("old-counter replay never sends", reqs == [])
    forged = dict(medical, ctr=counter[0] + 1)
    r, _m, reqs, _o = run(forged)
    check("bad signature never sends", r.get("reason") == "bad_signature" and reqs == [], str(r))

    # ---- no public address: no link ----
    config.PUBLIC_URL = None
    r, _m, reqs, _o = alert("SUSPICIOUS")
    p = reqs[0] if reqs else {}
    check("no SAFEPING_PUBLIC_URL: no link", "url" not in p and "url_title" not in p, str(p.keys()))

    # ---- Health after a send ----
    h = pushover.health()
    check("Health: on", h["enabled"] is True)
    check("Health: last send just now", h["last_send_age_s"] is not None and h["last_send_age_s"] <= 5, str(h))
    check("Health: last send alert id", h["last_send_alert"] == r["alert_id"], str(h))
    check("Health: no error yet", h["last_error"] is None and h["last_error_age_s"] is None, str(h))
    check("Health: not failing", h["failing"] is False, str(h))

    # ---- Pushover refuses (bad user key) ----
    Fake.reply = (400, {"status": 0, "errors": ["user identifier is not a valid user, group, or subscribed user key"]})
    r, _m, reqs, out = alert("MEDICAL")
    check("refused: alert still stored", r["ok"] and r["kind"] == "alert", str(r))
    check("refused: result says 'failed'", r["pushover"] == "failed", str(r))
    check("refused: error printed", "[Pushover failed]" in out and "HTTP 400" in out, out.strip())
    h = pushover.health()
    check("Health: last error saved", "HTTP 400" in (h["last_error"] or "") and "user identifier" in h["last_error"], str(h))
    check("Health: last error alert id", h["last_error_alert"] == r["alert_id"], str(h))
    check("Health: last send kept", h["last_send_alert"] is not None)
    check("Health: failing after an error", h["failing"] is True, str(h))
    check("error never holds the keys", FAKE_TOKEN not in h["last_error"] and FAKE_USER not in h["last_error"])

    # A reply that echoes the token is cleaned before printing and saving
    Fake.reply = (400, {"status": 0, "errors": ["token " + FAKE_TOKEN + " is invalid"]})
    r, _m, reqs, out = alert("SUSPICIOUS")
    h = pushover.health()
    check("echoed token hidden in the log", FAKE_TOKEN not in out, out.strip())
    check("echoed token hidden in Health", FAKE_TOKEN not in h["last_error"] and "(hidden)" in h["last_error"], h["last_error"])

    # 200 without status 1
    Fake.reply = (200, {"status": 0, "errors": ["application token is invalid"]})
    r, _m, _r, _o = alert("SILENT")
    check("status 0 counts as failed", r["pushover"] == "failed" and "refused" in pushover.health()["last_error"],
          pushover.health()["last_error"])

    # Nothing listening
    config.PUSHOVER_API_URL = "http://127.0.0.1:{}/1/messages.json".format(free_port())
    t = time.time()
    r, _m, _r, out = alert("MEDICAL")
    check("no connection: alert stored, result 'failed'", r["ok"] and r["pushover"] == "failed", str(r))
    check("no connection: reason saved", "no connection" in pushover.health()["last_error"], pushover.health()["last_error"])
    check("no connection: does not hold things up", time.time() - t < config.PUSHOVER_TIMEOUT_S + 1)

    # ---- back to working ----
    Fake.reply = (200, {"status": 1, "request": "fake"})
    config.PUSHOVER_API_URL = fake_url
    r, _m, reqs, _o = alert("SUSPICIOUS")
    h = pushover.health()
    check("works again after errors", r["pushover"] == "sent" and h["last_send_alert"] == r["alert_id"])
    check("Health: last error is older than the last send", h["last_error_age_s"] >= h["last_send_age_s"], str(h))
    check("Health: not failing once a send works", h["failing"] is False, str(h))

    # ---- /api/stats carries it for Settings > Health ----
    import app
    web = app.app.test_client()
    today = time.strftime("%Y-%m-%d")
    data = web.get("/api/stats?from={}&to={}".format(today, today)).get_json()
    po = data.get("pushover") or {}
    check("/api/stats has pushover", po.get("enabled") is True and po.get("last_send_alert") == r["alert_id"], str(po))
    check("/api/stats never has the keys", FAKE_TOKEN not in json.dumps(data) and FAKE_USER not in json.dumps(data))

    # ---- the press date shows when it was not the same day ----
    now = time.time()
    check("same day: time only", "," not in pushover._clock(now, now))
    check("other day: date in front", "," in pushover._clock(now - 2 * 86400, now))

    server.shutdown()
    print()
    print("{} of {} passed".format(sum(results), len(results)))
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
