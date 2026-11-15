"""The Reference board on the server (message-format.md, "Reference readings").

  - an alert with pressure stores the reference at its press time: interpolated between
    the two readings around it, the nearest within 60 s, or none
  - the Fob's sensor offset from sensor_offsets.json is stored with it, and the API
    gives the difference with the offset taken off, and meters
  - no floor is worked out from it (the old floor rule is unchanged)
  - /api/status, /api/devices and /api/reference show the readings
  - readings older than 14 days are deleted
  - REF is never acked, SURVEY is (topic rule)
Runs against a throwaway database.

  python test_reference.py"""
import json
import os
import tempfile
import time

_tmp = tempfile.mkdtemp()
os.environ["SAFEPING_DB"] = os.path.join(_tmp, "test.db")
os.environ["SAFEPING_SENSOR_OFFSETS"] = os.path.join(_tmp, "sensor_offsets.json")

import config         # noqa: E402
import db             # noqa: E402
import mqtt_listener  # noqa: E402  (puts firmware/lib on the path)
import msgsign        # noqa: E402
import processor      # noqa: E402
import refmatch       # noqa: E402
import validate       # noqa: E402

FOB_KEY = "a" * 32
REF_KEY = "b" * 32
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + str(detail) if detail and not passed else ""))


def ref_msg(ctr, ts, pd, t=2100):
    m = {"v": 1, "id": "REF-1", "type": "REF", "ctr": ctr, "ts": ts, "p": (pd + 5) // 10, "t": t,
         "pd": pd, "n": 15, "fw": "ref-test"}
    m["sig"] = msgsign.sign(REF_KEY, m)
    return json.dumps(m)


def alert(ctr, p, ts=None, kind="STATUS"):
    m = {"v": 1, "id": "FOB-1", "type": kind, "ctr": ctr, "p": p}
    if ts is not None:
        m["ts"] = ts
    m["sig"] = validate.sign(FOB_KEY, m)
    return json.dumps(m)


def stored(alert_id):
    return db.get_alert(alert_id)


def main():
    db.init_db()
    db.add_device("FOB-1", "FOB", "Test Student", FOB_KEY)
    db.add_device("REF-1", "REF", None, REF_KEY)
    processor.pushover.send = lambda *a, **k: None
    processor.textbelt.send = lambda *a, **k: "dry_run"
    now = int(time.time())

    check("REF topics are never acked", mqtt_listener.is_reference_topic("safeping/ref/REF-1")
          and mqtt_listener.is_reference_topic("safeping/reference"))
    check("survey and alert topics are acked", not mqtt_listener.is_reference_topic("safeping/survey/FOB-1")
          and not mqtt_listener.is_reference_topic("safeping/alert/FOB-1"))

    # readings at now-60 and now-30 (the middle of each window)
    r = processor.process(ref_msg(1, now - 60, 987500), now=now - 45)
    processor.process(ref_msg(2, now - 30, 987530), now=now - 15)
    check("REF accepted", r == {"ok": True, "kind": "reference"}, r)

    # ---- interpolated ----
    r = processor.process(alert(10, 98700, ts=now - 50), now=now)
    a = stored(r["alert_id"])
    check("alert between two readings: reference interpolated (98751.0)", a["ref_pressure"] == 98751.0, a["ref_pressure"])
    check("difference is alert minus reference", a["ref_diff"] == -51.0, a["ref_diff"])
    check("no offset file: no offset", a["ref_offset"] is None)
    # No new floor logic: the old rule (latest reading, PA_PER_FLOOR 42) gives what it gave before.
    check("floor is still the old rule's (1 + round(53 / 42) = 2)", a["floor"] == 2, a["floor"])

    # ---- nearest ----
    r = processor.process(alert(11, 98760, ts=now - 5), now=now)
    a = stored(r["alert_id"])
    check("only a reading before (25 s): the nearest one", a["ref_pressure"] == 98753.0, a["ref_pressure"])

    # ---- none ----
    r = processor.process(alert(12, 98760, ts=now - 300), now=now)
    a = stored(r["alert_id"])
    check("no reading within 60 s: nothing stored", a["ref_pressure"] is None and a["ref_diff"] is None, a)
    r = processor.process(alert(13, 98760), now=now - 20)
    a = stored(r["alert_id"])
    check("no ts: the arrival time is used (now-20: nearest is the now-30 reading)",
          a["ref_pressure"] == 98753.0, a["ref_pressure"])
    r = processor.process(alert(14, None, ts=now - 50), now=now)
    a = stored(r["alert_id"])
    check("no pressure: nothing stored", a["ref_pressure"] is None)

    # ---- the sensor offset ----
    with open(config.SENSOR_OFFSETS_PATH, "w", encoding="utf-8") as f:
        json.dump({"FOB-1": {"offset_pa": 3.2, "spread_pa": 0.8, "pairs": 20, "reference": "REF-1"}}, f)
    r = processor.process(alert(15, 98700, ts=now - 50, kind="MEDICAL"), now=now)
    a = stored(r["alert_id"])
    check("offset from sensor_offsets.json stored with the alert", a["ref_offset"] == 3.2, a["ref_offset"])
    check("height above the reference: -54.2 Pa is about 4.7 m up",
          4.5 < refmatch.height_m(-54.2, 98751.0, 2100) < 4.9, refmatch.height_m(-54.2, 98751.0, 2100))
    check("lower pressure is above, higher is below",
          refmatch.height_m(-10, 98800) > 0 > refmatch.height_m(10, 98800))
    with open(config.SENSOR_OFFSETS_PATH, "w", encoding="utf-8") as f:
        f.write("{not json")
    os.utime(config.SENSOR_OFFSETS_PATH, (time.time() + 5, time.time() + 5))
    check("a broken offsets file means no offsets (never stops an alert)", refmatch.offset_for("FOB-1") is None)

    # ---- the API ----
    import app
    client = app.app.test_client()
    alerts = client.get("/api/alerts?status=1&resolved=1&limit=50").get_json()["alerts"]
    med = [x for x in alerts if x["counter"] == 15][0]
    check("API: ref_pressure, raw difference and offset", med["ref_pressure"] == 98751.0 and med["ref_diff_pa"] == -51.0
          and med["ref_offset_pa"] == 3.2, med)
    check("API: difference with the offset taken off", med["ref_diff_adj_pa"] == -54.2, med["ref_diff_adj_pa"])
    check("API: meters above the reference", med["ref_height_m"] is not None and 4.4 < med["ref_height_m"] < 5.0,
          med["ref_height_m"])
    plain = [x for x in alerts if x["counter"] == 12][0]
    check("API: no reference gives nulls", plain["ref_pressure"] is None and plain["ref_height_m"] is None)
    check("API: raw columns not sent twice", "ref_diff" not in med and "ref_offset" not in med)

    status = client.get("/api/status").get_json()
    check("/api/status: pressure to one decimal and the board", status["reference_pressure"] == 98753.0
          and status["reference_id"] == "REF-1" and status["reference_temperature"] == 2100, status)
    check("/api/status: age from the newest reading", 10 <= status["reference_age_s"] <= 20, status["reference_age_s"])
    devices = client.get("/api/devices").get_json()["devices"]
    refdev = [d for d in devices if d["device_id"] == "REF-1"][0]
    check("/api/devices: the board's last reading", refdev["reference"] is not None
          and refdev["reference"]["pressure"] == 98753.0 and refdev["reference"]["samples"] == 15
          and refdev["reference"]["temperature"] == 2100 and refdev["reference"]["firmware"] == "ref-test", refdev)
    fobdev = [d for d in devices if d["device_id"] == "FOB-1"][0]
    check("/api/devices: Fobs have no reference block", fobdev["reference"] is None)
    readings = client.get("/api/reference?start={}&end={}".format(now - 3600, now + 60)).get_json()["readings"]
    check("/api/reference lists the readings with their time", len(readings) == 2
          and readings[0]["time"] == now - 60 and readings[0]["pressure"] == 98750.0, readings)
    bad = client.get("/api/reference?start=abc")
    check("/api/reference: bad range is a 400", bad.status_code == 400)

    # ---- 14 days ----
    old = now - int(15 * 86400)
    processor.process(ref_msg(3, old, 987000), now=old)
    with db.connect() as c:
        before = c.execute("SELECT COUNT(*) FROM reference_readings").fetchone()[0]
    processor._last_prune[0] = 0
    processor.process(ref_msg(4, now, 987540), now=now)
    with db.connect() as c:
        after = c.execute("SELECT COUNT(*) FROM reference_readings").fetchone()[0]
        oldest = c.execute("SELECT MIN(timestamp) FROM reference_readings").fetchone()[0]
    check("readings older than 14 days are deleted", before == 3 and after == 3 and oldest > now - 14 * 86400,
          (before, after))

    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
