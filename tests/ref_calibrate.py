"""Side-by-side calibration: the fixed offset between a Fob's pressure sensor and the
Reference board's (runs on the LAPTOP).

Two BME280s never read exactly the same. With the Fob lying next to the Reference board
for 10 minutes, every difference (Fob minus Reference) is sensor offset, not height.
This script takes those survey points, finds the reference at each point's time (the
same interpolation the server uses), and saves the mean difference as the Fob's offset in
server/sensor_offsets.json. The server reads that file for each alert (no restart).

Before you run it
  * The Fob in survey mode, SURVEY_AUTO_MS = 30000 (a point every 30 s by itself), or
    press it once every 30 s. Fob and Reference board side by side, same height, for
    10 minutes. Do not hold the Fob (hand heat).
  * The server running with MQTT, so the points and readings reach it.

Run it (from the safeping folder), right after the 10 minutes:
  python tests/ref_calibrate.py --device FOB-001
      the last 10 minutes, from http://localhost:5000, writes server/sensor_offsets.json
  python tests/ref_calibrate.py --device FOB-001 --start "2026-11-15 14:00" --minutes 10
  python tests/ref_calibrate.py --device FOB-001 --dry-run          print only
  python tests/ref_calibrate.py --device FOB-001 --points p.json --reference r.json
      from files saved from /api/survey and /api/reference (no server needed)
Add --password if the dashboard has DASHBOARD_PASSWORD set.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import surveydata  # noqa: E402

DEFAULT_OUT = os.path.join(HERE, "..", "server", "sensor_offsets.json")
MIN_PAIRS = 5
SPREAD_WARN_PA = 2.0         # about 17 cm: more than this means the setup moved or warmed up
DRIFT_WARN_PA_PER_MIN = 0.2


def parse_time(text):
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp()     # local time, like the dashboard


def pairs_for(points, readings):
    """(time, fob Pa, ref Pa, diff Pa) for each point that has pressure and a reference."""
    out = []
    for p in points:
        if p.get("pressure") is None:
            continue
        ref = surveydata.ref_at(p["t"], readings)
        if ref is None and p.get("ref_pressure") is not None:
            ref = (p["ref_pressure"], None)
        if ref is None:
            continue
        out.append((p["t"], p["pressure"], ref[0], p["pressure"] - ref[0]))
    return out


def slope_per_min(pairs):
    """How fast the difference changes (Pa per minute): a Fob still warming up drifts."""
    if len(pairs) < 3:
        return 0.0
    ts = [(t - pairs[0][0]) / 60 for t, _, _, _ in pairs]
    ds = [d for _, _, _, d in pairs]
    mt, md = surveydata.mean(ts), surveydata.mean(ds)
    var = sum((t - mt) ** 2 for t in ts)
    return 0.0 if var == 0 else sum((t - mt) * (d - md) for t, d in zip(ts, ds)) / var


def calibrate(points, readings):
    """The offset and how much to trust it, or None with no pairs."""
    pairs = pairs_for(points, readings)
    if not pairs:
        return None
    diffs = [d for _, _, _, d in pairs]
    refs = sorted({r.get("device_id") for r in readings if r.get("device_id")})
    return {
        "offset_pa": round(surveydata.mean(diffs), 1),
        "spread_pa": round(surveydata.sd(diffs), 2),
        "pairs": len(pairs),
        "min_pa": round(min(diffs), 1),
        "max_pa": round(max(diffs), 1),
        "drift_pa_per_min": round(slope_per_min(pairs), 3),
        "reference": ", ".join(refs) or None,
        "from": datetime.fromtimestamp(pairs[0][0]).strftime("%Y-%m-%d %H:%M:%S"),
        "to": datetime.fromtimestamp(pairs[-1][0]).strftime("%Y-%m-%d %H:%M:%S"),
        "measured_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def save(path, device, result):
    """Merge into the file: other Fobs' offsets stay. Written through a .tmp file."""
    data = surveydata.load_offsets(path)
    data[device] = result
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def report(device, result, unmatched):
    lines = ["Calibration for {} against the Reference board ({})".format(device, result["reference"] or "unknown"),
             "  pairs:        {} ({} to {}){}".format(result["pairs"], result["from"], result["to"],
                                                    ", {} points had no reference within 60 s".format(unmatched) if unmatched else ""),
             "  offset:       {:+.1f} Pa (Fob minus Reference, mean)".format(result["offset_pa"]),
             "  spread:       {:.2f} Pa (standard deviation), min {:+.1f}, max {:+.1f}".format(
                 result["spread_pa"], result["min_pa"], result["max_pa"]),
             "  drift:        {:+.3f} Pa per minute".format(result["drift_pa_per_min"]),
             "  in meters:    the offset is about {:.2f} m, the spread about {:.2f} m".format(
                 abs(result["offset_pa"]) / 11.5, result["spread_pa"] / 11.5)]
    warnings = []
    if result["pairs"] < MIN_PAIRS:
        warnings.append("only {} pairs, {} or more needed".format(result["pairs"], MIN_PAIRS))
    if result["spread_pa"] > SPREAD_WARN_PA:
        warnings.append("spread over {} Pa: was the Fob moved, held, or next to a heater?".format(SPREAD_WARN_PA))
    if abs(result["drift_pa_per_min"]) > DRIFT_WARN_PA_PER_MIN:
        warnings.append("the difference is drifting: let the Fob sit 5 more minutes and run it again")
    return lines, warnings


def main(argv=None, settings=True):
    if settings:
        surveydata.load_settings()               # safeping.env (DASHBOARD_PASSWORD), names only printed
    ap = argparse.ArgumentParser(description="Fob vs Reference sensor offset (side by side)")
    ap.add_argument("--device", required=True, help="the Fob, for example FOB-001")
    ap.add_argument("--server", default="http://localhost:5000")
    ap.add_argument("--password", default=os.environ.get("DASHBOARD_PASSWORD"))
    ap.add_argument("--start", help='"YYYY-MM-DD HH:MM" (local) or Unix seconds. Default: --minutes before now')
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--points", help="JSON saved from /api/survey instead of the server")
    ap.add_argument("--reference", help="JSON saved from /api/reference instead of the server")
    ap.add_argument("--out", default=DEFAULT_OUT, help="offsets file (default server/sensor_offsets.json)")
    ap.add_argument("--dry-run", action="store_true", help="print, do not save")
    ap.add_argument("--force", action="store_true", help="save even with warnings")
    args = ap.parse_args(argv)

    start = parse_time(args.start)
    end = (start + args.minutes * 60) if start is not None else time.time()
    if start is None:
        start = end - args.minutes * 60
    try:
        points = surveydata.fetch_points(args.server, args.points, start, end, args.device, args.password)
        readings = surveydata.fetch_reference(args.server, args.reference, start, end, args.password)
    except OSError as error:
        print("Could not reach the server ({}). Is it running? Or use --points and --reference.".format(error))
        return 2
    print("{} survey points from {}, {} reference readings".format(len(points), args.device, len(readings)))
    result = calibrate(points, readings)
    if result is None:
        print("No pairs: no survey point had pressure and a reference reading within 60 s.")
        return 1
    lines, warnings = report(args.device, result, len([p for p in points if p.get("pressure") is not None]) - result["pairs"])
    print("\n".join(lines))
    for w in warnings:
        print("WARNING: " + w)
    if args.dry_run:
        print("Dry run: nothing saved.")
        return 0
    if warnings and not args.force:
        print("Not saved because of the warnings. Fix the setup and run again, or add --force.")
        return 1
    save(args.out, args.device, result)
    print("Saved to {} (the server reads it on the next alert).".format(os.path.normpath(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
