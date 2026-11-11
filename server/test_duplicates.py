"""The duplicate rule and the signed MQTT ack (message-format.md).

A Fob can send the same message twice (WiFi, then LoRa) if an ack is lost. An identical
copy within 10 minutes is a "duplicate": not stored again, logged as "duplicate", and
acked again. Anything else with an old counter stays a "replay". Runs against a
throwaway database, so it never touches real data.

  python test_duplicates.py"""
import json
import os
import sys
import tempfile
import time

# Use a temporary database. This must happen before config is imported.
_tmp = tempfile.mkdtemp()
os.environ["SAFEPING_DB"] = os.path.join(_tmp, "test.db")

import config         # noqa: E402
import db             # noqa: E402
import fake_fob       # noqa: E402
import mqtt_listener  # noqa: E402  (also puts firmware/lib on the path for ackcheck)
import ackcheck       # noqa: E402
import processor      # noqa: E402

KEY = "c" * 32
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


def alert_count():
    with db.connect() as c:
        return c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]


def rejected_reasons():
    with db.connect() as c:
        return [r[0] for r in c.execute("SELECT reason FROM rejected ORDER BY id")]


class Acks:
    def __init__(self):
        self.calls = []

    def __call__(self, device_id, ctr, sig):
        self.calls.append((device_id, ctr, sig))


def send(msg, now=None, source="wifi"):
    acks = Acks()
    r = processor.process(json.dumps(msg), now=now, source=source, on_ack=acks)
    return r, acks.calls


def main():
    db.init_db()
    db.add_device("FOB-D1", "FOB", "Test Student", KEY)
    db.add_device("REF-D1", "REF", None, "d" * 32)
    t0 = time.time()

    # ---- a new alert is saved and acked once ----
    first = fake_fob.build_message("FOB-D1", KEY, "SUSPICIOUS", 5, battery=80)
    r, acks = send(first, now=t0)
    check("new alert accepted", r["ok"] and r["kind"] == "alert")
    check("new alert acked once", acks == [("FOB-D1", 5, first["sig"])], str(acks))

    # ---- the identical message right away (MQTT, then LoRa) is a duplicate ----
    stored = alert_count()
    r, acks = send(first, now=t0 + 3, source="lora")
    check("immediate identical resend is 'duplicate'", r == {"ok": False, "reason": "duplicate"}, str(r))
    check("duplicate not stored again", alert_count() == stored, "alerts {}".format(alert_count()))
    check("duplicate logged as 'duplicate'", rejected_reasons()[-1:] == ["duplicate"], str(rejected_reasons()))
    check("duplicate acked again", acks == [("FOB-D1", 5, first["sig"])], str(acks))

    # ---- old counter, different signature: still a replay, never acked ----
    other = fake_fob.build_message("FOB-D1", KEY, "MEDICAL", 5, battery=80)    # same ctr, new content
    check("same counter, different signature", other["sig"] != first["sig"])
    r, acks = send(other, now=t0 + 5)
    check("old counter with a different signature is 'replay'", r["reason"] == "replay", str(r))
    check("replay not acked", acks == [], str(acks))

    lower = fake_fob.build_message("FOB-D1", KEY, "SILENT", 2, battery=80)     # below the last one
    r, acks = send(lower, now=t0 + 6)
    check("lower counter is 'replay'", r["reason"] == "replay" and acks == [], str(r))

    # ---- identical copy after the 10 minute window: replay ----
    late = t0 + config.DUPLICATE_WINDOW_S + 1
    r, acks = send(first, now=late)
    check("identical copy after 10 min is 'replay'", r["reason"] == "replay" and acks == [], str(r))

    # ---- a forged copy (same id and ctr, wrong key) is still bad_signature ----
    forged = fake_fob.build_message("FOB-D1", "wrong-key", "SUSPICIOUS", 5, battery=80)
    r, acks = send(forged, now=t0 + 7)
    check("forged copy is 'bad_signature', not acked", r["reason"] == "bad_signature" and acks == [], str(r))

    # ---- a changed copy (signature from the real alert, one field edited) ----
    changed = dict(first)
    changed["bat"] = 10
    r, acks = send(changed, now=t0 + 8)
    check("edited copy is 'bad_signature', not acked", r["reason"] == "bad_signature" and acks == [], str(r))

    # ---- Reference readings are never duplicates and never acked ----
    ref = fake_fob.build_message("REF-D1", "d" * 32, "REF", 1, pressure=101325)
    r, acks = send(ref, now=t0 + 9)
    check("Reference reading accepted, not acked", r["ok"] and acks == [], str(r))
    r, acks = send(ref, now=t0 + 10)
    check("identical Reference resend stays 'replay'", r["reason"] == "replay" and acks == [], str(r))

    # ---- the next real alert still works ----
    nxt = fake_fob.build_message("FOB-D1", KEY, "STATUS", 6, battery=80)
    r, acks = send(nxt, now=t0 + 11)
    check("next counter accepted and acked", r["ok"] and len(acks) == 1, str(r))

    # ---- the ack text is the one the Fob expects ----
    topic, text = mqtt_listener.ack_for("FOB-D1", 5, first["sig"])
    fob_side = ackcheck.ack_text(ackcheck.ack_key(KEY.encode()), "FOB-D1", 5, first["sig"])
    check("ack goes to safeping/ack/FOB-D1", topic == "safeping/ack/FOB-D1", topic)
    check("ack text matches the Fob's ackcheck", text == fob_side, text)
    other_ack = mqtt_listener.ack_for("FOB-D1", 5, other["sig"])[1]
    check("ack for a different signature does not match", other_ack != fob_side)

    # ---- counts for System health ----
    by_reason = db.rejected_by_reason(t0 - 1, late + 1)
    check("1 duplicate counted", by_reason.get("duplicate") == 1, str(by_reason))

    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
