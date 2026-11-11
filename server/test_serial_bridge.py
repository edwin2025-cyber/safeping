"""The serial bridge reads the Relay's SAFEPING_MSG lines, also when the Relay put bytes
left over from an earlier print in front of the message.

Board test 2026-11-11 (logs/2026-11-11/152822_selfcheck_b4): a BOOT report over LoRa
(ctr 243) was acked by the Relay, but --forward gave bad_json. The Relay's line started
with 64 left-over bytes (the size of the board's USB serial buffer), then the real message.
Runs against a throwaway database, so it never touches real data.

  python test_serial_bridge.py"""
import json
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["SAFEPING_DB"] = os.path.join(_tmp, "test.db")

import db              # noqa: E402
import serial_bridge   # noqa: E402
import validate        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tests"))
import field_log       # noqa: E402

KEY = "e" * 32          # test key, not a real one

# The Relay line exactly as logged at 15:28:35.558 (after the "RELAY" column)
REAL_LINE = ('SAFEPING_MSG {"bat": 100, "type": "BOOT", "wifi": 0, "fail": 0, SAFEPING_MSG {"wifi": 0, '
             '"type": "BOOT", "fail": 0, "sig": "14f0df5041bd09caf4cb3879d48b0dcbb4bd8d2814b134229653af87987e0d41", '
             '"fw": "2026.11.11", "ctr": 243, "id": "FOB-001", "bat": 100, "v": 1}')
LEFTOVER = 'SAFEPING_MSG {"bat": 100, "type": "BOOT", "wifi": 0, "fail": 0, '

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


def main():
    db.init_db()
    db.add_device("FOB-001", "FOB", "Test Student", KEY)

    check("the left-over part is 64 bytes (the USB serial buffer)", len(LEFTOVER) == 64, str(len(LEFTOVER)))
    text = serial_bridge.message_text(REAL_LINE)
    msg = json.loads(text)
    check("bridge: the message after the last SAFEPING_MSG is valid JSON", msg["ctr"] == 243 and msg["type"] == "BOOT")

    # The real signature was made with the Fob's real key, which this test does not have.
    # So the real line must now get as far as the signature check: not bad_json any more.
    r = serial_bridge.handle_line(REAL_LINE)
    check("bridge: the real line is no longer bad_json (it reaches the signature check)",
          r == {"ok": False, "reason": "bad_signature"}, str(r))

    # The same message signed with the test key, behind the same left-over bytes: saved.
    resigned = {k: v for k, v in msg.items() if k != "sig"}
    resigned["sig"] = validate.sign(KEY, resigned)
    line = LEFTOVER + "SAFEPING_MSG " + json.dumps(resigned)
    r = serial_bridge.handle_line(line)
    check("bridge: a BOOT over LoRa behind left-over bytes is saved", r.get("ok") and r.get("kind") == "boot", str(r))
    boots = db.list_boots("FOB-001")
    check("bridge: stored as a boot report with link lora", len(boots) == 1 and boots[0]["link"] == "lora"
          and boots[0]["counter"] == 243, str(boots))

    # A normal line and other lines are unchanged
    alert = {"v": 1, "id": "FOB-001", "type": "SUSPICIOUS", "ctr": 244}
    alert["sig"] = validate.sign(KEY, alert)
    r = serial_bridge.handle_line("SAFEPING_MSG " + json.dumps(alert))
    check("bridge: a normal line still works", r.get("ok") and r.get("kind") == "alert", str(r))
    check("bridge: other Relay lines are ignored", serial_bridge.handle_line("  from FOB-001 type BOOT ctr 243") is None)

    # 2026-11-11 15:44:45 (crashtest): left-over bytes, then a plain Relay line
    broken = ('SAFEPING_MSG {"wifi": 1, "ctr": 246, "ts": 1794411525, "v": 1, '
              'ignored a packet that is not a SafePing alert')
    rejected_before = db.count_rejected()
    r = serial_bridge.handle_line(broken)
    check("bridge: left-over bytes + a plain line are not sent to the server", r is None, str(r))
    check("bridge: no bad_json in the rejected table for it", db.count_rejected() == rejected_before)
    check("bridge: a cut-off message alone is not sent either",
          serial_bridge.handle_line(LEFTOVER.strip()) is None)

    # The field logger reads the same line
    s = field_log.Session("t", os.path.join(_tmp, "x"))
    s.relay_line(1.0, REAL_LINE)
    s.relay_line(1.1, "  from FOB-001 type BOOT ctr 243 signal -43 dBm, snr 10.0".strip())
    check("logger: the Relay's BOOT ctr 243 is recorded", 243 in s.relay and s.relay[243]["rssi"] == -43, str(s.relay))
    check("logger: the left-over bytes are noted", any("left over" in n for n in s.notes), str(s.notes))

    # The logger's reset reason
    old = field_log.Session("t", os.path.join(_tmp, "y"))
    old.fob_line(0, "SELF_CHECK key=ok counter=ok lora=ok gps=ok battery=ok pressure=ok wifi=off fw=2026.11.11")
    new = field_log.Session("t", os.path.join(_tmp, "z"))
    new.fob_line(0, "SELF_CHECK key=ok counter=ok lora=ok gps=ok battery=ok pressure=ok wifi=off reset=crash fw=2026.11.11b")
    check("logger: new firmware shows the reset reason", "reset crash" in new.summary(1), new.summary(1))
    check("logger: old firmware says it does not report it, not '?'",
          "reset not reported (firmware before 2026.11.11b)" in old.summary(1))

    # The crashtest log: boot lines after an alert are not "LoRa had a problem"
    log = os.path.join(HERE, "..", "logs", "2026-11-11", "153933_crashtest", "2026-11-11_153933_crashtest_raw.txt")
    if os.path.isfile(log):
        s = field_log.Session("t", os.path.join(_tmp, "c"))
        with open(log, encoding="utf-8") as f:
            for raw in f:
                if raw.startswith("#") or len(raw) < 31:
                    continue
                src, text = raw[24:29].strip(), raw[30:].rstrip("\n")
                if src == "FOB":
                    s.fob_line(0, text)
                elif src == "RELAY":
                    s.relay_line(0, text)
        problems = sorted(c for c, f in s.fob.items() if f.get("retried"))
        check("crashtest log: no 'LoRa had a problem' (was ctr 248, 250, 252, 254)", problems == [], str(problems))
        check("crashtest log: 5 stopped BOOT reports, none sent later (old firmware)",
              "stopped by a press, not sent yet: 5" in s.summary(1)
              and "stopped by a press, sent later: 0" in s.summary(1), s.summary(1))
    else:
        print("SKIP  crashtest log not found")

    # New firmware: a stopped BOOT report that is sent later
    s = field_log.Session("t", os.path.join(_tmp, "n"))
    s.fob_line(0, 'SafePing Fob FOB-001 firmware 2026.11.11c')
    s.fob_line(0, 'SAFEPING_MSG {"v": 1, "id": "FOB-001", "type": "BOOT", "ctr": 300, "fail": 32, "sig": "x"}')
    s.fob_line(0, 'BOOT_STOPPED ctr=300 reason=button (sent after the press)')
    s.fob_line(0, 'SAFEPING_MSG {"v": 1, "id": "FOB-001", "type": "SUSPICIOUS", "ctr": 301, "sig": "y"}')
    s.fob_line(0, 'SEND_RESULT ctr=301 kind=SUSPICIOUS path=wifi result=confirmed ms=1400 reason=-')
    s.fob_line(0, 'BOOT_RESEND ctr=300 reason=stopped_by_press')
    s.fob_line(0, 'SEND_RESULT ctr=300 kind=BOOT path=wifi result=confirmed ms=300 reason=- resend=1')
    text = s.summary(1)
    check("logger: 'stopped by a press, sent later' counts the BOOT report",
          "stopped by a press, sent later: 1  (ctr 300)" in text and "Boot reports:                1 made, 1 confirmed" in text,
          text)

    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
