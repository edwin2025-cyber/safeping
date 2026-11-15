"""Laptop test for tests/ref_calibrate.py and tests/survey_analyze.py on fake data.

A made-up walk with known answers: three buildings with known floor heights, the weather
moving the pressure by 40 Pa over the walk, a Fob sensor that reads 3.0 Pa high, sensor
noise, access points per building plus one campus-wide one, and marks and points that
should not match. The scripts must get the known answers back.

  python tests/test_survey_analyze.py"""
import contextlib
import io
import json
import math
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ref_calibrate   # noqa: E402
import survey_analyze  # noqa: E402
import surveydata      # noqa: E402

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print("{}  {}{}".format("PASS" if passed else "FAIL", name, "  " + str(detail) if detail and not passed else ""))


T0 = 1794754800                      # 2026-11-15, start of the fake walk
OFFSET = 3.0                         # the fake Fob reads 3.0 Pa high
TRUE = {
    "Residential": {0: -5.2, 1: -1.6, 2: 2.0, 3: 5.6},
    "Academic": {1: 0.0, 2: 3.9, 3: 7.8},
    "Sentinel Center": {0: -4.0, 1: 0.2, 2: 4.4},
}
APS = {"Residential": "aa", "Academic": "bb", "Sentinel Center": "cc"}


def weather(t):
    """The Reference board's pressure: 98800 Pa, 40 Pa rise over 2 hours, a small wave."""
    return 98800 + 40 * (t - T0) / 7200 + 1.5 * math.sin((t - T0) / 900)


def readings(start, end, noise=0.2, rnd=None):
    rnd = rnd or random.Random(1)
    out = []
    t = start
    while t <= end:
        out.append({"device_id": "REF-001", "received": t + 15, "time": t,
                    "pressure": round(weather(t) + rnd.gauss(0, noise), 1), "temperature": 2100,
                    "samples": 15, "firmware": "ref-test"})
        t += 30
    return out


def fob_pressure(t, h, rnd, noise=0.8):
    """What the Fob reads h meters above the reference (the inverse of height_m)."""
    ref = weather(t)
    p = ref * math.exp(-h * surveydata.refmatch.G / (surveydata.refmatch.R_DRY_AIR * (21.0 + 273.15)))
    return round(p + OFFSET + rnd.gauss(0, noise), 1)


def aps_for(building, rnd):
    own = APS[building]
    out = [{"bssid": "{}00000000{:02d}".format(own, i), "rssi": -45 - 6 * i + rnd.randint(-3, 3),
            "channel": 6, "ssid": "School"} for i in range(4)]
    out.append({"bssid": "dd0000000001", "rssi": -70 + rnd.randint(-4, 4), "channel": 36, "ssid": "Campus"})
    rnd.shuffle(out)
    return out


def make_walk(true=TRUE, seed=7):
    """(marks, points). Three marks per floor, 60 s apart. Each point is 0 to 25 s from
    its mark. Plus: a mark with no point, a point with no mark, and a pair 90 s apart."""
    rnd = random.Random(seed)
    marks, points = [], []
    t = T0
    ctr = 500
    for b in ["Residential", "Academic", "Sentinel Center"]:
        for f in sorted(true[b]):
            for spot in ("one end", "middle", "other end"):
                t += 60
                n = len(marks) + 1
                marks.append({"n": n, "building": b, "floor": f, "spot": "floor {} {}".format(f, spot), "t": float(t)})
                pt = t + rnd.randint(-25, 25)
                points.append({"device_id": "FOB-001", "counter": ctr, "received": pt + 2, "time": pt, "t": pt,
                               "pressure": fob_pressure(pt, true[b][f], rnd), "ref_pressure": None,
                               "aps": aps_for(b, rnd)})
                ctr += 1
            t += 120                                   # stairs
        t += 300                                       # walk to the next building
    t += 60
    marks.append({"n": len(marks) + 1, "building": "Academic", "floor": 2, "spot": "no point", "t": float(t)})
    t += 600
    points.append({"device_id": "FOB-001", "counter": ctr, "received": t, "time": t, "t": t,
                   "pressure": fob_pressure(t, 0.0, rnd), "ref_pressure": None, "aps": []})
    t += 600
    marks.append({"n": len(marks) + 1, "building": "Academic", "floor": 3, "spot": "too far", "t": float(t)})
    points.append({"device_id": "FOB-001", "counter": ctr + 1, "received": t + 90, "time": t + 90, "t": t + 90,
                   "pressure": fob_pressure(t + 90, 7.8, rnd), "ref_pressure": None, "aps": []})
    return marks, points


def phone_csv(marks, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("n,building,floor,spot,iso,epoch_ms,tz_offset_min\n")
        for m in marks:
            f.write('{},{},{},"{}",x,{},-360\n'.format(m["n"], m["building"], m["floor"], m["spot"], int(m["t"] * 1000)))


# ---------- surveydata ----------
def test_ref_at():
    rs = [{"time": 100, "pressure": 98800.0, "temperature": 2100}, {"time": 130, "pressure": 98803.0, "temperature": 2200}]
    check("ref_at: interpolated between two readings", abs(surveydata.ref_at(110, rs)[0] - 98801.0) < 1e-6)
    check("ref_at: temperature averaged", surveydata.ref_at(110, rs)[1] == 2150)
    check("ref_at: exactly on a reading", surveydata.ref_at(130, rs)[0] == 98803.0)
    check("ref_at: nearest within 60 s", surveydata.ref_at(180, rs)[0] == 98803.0)
    check("ref_at: nothing beyond 60 s", surveydata.ref_at(200, rs) is None and surveydata.ref_at(30, rs) is None)
    check("height_m is the server's formula (one source)", surveydata.height_m is surveydata.refmatch.height_m)


# ---------- ref_calibrate ----------
def test_calibrate():
    rnd = random.Random(3)
    start = T0 - 900
    refs = readings(start - 120, start + 720, rnd=rnd)
    points = []
    for i in range(20):                                # a point every 30 s for 10 minutes, side by side
        t = start + 15 + 30 * i + rnd.randint(-3, 3)
        points.append({"device_id": "FOB-001", "counter": 100 + i, "time": t, "t": t,
                       "pressure": round(weather(t) + OFFSET + rnd.gauss(0, 0.5), 1), "ref_pressure": None})
    r = ref_calibrate.calibrate(points, refs)
    check("calibrate: offset found (3.0 Pa)", abs(r["offset_pa"] - OFFSET) <= 0.3, r)
    check("calibrate: spread about the noise (0.5 Pa)", 0.2 < r["spread_pa"] < 1.0, r["spread_pa"])
    check("calibrate: 20 pairs", r["pairs"] == 20, r["pairs"])
    check("calibrate: weather drift taken out (no drift left)", abs(r["drift_pa_per_min"]) < 0.1, r["drift_pa_per_min"])
    check("calibrate: reference board named", r["reference"] == "REF-001")
    lines, warnings = ref_calibrate.report("FOB-001", r, 0)
    check("calibrate: no warnings on good data", warnings == [], warnings)
    check("calibrate: offset line", any("offset:       +3." in x or "offset:       +2.9" in x for x in lines), lines)

    few = ref_calibrate.calibrate(points[:3], refs)
    check("calibrate: too few pairs warns", any("pairs" in w for w in ref_calibrate.report("FOB-001", few, 0)[1]))
    moved = [dict(p, pressure=p["pressure"] + (6 if i % 2 else -6)) for i, p in enumerate(points)]
    check("calibrate: a big spread warns", any("spread" in w for w in ref_calibrate.report(
        "FOB-001", ref_calibrate.calibrate(moved, refs), 0)[1]))
    warming = [dict(p, pressure=p["pressure"] + 0.5 * i) for i, p in enumerate(points)]
    check("calibrate: drift warns", any("drifting" in w for w in ref_calibrate.report(
        "FOB-001", ref_calibrate.calibrate(warming, refs), 0)[1]))
    check("calibrate: no reference near the points gives None", ref_calibrate.calibrate(points, []) is None)

    # main() with files: dry run writes nothing, a real run merges with other Fobs
    work = tempfile.mkdtemp()
    pfile, rfile, out = (os.path.join(work, n) for n in ("p.json", "r.json", "offsets.json"))
    with open(pfile, "w") as f:
        json.dump({"points": points}, f)
    with open(rfile, "w") as f:
        json.dump({"readings": refs}, f)
    with open(out, "w") as f:
        json.dump({"FOB-002": {"offset_pa": -1.5}}, f)
    args = ["--device", "FOB-001", "--points", pfile, "--reference", rfile, "--out", out,
            "--start", str(start), "--minutes", "11"]
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        code = ref_calibrate.main(args + ["--dry-run"], settings=False)    # never the real safeping.env
    with open(out) as f:
        check("calibrate main: dry run saves nothing", code == 0 and "FOB-001" not in json.load(f), buf.getvalue())
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        code = ref_calibrate.main(args, settings=False)
    with open(out) as f:
        saved = json.load(f)
    check("calibrate main: saved, other Fobs kept", code == 0 and abs(saved["FOB-001"]["offset_pa"] - OFFSET) <= 0.3
          and saved["FOB-002"]["offset_pa"] == -1.5, saved)
    check("calibrate main: no .tmp left", not os.path.exists(out + ".tmp"))
    return out


# ---------- survey_analyze ----------
def test_analyze(offsets_path):
    marks, points = make_walk()
    refs = readings(T0 - 3600, T0 + 5 * 3600)
    ctx = survey_analyze.analyze(marks, points, refs, OFFSET, True, "FOB-001", "walk.csv")
    n_real = sum(len(f) for f in TRUE.values()) * 3
    check("join: every real mark matched", len(ctx["rows"]) == n_real, len(ctx["rows"]))
    check("join: the mark with no point is listed", any(m["spot"] == "no point" for m in ctx["lone_marks"]))
    check("join: the point with no mark is listed", len(ctx["lone_points"]) == 2, len(ctx["lone_points"]))
    check("join: a pair 90 s apart is not matched", any(m["spot"] == "too far" for m in ctx["lone_marks"]))
    check("join: every gap within 60 s", all(r["gap_s"] <= 60 for r in ctx["rows"]))

    worst = 0.0
    for b, floors in TRUE.items():
        for f, h in floors.items():
            got = ctx["table"][b][f]
            worst = max(worst, abs(got["mean"] - h))
            check("{} floor {}: 3 points, mean {:+.1f} m (true {:+.1f})".format(b, f, got["mean"], h),
                  got["n"] == 3 and abs(got["mean"] - h) < 0.3, got)
    check("weather drift and offset taken out (worst floor error under 0.3 m)", worst < 0.3, worst)
    gaps = {(g[0], g[1], g[2]): g for g in ctx["gaps"]}
    check("gaps: one row per pair of neighboring floors", len(ctx["gaps"]) == 3 + 2 + 2, len(ctx["gaps"]))
    g = gaps[("Academic", 1, 2)]
    check("gap Academic 1 to 2 about 3.9 m", abs(g[3] - 3.9) < 0.3, g)
    check("floors 3.5 m apart are told apart with margin", all(x[6].startswith("yes") for x in ctx["gaps"]),
          [x[6] for x in ctx["gaps"]])
    per, overall = ctx["wifi_check"]
    check("WiFi: strongest known AP points to the right building", overall[1] == n_real and overall[0] >= n_real - 1, overall)
    wf = ctx["wifi_floors"][("Academic", 2)]
    check("WiFi per floor: access points and networks", len(wf["bssids"]) == 5 and wf["ssids"][0][0] == "School", wf)

    # floors that cannot be told apart
    close = json.loads(json.dumps(TRUE))
    close = {b: {int(f): h for f, h in fl.items()} for b, fl in close.items()}
    close["Sentinel Center"][1] = -3.8
    m2, p2 = make_walk(close, seed=11)
    ctx2 = survey_analyze.analyze(m2, p2, refs, OFFSET, True)
    v = [x for x in ctx2["gaps"] if x[0] == "Sentinel Center" and x[1] == 0][0]
    check("floors 0.2 m apart: not told apart", v[6].startswith("no") or v[6].startswith("tight"), v)

    # no calibration: heights shifted, and the report says so
    ctx3 = survey_analyze.analyze(marks, points, refs, 0.0, False)
    shift = ctx3["table"]["Academic"][1]["mean"] - ctx["table"]["Academic"][1]["mean"]
    check("no offset: heights shifted by about -0.26 m", -0.35 < shift < -0.18, shift)
    check("no offset: the report says no calibration", "no calibration for this Fob" in survey_analyze.render(ctx3))

    # main() with files
    work = tempfile.mkdtemp()
    phone = os.path.join(work, "survey_test.csv")
    phone_csv(marks, phone)
    pfile, rfile, out = (os.path.join(work, n) for n in ("p.json", "r.json", "results.md"))
    with open(pfile, "w") as f:
        json.dump({"points": points}, f)
    with open(rfile, "w") as f:
        json.dump({"readings": refs}, f)
    with open(offsets_path, "w") as f:
        json.dump({"FOB-001": {"offset_pa": OFFSET}}, f)
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        code = survey_analyze.main(["--phone", phone, "--device", "FOB-001", "--points", pfile, "--reference", rfile,
                                    "--offsets", offsets_path, "--out", out], settings=False)
    check("analyze main: runs and writes the results file", code == 0 and os.path.isfile(out), buf.getvalue()[-300:])
    with open(out, encoding="utf-8") as f:
        md = f.read()
    for part in ("## Heights by building and floor", "### Residential", "## Neighboring floors", "## WiFi",
                 "## Every matched point", "## Not matched", "+3.0 Pa (from sensor_offsets.json)"):
        check("results file has: " + part, part in md)
    check("results file: no em dashes, no emojis", chr(0x2014) not in md and all(ord(c) < 0x2000 for c in md))
    phone_csv([dict(marks[0], spot="lobby, by the door")], phone)
    check("read_phone_csv: quoted spot with a comma", surveydata.read_phone_csv(phone)[0]["spot"] == "lobby, by the door")


def main():
    test_ref_at()
    offsets = test_calibrate()
    test_analyze(offsets)
    print()
    print("{} of {} checks passed".format(sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
