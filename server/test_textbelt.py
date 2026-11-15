"""Text messages through Textbelt (server/textbelt.py), against a fake Textbelt on
127.0.0.1. Nothing is sent to the real service. The numbers are fictional 555-01xx
numbers and the key is a placeholder.

  - the real URL is fixed in code, not read from the environment
  - dry (the default) prints the text and sends nothing, off does nothing
  - live: only MEDICAL, SUSPICIOUS and SILENT, only for a new saved alert. Never STATUS,
    BOOT, REF, SURVEY, a duplicate or a replay
  - the request: phone, message, sender=SafePing, key
  - the text: starts with "SafePing", type, name, device, place, press time, "arrived late
    at" or "Press time unknown", at most 160 characters, plain characters only
  - "Reply STOP to opt out" only on a number's first text
  - one text per alert per number, and the hourly cap (logged when hit)
  - textId and quotaRemaining stored, Settings > Health (orange under 25 credits)
  - a failed text never stops the alert, the ack or Pushover
  - the key is never printed or stored, numbers only as their last 2 digits
  - the serial bridge texts too
  - live mode on a test database runs as dry unless the test allows it

  python test_textbelt.py"""
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

_tmp = tempfile.mkdtemp()
os.environ["SAFEPING_DB"] = os.path.join(_tmp, "test.db")
os.environ["SAFEPING_PLACES"] = os.path.join(_tmp, "places.json")
for _name in ("SAFEPING_SMS", "TEXTBELT_KEY", "SAFEPING_SMS_TO", "SAFEPING_SMS_MAX_PER_HOUR",
              "SAFEPING_PUSHOVER_USER", "SAFEPING_PUSHOVER_TOKEN"):
    os.environ.pop(_name, None)
with open(os.environ["SAFEPING_PLACES"], "w", encoding="utf-8") as _f:
    json.dump([{"name": "the bus loop", "lat": 34.7318, "lon": -86.5842}], _f)

import config         # noqa: E402
import db             # noqa: E402
import fake_fob       # noqa: E402
import processor      # noqa: E402
import serial_bridge  # noqa: E402
import textbelt       # noqa: E402
import validate       # noqa: E402

KEY = secrets.token_hex(16)                 # device key, made fresh
FAKE_TB_KEY = "fake-textbelt-key-for-tests"
NUM_A, NUM_B = "5550100001", "5550100002"   # fictional numbers
results = []


def check(name, passed, detail=""):
    passed = bool(passed)
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + str(detail) if detail and not passed else ""))


class Fake:
    requests = []
    replies = []                  # queued replies, then the default
    default = {"success": True, "quotaRemaining": 40, "textId": "100"}
    next_id = [100]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        Fake.requests.append({k: v[0] for k, v in urllib.parse.parse_qs(body).items()})
        if Fake.replies:
            code, reply = Fake.replies.pop(0)
        else:
            Fake.next_id[0] += 1
            code, reply = 200, dict(Fake.default, textId=str(Fake.next_id[0]))
        data = json.dumps(reply).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


counter = [0]
OUT = []                         # everything printed, to check the key never shows


def alert(msg_type, device="FOB-S1", ts="now", acks=None, **kw):
    counter[0] += 1
    if ts == "now":
        ts = int(time.time())
    msg = fake_fob.build_message(device, KEY, msg_type, counter[0], device_ts=ts, **kw)
    return run(json.dumps(msg), acks), msg


def run(payload, acks=None):
    before = len(Fake.requests)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = processor.process(payload, source="wifi",
                              on_ack=(lambda *a: acks.append(a)) if acks is not None else None)
    OUT.append(out.getvalue())
    return r, Fake.requests[before:], out.getvalue()


def live(url, numbers=(NUM_A, NUM_B), cap=20):
    config.SMS_MODE = "live"
    config.TEXTBELT_KEY = FAKE_TB_KEY
    config.SMS_TO = list(numbers)
    config.SMS_MAX_PER_HOUR = cap
    config.TEXTBELT_URL = url
    textbelt.ALLOW_LIVE_ON_TEST_DB = True


def main():
    db.init_db()
    db.add_device("FOB-S1", "FOB", "Test Student", KEY)
    db.add_device("FOB-S2", "FOB", "Zoë Ünicode-Name With A Very Long Family Name Indeed", KEY)
    db.add_device("REF-S1", "REF", None, KEY)
    port = free_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:{}/text".format(port)
    pushes = []
    processor.pushover.send = lambda *a, **k: pushes.append(a) or "off"

    # ---- defaults ----
    check("the real URL is fixed in code", config.TEXTBELT_URL == "https://textbelt.com/text")
    check("default mode is dry", config.SMS_MODE == "dry")
    check("default cap is 20 per hour", config.SMS_MAX_PER_HOUR == 20)
    config.TEXTBELT_URL = url
    config.SMS_TO = [NUM_A]
    (r, reqs, out), _ = alert("MEDICAL")
    check("dry: no request", reqs == [] and r["sms"] == "dry_run", r)
    check("dry: the text is printed, the number as its last 2 digits",
          "[SMS dry run] to ...01: SafePing MEDICAL" in out and NUM_A not in out, out)
    config.SMS_MODE = "off"
    (r, reqs, out), _ = alert("MEDICAL")
    check("off: nothing at all", reqs == [] and r["sms"] == "off" and "[SMS" not in out, r)

    # ---- the test database guard ----
    config.SMS_MODE, config.TEXTBELT_KEY, config.TEXTBELT_URL = "live", FAKE_TB_KEY, url
    textbelt.ALLOW_LIVE_ON_TEST_DB = False
    (r, reqs, out), _ = alert("MEDICAL")
    check("live on a test database runs as dry (no request)", reqs == [] and r["sms"] == "dry_run", r)

    # ---- live ----
    live(url)
    acks = []
    (r, reqs, out), msg = alert("MEDICAL", acks=acks, lat=34.7318, lon=-86.5842, acc=6)
    check("live MEDICAL: one request per number", len(reqs) == 2 and r["sms"] == "sent", reqs)
    q = reqs[0]
    check("request has phone, message, sender=SafePing and key",
          q["phone"] == NUM_A and q["sender"] == "SafePing" and q["key"] == FAKE_TB_KEY and q["message"], q)
    text = q["message"]
    check("text starts with SafePing and the type", text.startswith("SafePing MEDICAL: "), text)
    check("text has the name, device and place in words",
          "Test Student (FOB-S1)" in text and "Near the bus loop" in text, text)
    check("text has the press time", " Pressed " in text and ("AM" in text or "PM" in text), text)
    check("text at most 160 characters", len(text) <= 160, len(text))
    check("first text to a number has the STOP line", text.endswith("Reply STOP to opt out"), text)
    check("alert saved, acked, and Pushover called before the text",
          r["ok"] and len(acks) == 1 and len(pushes) >= 1, (r, acks))
    check("alert marked as texted", db.get_alert(r["alert_id"])["sms_sent"] == 1)
    with db.connect() as c:
        rows = [dict(x) for x in c.execute("SELECT * FROM sms_sent WHERE alert_id = ?", (r["alert_id"],))]
    check("textId stored for each number", sorted(x["text_id"] for x in rows) == sorted([str(Fake.next_id[0] - 1),
          str(Fake.next_id[0])]) and all(x["ok"] == 1 for x in rows), rows)
    check("numbers stored only as a hash and the last 2 digits",
          sorted(x["phone_last2"] for x in rows) == ["01", "02"] and all(NUM_A not in json.dumps(x) for x in rows))
    check("the log shows the last 2 digits and credits left",
          "sent to ...01" in out and "40 credits left" in out and NUM_A not in out, out)

    (r2, reqs, out), _ = alert("SUSPICIOUS")
    check("second text to the same numbers has no STOP line",
          len(reqs) == 2 and not reqs[0]["message"].endswith("Reply STOP to opt out"), reqs[0]["message"] if reqs else reqs)
    check("SUSPICIOUS is texted", r2["sms"] == "sent")
    (r3, reqs, out), _ = alert("SILENT", ts=None)
    check("SILENT is texted, with 'Press time unknown' when the Fob had no clock",
          len(reqs) == 2 and "Press time unknown, received " in reqs[0]["message"], reqs[0]["message"] if reqs else reqs)
    (r4, reqs, out), _ = alert("MEDICAL", ts=int(time.time()) - 400)
    check("late alert: 'arrived late at'", reqs and "arrived late at" in reqs[0]["message"], reqs[0]["message"] if reqs else reqs)

    # ---- never these ----
    before = len(Fake.requests)
    (r, reqs, out), stat = alert("STATUS")
    check("STATUS: no text", reqs == [] and r["sms"] is None, r)
    boot = {"v": 1, "id": "FOB-S1", "type": "BOOT", "ctr": counter[0] + 1, "fail": 0, "wifi": 1, "fw": "t", "rst": 1}
    counter[0] += 1
    boot["sig"] = validate.sign(KEY, boot)
    r, reqs, out = run(json.dumps(boot))
    check("BOOT: no text", r["kind"] == "boot" and reqs == [], r)
    ref = {"v": 1, "id": "REF-S1", "type": "REF", "ctr": 1, "p": 98800}
    ref["sig"] = validate.sign(KEY, ref)
    r, reqs, out = run(json.dumps(ref))
    check("REF: no text", r["kind"] == "reference" and reqs == [], r)
    survey = {"v": 1, "id": "FOB-S1", "type": "SURVEY", "ctr": counter[0] + 1, "n": 0, "fix": 0, "sats": 0, "aps": []}
    counter[0] += 1
    survey["sig"] = validate.sign(KEY, survey)
    r, reqs, out = run(json.dumps(survey))
    check("SURVEY: no text", r["kind"] == "survey" and reqs == [], r)
    r, reqs, out = run(json.dumps(msg))
    check("duplicate: no text", r == {"ok": False, "reason": "duplicate"} and reqs == [], r)
    replay = dict(msg, bat=1)
    replay["sig"] = validate.sign(KEY, replay)
    r, reqs, out = run(json.dumps(replay))
    check("replay: no text", r["reason"] == "replay" and reqs == [], r)
    check("nothing was sent for any of those", len(Fake.requests) == before)

    # ---- one text per alert per number ----
    with contextlib.redirect_stdout(io.StringIO()):
        again = textbelt.send(r2["alert_id"], "SUSPICIOUS", "Test Student", "FOB-S1",
                              {"source": "none"}, time.time(), None, None)
    check("the same alert again: no second text to a number", again == "already" and len(Fake.requests) == before, again)

    # ---- long and non-plain names ----
    (r, reqs, out), _ = alert("MEDICAL", device="FOB-S2", lat=34.75, lon=-86.70, acc=12)
    m = reqs[0]["message"] if reqs else ""
    check("long name and GPS place still at most 160 characters", 0 < len(m) <= 160, len(m))
    check("plain characters only (one text)", all(32 <= ord(ch) < 127 for ch in m) and "Zoe" in m, m)

    # ---- failures never stop anything ----
    Fake.replies = [(200, {"success": False, "error": "Out of quota", "quotaRemaining": 0}),
                    (200, {"success": True, "quotaRemaining": 12, "textId": "999"})]
    acks, pushes_before = [], len(pushes)
    (r, reqs, out), _ = alert("MEDICAL", acks=acks)
    check("a refused text: the alert is saved and acked, Pushover still called",
          r["ok"] and len(acks) == 1 and len(pushes) == pushes_before + 1, r)
    check("one number refused, the other sent: result sent", r["sms"] == "sent", r)
    check("the refusal is logged with the last 2 digits",
          "[SMS failed] alert {} to ...01: refused: Out of quota".format(r["alert_id"]) in out, out)
    h = textbelt.health()
    check("Health: quota from the last reply (12) is low, orange under 25",
          h["quota_remaining"] == 12 and h["quota_low"], h)
    check("Health: last error kept", h["last_error"] == "refused: Out of quota", h)
    config.TEXTBELT_URL = "http://127.0.0.1:{}/text".format(free_port())     # nothing listens there
    acks = []
    (r, reqs, out), _ = alert("SILENT", acks=acks)
    check("no connection: alert saved and acked, result failed, no crash",
          r["ok"] and len(acks) == 1 and r["sms"] == "failed" and "no connection" in out, out)
    config.TEXTBELT_URL = url
    Fake.replies = [(500, {"success": False, "error": "server error"})] * 2
    (r, reqs, out), _ = alert("SILENT")
    check("an HTTP error is a failed text, never an exception", r["ok"] and r["sms"] == "failed", r)
    Fake.replies = []
    config.TEXTBELT_KEY = None
    (r, reqs, out), _ = alert("MEDICAL")
    check("live without a key: no request, failed, said plainly",
          reqs == [] and r["sms"] == "failed" and "TEXTBELT_KEY not set" in out, out)
    config.TEXTBELT_KEY = FAKE_TB_KEY

    # ---- the hourly cap ----
    tried = db.sms_count_since(time.time() - 3600)
    live(url, numbers=(NUM_A,), cap=tried + 2)
    results_cap = []
    outs = ""
    for _ in range(3):
        (r, reqs, out), _ = alert("MEDICAL")
        results_cap.append((r["sms"], len(reqs)))
        outs += out
    check("hourly cap: two more texts, then the third is not sent",
          results_cap == [("sent", 1), ("sent", 1), ("capped", 0)], results_cap)
    check("hitting the cap is logged", "hourly cap of {} texts reached".format(tried + 2) in outs, outs)
    check("Health counts the texts tried in the last hour", textbelt.health()["tried_last_hour"] == tried + 2)

    # ---- the serial bridge texts too ----
    live(url, numbers=(NUM_B,))
    counter[0] += 1
    lora = fake_fob.build_message("FOB-S1", KEY, "SUSPICIOUS", counter[0], device_ts=int(time.time()))
    before = len(Fake.requests)
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        r = serial_bridge.handle_line("SAFEPING_MSG " + json.dumps(lora))
    OUT.append(buf.getvalue())
    check("an alert from the serial bridge is texted", r["ok"] and r["sms"] == "sent"
          and len(Fake.requests) == before + 1, r)

    # ---- Health on the API ----
    import app
    today = time.strftime("%Y-%m-%d")
    stats = app.app.test_client().get("/api/stats?from={0}&to={0}".format(today)).get_json()
    check("/api/stats has the Text messages block", stats.get("sms", {}).get("mode") == "live"
          and "quota_remaining" in stats["sms"], stats.get("sms"))

    # ---- secrets ----
    everything = "".join(OUT)
    with db.connect() as c:
        dump = json.dumps([dict(x) for x in c.execute("SELECT * FROM sms_sent")] +
                          [dict(x) for x in c.execute("SELECT * FROM notify_status")])
    check("the Textbelt key is never printed", FAKE_TB_KEY not in everything)
    check("the key and full numbers are never stored", FAKE_TB_KEY not in dump and NUM_A not in dump and NUM_B not in dump)
    check("full numbers are never printed", NUM_A not in everything and NUM_B not in everything)

    # ---- announce ----
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        textbelt.announce()
    check("start line: live, numbers as last 2 digits, the cap",
          "[SMS] live through Textbelt. Numbers: ...02." in buf.getvalue(), buf.getvalue())
    server.shutdown()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
