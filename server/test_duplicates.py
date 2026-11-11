"""The duplicate and replay rule (counter window) and the signed MQTT ack (message-format.md).

A Fob can send the same message more than once (WiFi, then LoRa, then its retry queue).
An identical copy of a saved message, of any age, is a "duplicate": not stored again,
logged as "duplicate", and acked again. A counter never seen before is accepted if it is
no more than COUNTER_WINDOW below the highest seen, with or without ts, even when a
higher counter got in first. A used counter with a different message, or a counter
below the window, is a "replay". Age never rejects: an old ts only tags the alert as
sent late. Runs against a throwaway database, so it never touches real data.

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
    check("lower unseen counter inside the window is accepted (no ts)", r.get("ok") and len(acks) == 1, str(r))

    # ---- identical copy long after: still a duplicate (no time window any more) ----
    late = t0 + 3600
    r, acks = send(first, now=late)
    check("identical copy 1 hour later is 'duplicate', acked again",
          r["reason"] == "duplicate" and len(acks) == 1, str(r))

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
    check("2 duplicates counted", by_reason.get("duplicate") == 2, str(by_reason))

    test_held_session(t0)
    test_out_of_order(t0)
    test_restart_and_prune(t0)
    test_persistent_client()
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


def link_of(alert_id):
    with db.connect() as c:
        return c.execute("SELECT link FROM alerts WHERE id = ?", (alert_id,)).fetchone()[0]


def test_held_session(t0):
    """The server keeps its MQTT session, so the broker holds WiFi alerts while the server
    is down and delivers them when it reconnects. Meanwhile the LoRa copy may already have
    reached the database through the serial bridge (a separate program)."""
    db.add_device("FOB-D2", "FOB", "Held Student", KEY)

    # LoRa copy first (bridge), then the held WiFi copy 5 minutes later
    a = fake_fob.build_message("FOB-D2", KEY, "MEDICAL", 30, battery=70)
    r, acks = send(a, now=t0, source="lora")
    check("held: LoRa copy saved first", r["ok"] and link_of(r["alert_id"]) == "lora")
    stored = alert_count()
    r, acks = send(a, now=t0 + 300, source="wifi")
    check("held: WiFi copy 5 min later is 'duplicate'", r["reason"] == "duplicate", str(r))
    check("held: not stored twice", alert_count() == stored)
    check("held: duplicate acked (harmless, the Fob has moved on)", len(acks) == 1)

    # WiFi first, then the LoRa copy (the normal "ack lost" case)
    b = fake_fob.build_message("FOB-D2", KEY, "SUSPICIOUS", 31, battery=70)
    r, acks = send(b, now=t0 + 400, source="wifi")
    check("WiFi then LoRa: WiFi copy saved and acked", r["ok"] and len(acks) == 1)
    r, acks = send(b, now=t0 + 402, source="lora")
    check("WiFi then LoRa: LoRa copy is 'duplicate'", r["reason"] == "duplicate", str(r))

    # The LoRa copy never reached the server (bridge off): the held WiFi copy is the alert
    c = fake_fob.build_message("FOB-D2", KEY, "SILENT", 32, battery=70)
    r, acks = send(c, now=t0 + 900, source="wifi")
    check("held: WiFi copy alone is accepted when it finally arrives", r["ok"] and len(acks) == 1, str(r))

    # The server was down more than 10 minutes and the bridge stored the LoRa copy:
    # the held WiFi copy is now a duplicate (it used to count as a replay).
    d = fake_fob.build_message("FOB-D2", KEY, "SUSPICIOUS", 33, battery=70)
    send(d, now=t0 + 1000, source="lora")
    r, acks = send(d, now=t0 + 1000 + 660, source="wifi")
    check("held over 10 min: 'duplicate', not a replay", r["reason"] == "duplicate" and len(acks) == 1, str(r))

    # NO ts (Fob clock never set): a newer alert got in first, then the older one arrives.
    # The counter window accepts it (this used to be a "replay").
    e_old = fake_fob.build_message("FOB-D2", KEY, "MEDICAL", 34, battery=70)
    e_new = fake_fob.build_message("FOB-D2", KEY, "STATUS", 35, battery=70)
    send(e_new, now=t0 + 2000, source="lora")
    r, acks = send(e_old, now=t0 + 2010, source="wifi")
    check("no ts, older than a newer accepted alert: accepted by the window",
          r.get("ok") and r["late"] is None and len(acks) == 1, str(r))


def security_events():
    """Rejections the dashboard shows in red."""
    with db.connect() as c:
        return [r[0] for r in c.execute(
            "SELECT reason FROM rejected WHERE reason IN ('replay', 'stale', 'bad_signature') ORDER BY id")]


def test_out_of_order(t0):
    """Part A: late but real alerts from the retry queue (all with ts)."""
    db.add_device("FOB-D3", "FOB", "Queue Student", KEY)
    now = t0 + 5000

    # ctr 50 failed both paths and waited in the queue. ctr 51 got through first.
    older = fake_fob.build_message("FOB-D3", KEY, "MEDICAL", 50, battery=60, device_ts=int(now - 300))
    newer = fake_fob.build_message("FOB-D3", KEY, "SUSPICIOUS", 51, battery=60, device_ts=int(now - 10))
    r, acks = send(newer, now=now, source="lora")
    check("out of order: newer alert accepted first", r["ok"], str(r))
    stored = alert_count()
    r, acks = send(older, now=now + 5, source="wifi")
    check("out of order: older real alert (5 min old) accepted after a newer one",
          r["ok"] and r["kind"] == "alert" and len(acks) == 1, str(r))
    check("out of order: it is stored", alert_count() == stored + 1)
    check("out of order: it is marked late (more than 60 s)", r.get("late") == "late", str(r))
    with db.connect() as c:
        last = c.execute("SELECT last_counter FROM devices WHERE device_id = 'FOB-D3'").fetchone()[0]
    check("out of order: last counter stays at the highest (51)", last == 51, str(last))

    # an exact old copy of ctr 50 is a duplicate, even much later
    events = len(security_events())
    r, acks = send(older, now=now + 4000, source="lora")
    check("old exact copy is 'duplicate' and acked", r["reason"] == "duplicate" and len(acks) == 1, str(r))
    check("old exact copy is not a security event", len(security_events()) == events)

    # a changed message (validly signed) with a used counter is a replay
    changed = fake_fob.build_message("FOB-D3", KEY, "SILENT", 50, battery=60, device_ts=int(now))
    r, acks = send(changed, now=now + 10)
    check("changed message with a used counter is 'replay', not acked",
          r["reason"] == "replay" and acks == [], str(r))
    check("replay is a security event", security_events()[-1:] == ["replay"], str(security_events()))

    # age never rejects: an alert 20 minutes old is accepted and tagged "over_max"
    stored = alert_count()
    events = len(security_events())
    old = fake_fob.build_message("FOB-D3", KEY, "MEDICAL", 49, battery=60, device_ts=int(now - 1200))
    r, acks = send(old, now=now + 20)
    check("20 min old alert is accepted and acked", r.get("ok") and len(acks) == 1, str(r))
    check("20 min old alert is tagged over 15 min", r["late"] == "over_max", str(r))
    check("20 min old alert is stored, not a security event",
          alert_count() == stored + 1 and len(security_events()) == events)
    edge = fake_fob.build_message("FOB-D3", KEY, "STATUS", 48, device_ts=int(now - config.MAX_ALERT_AGE_S + 30))
    r, acks = send(edge, now=now + 20)
    check("just under MAX_ALERT_AGE_S: accepted, plain 'late'", r.get("ok") and r["late"] == "late", str(r))
    ahead = fake_fob.build_message("FOB-D3", KEY, "STATUS", 52, device_ts=int(now + 3600))
    r, acks = send(ahead, now=now + 20)
    check("clock 1 hour ahead: accepted, not tagged", r.get("ok") and r["late"] is None, str(r))
    check("the Health count sees the over-15-min alert",
          db.count_late(now - 10, now + 30, config.MAX_ALERT_AGE_S) == 1)

    # the counter window: highest is 52 now
    inside = fake_fob.build_message("FOB-D3", KEY, "SUSPICIOUS", 52 - config.COUNTER_WINDOW, device_ts=int(now))
    r, acks = send(inside, now=now + 30)
    check("exactly COUNTER_WINDOW below the highest: accepted", r.get("ok"), str(r))
    below = fake_fob.build_message("FOB-D3", KEY, "SUSPICIOUS", 52 - config.COUNTER_WINDOW - 1, device_ts=int(now))
    r, acks = send(below, now=now + 30)
    check("one more below the window: 'replay', not acked", r["reason"] == "replay" and acks == [], str(r))
    check("below the window is a security event", security_events()[-1:] == ["replay"])
    check("a rejected counter is not claimed", db.seen_sig("FOB-D3", 52 - config.COUNTER_WINDOW - 1) is None)
    no_ts = fake_fob.build_message("FOB-D3", KEY, "SILENT", 52 - config.COUNTER_WINDOW - 2)
    r, acks = send(no_ts, now=now + 30)
    check("below the window without ts: 'replay' too", r["reason"] == "replay", str(r))
    jump = fake_fob.build_message("FOB-D3", KEY, "STATUS", 5000, device_ts=int(now))
    r, acks = send(jump, now=now + 31)
    check("a big jump up is accepted (counter file restored from the clock)", r.get("ok"), str(r))


def test_restart_and_prune(t0):
    """Seen counters live in the database, so the rule works after a server restart."""
    import importlib
    db.add_device("FOB-D4", "FOB", "Restart Student", KEY)
    now = t0 + 9000
    a = fake_fob.build_message("FOB-D4", KEY, "SUSPICIOUS", 70, device_ts=int(now))
    send(a, now=now)
    importlib.reload(db)
    importlib.reload(processor.validate)
    importlib.reload(processor)
    db.init_db()                                         # what app.py does at start
    r, acks = send(a, now=now + 60)
    check("after a restart: exact copy is still 'duplicate'", r["reason"] == "duplicate", str(r))
    b = fake_fob.build_message("FOB-D4", KEY, "SILENT", 69, device_ts=int(now + 50))
    r, acks = send(b, now=now + 60)
    check("after a restart: lower unseen counter with good ts accepted", r["ok"], str(r))

    # pruning never forgets a counter inside the window, so an old copy is still a duplicate
    cutoff = now + 8 * 86400 - config.SEEN_KEEP_DAYS * 86400
    db.prune_seen(cutoff)
    check("prune keeps counters inside the window", db.seen_sig("FOB-D4", 70) is not None
          and db.seen_sig("FOB-D4", 69) is not None)
    r, acks = send(a, now=now + 8 * 86400)
    check("an 8 day old exact copy inside the window is still 'duplicate'", r["reason"] == "duplicate", str(r))
    far = fake_fob.build_message("FOB-D4", KEY, "STATUS", 70 + config.COUNTER_WINDOW + 40, device_ts=int(now))
    send(far, now=now + 100)
    db.prune_seen(cutoff)
    check("prune removes old counters once they are below the window",
          db.seen_sig("FOB-D4", 70) is None and db.seen_sig("FOB-D4", 70 + config.COUNTER_WINDOW + 40) is not None)
    r, acks = send(a, now=now + 8 * 86400)
    check("after pruning, an old copy below the window is 'replay', never stored twice",
          r["reason"] == "replay", str(r))


def test_persistent_client():
    if mqtt_listener.mqtt is None:
        print("SKIP  persistent session checks (paho-mqtt not installed)")
        return
    client = mqtt_listener._make_client(config.MQTT_CLIENT_ID, clean_session=False)
    check("MQTT client id is fixed", getattr(client, "_client_id", b"") == b"safeping-server",
          str(getattr(client, "_client_id", None)))
    check("MQTT session is persistent (clean_session off)", getattr(client, "_clean_session", True) is False)


if __name__ == "__main__":
    sys.exit(main())
