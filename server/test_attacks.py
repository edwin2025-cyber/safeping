"""DT-04: alert security.

Sends 10 forged, 10 replayed and 10 unknown-ID messages, plus one valid message,
and checks that none of the 30 bad ones are accepted, the valid one is, and every
rejection is logged. Runs against a throwaway database, so it never touches real data.

  python test_attacks.py"""
import os
import sys
import tempfile
import time

# Use a temporary database. This must happen before config is imported.
_tmp = tempfile.mkdtemp()
os.environ["SAFEPING_DB"] = os.path.join(_tmp, "test.db")

import db            # noqa: E402
import fake_fob      # noqa: E402
import processor     # noqa: E402
import validate      # noqa: E402

KEY = "a" * 32
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + detail if detail else ""))


def send(msg):
    import json
    return processor.process(json.dumps(msg))


def main():
    db.init_db()
    db.add_device("FOB-T1", "FOB", "Test Student", KEY)
    db.add_device("REF-T1", "REF", None, "b" * 32)

    # ---- the valid message ----
    good = fake_fob.build_message("FOB-T1", KEY, "SILENT", 0, lat=34.7304, lon=-86.5861,
                                  acc=8, battery=80, device_ts=int(time.time()))
    r = send(good)
    check("one valid message is accepted", r["ok"] and r["kind"] == "alert")

    # ---- 10 forged: right ID and format, signed with the wrong key ----
    accepted = 0
    for i in range(10):
        forged = fake_fob.build_message("FOB-T1", "wrong-key-" + str(i), "SILENT", 1000 + i, battery=80)
        accepted += send(forged)["ok"]
    check("10 forged alerts rejected", accepted == 0, "accepted {}".format(accepted))

    # ---- 10 replayed: the exact valid message again ----
    accepted = sum(send(good)["ok"] for _ in range(10))
    check("10 replayed alerts rejected", accepted == 0, "accepted {}".format(accepted))

    # ---- 10 unknown IDs: well formed and signed, but never registered ----
    accepted = 0
    for i in range(10):
        stranger = fake_fob.build_message("FOB-X{}".format(i), KEY, "MEDICAL", 0, battery=80)
        accepted += send(stranger)["ok"]
    check("10 unknown-ID alerts rejected", accepted == 0, "accepted {}".format(accepted))

    # ---- every rejection is logged ----
    check("all 30 rejections logged", db.count_rejected() == 30, "logged {}".format(db.count_rejected()))

    # ---- extra checks ----
    tampered = dict(fake_fob.build_message("FOB-T1", KEY, "SUSPICIOUS", 5, battery=80))
    tampered["type"] = "MEDICAL"          # changed after signing
    check("changed message rejected", send(tampered)["reason"] == "bad_signature")

    old = fake_fob.build_message("FOB-T1", KEY, "SUSPICIOUS", 0, battery=80)   # counter 0 again
    check("old counter rejected", send(old)["reason"] == "replay")

    wrong_role = fake_fob.build_message("FOB-T1", KEY, "REF", 6, pressure=101000)
    check("Fob pretending to be Reference rejected", send(wrong_role)["reason"] == "wrong_role")

    float_msg = {"v": 1, "id": "FOB-T1", "type": "SILENT", "ctr": 9, "lat": 34.7304, "lon": -86.5861}
    float_msg["sig"] = validate.sign(KEY, float_msg)
    check("decimal coordinates rejected", send(float_msg)["reason"] == "bad_format")

    check("garbage rejected", send_raw(b"not json at all")["reason"] == "bad_json")
    check("oversized payload rejected", send_raw(b"{" + b"x" * 600 + b"}")["reason"] == "bad_json")

    # A bad signature must not use up the counter (nobody can lock a device out).
    forged_high = fake_fob.build_message("FOB-T1", "nope", "SILENT", 50000, battery=80)
    send(forged_high)
    after = fake_fob.build_message("FOB-T1", KEY, "SUSPICIOUS", 7, battery=80)
    check("forged message does not lock out the real Fob", send(after)["ok"])

    # ---- location and texts ----
    ref = fake_fob.build_message("REF-T1", "b" * 32, "REF", 0, pressure=101325, temp=21.5)
    check("Reference reading accepted", send(ref)["ok"])
    upstairs = fake_fob.build_message("FOB-T1", KEY, "MEDICAL", 8, pressure=101325 - 84, battery=70)
    r = send(upstairs)
    check("pressure 84 Pa below Reference is floor 3", r["ok"] and r["floor"] == 3, "floor {}".format(r.get("floor")))
    status = fake_fob.build_message("FOB-T1", KEY, "STATUS", 9, battery=70)
    r = send(status)
    check("status check stored but no text", r["ok"] and r["sms"] is None)
    check("alert texts are sent (dry run counts)", r["ok"] and send(
        fake_fob.build_message("FOB-T1", KEY, "SILENT", 10, battery=70))["sms"] in ("dry_run", "sent"))

    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


def send_raw(payload):
    return processor.process(payload)


if __name__ == "__main__":
    sys.exit(main())
