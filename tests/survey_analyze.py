"""Floor survey analysis (runs on the LAPTOP).

Joins the Fob's survey points (from the server) with the phone's marks (the CSV from
range-logger/survey.html) by time, then for each point works out the height above the
Reference board:

    Fob pressure - Reference pressure at that time - the Fob's sensor offset
    -> meters (server/refmatch.height_m, about 11.5 Pa per meter)

and writes, per building:
  * a table by floor: mean, min, max and count (meters above the reference)
  * the gap between neighboring floors, and whether they can be told apart with margin
  * WiFi: the access points seen on each floor, and how often the strongest access point
    points to the right building (each point checked against the other points only)

The results go to docs/survey-results.md (and are printed).

Run it (from the safeping folder), with the server running:
  python tests/survey_analyze.py --phone survey_2026-11-15_1400.csv --device FOB-001
  python tests/survey_analyze.py --phone marks.csv --device FOB-001 --points p.json --reference r.json
      from files saved from /api/survey and /api/reference (no server needed)
Options: --offsets (default server/sensor_offsets.json), --join-s 60 (how far apart a
mark and a point may be), --margin-m 1.0 (gap needed to call two floors apart),
--out (default docs/survey-results.md), --password (DASHBOARD_PASSWORD).
"""
import argparse
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import surveydata  # noqa: E402

DEFAULT_OUT = os.path.join(HERE, "..", "docs", "survey-results.md")
DEFAULT_OFFSETS = os.path.join(HERE, "..", "server", "sensor_offsets.json")
BUILDING_ORDER = ["Residential", "Academic", "Sentinel Center"]
PAD_S = 1800                 # look for points this long before the first mark and after the last


def building_key(name):
    return (BUILDING_ORDER.index(name) if name in BUILDING_ORDER else len(BUILDING_ORDER), name)


# ---------- join ----------
def join(marks, points, join_s=60):
    """One point per mark: the closest pairs first, each within join_s seconds.
    Returns (matched [(mark, point, gap_s)], marks with no point, points with no mark)."""
    candidates = []
    for i, m in enumerate(marks):
        for j, p in enumerate(points):
            gap = abs(p["t"] - m["t"])
            if gap <= join_s:
                candidates.append((gap, i, j))
    candidates.sort()
    used_m, used_p, matched = set(), set(), []
    for gap, i, j in candidates:
        if i in used_m or j in used_p:
            continue
        used_m.add(i)
        used_p.add(j)
        matched.append((marks[i], points[j], gap))
    matched.sort(key=lambda x: x[0]["t"])
    return (matched, [m for i, m in enumerate(marks) if i not in used_m],
            [p for j, p in enumerate(points) if j not in used_p])


# ---------- heights ----------
def heights(matched, readings, offset_pa):
    """Adds the reference, the difference and the height to each matched pair.
    Returns rows; a point with no pressure or no reference is kept with height None."""
    rows = []
    for mark, p, gap in matched:
        row = {"building": mark["building"], "floor": mark["floor"], "spot": mark["spot"], "n": mark["n"],
               "t": p["t"], "gap_s": gap, "counter": p.get("counter"), "pressure": p.get("pressure"),
               "ref": None, "diff_pa": None, "height_m": None, "point": p, "why": None}
        if p.get("pressure") is None:
            row["why"] = "no pressure in the point"
        else:
            ref = surveydata.ref_at(p["t"], readings)
            if ref is None and p.get("ref_pressure") is not None:
                ref = (p["ref_pressure"], None)
            if ref is None:
                row["why"] = "no reference reading within 60 s"
            else:
                row["ref"] = ref[0]
                row["diff_pa"] = p["pressure"] - ref[0] - offset_pa
                row["height_m"] = surveydata.height_m(row["diff_pa"], ref[0], ref[1])
        rows.append(row)
    return rows


def floor_table(rows):
    """{building: {floor: {"n", "mean", "min", "max", "sd", "mean_pa"}}} from rows with a height."""
    out = {}
    for r in rows:
        if r["height_m"] is None:
            continue
        out.setdefault(r["building"], {}).setdefault(r["floor"], {"h": [], "pa": []})
        out[r["building"]][r["floor"]]["h"].append(r["height_m"])
        out[r["building"]][r["floor"]]["pa"].append(r["diff_pa"])
    table = {}
    for b, floors in out.items():
        table[b] = {}
        for f, v in floors.items():
            h = v["h"]
            table[b][f] = {"n": len(h), "mean": surveydata.mean(h), "min": min(h), "max": max(h),
                           "sd": surveydata.sd(h), "mean_pa": surveydata.mean(v["pa"])}
    return table


def floor_gaps(table, margin_m):
    """[(building, lower, upper, gap_m, clear_m, split_m, verdict)] for neighboring floors.
    gap = difference of the means. clear = the lowest point of the upper floor minus the
    highest point of the lower floor. split = halfway between them (a first threshold)."""
    out = []
    for b in sorted(table, key=building_key):
        floors = sorted(table[b])
        for lo, hi in zip(floors, floors[1:]):
            a, c = table[b][lo], table[b][hi]
            gap = c["mean"] - a["mean"]
            clear = c["min"] - a["max"]
            split = (c["min"] + a["max"]) / 2
            if clear >= margin_m:
                verdict = "yes, {:.1f} m clear".format(clear)
            elif clear > 0:
                verdict = "tight, only {:.1f} m clear".format(clear)
            else:
                verdict = "no, they overlap by {:.1f} m".format(-clear)
            out.append((b, lo, hi, gap, clear, split, verdict))
    return out


# ---------- WiFi ----------
def ap_buildings(rows):
    """{bssid: building where its mean signal is strongest} from the rows given."""
    seen = {}
    for r in rows:
        for ap in r["point"].get("aps") or []:
            seen.setdefault(ap["bssid"], {}).setdefault(r["building"], []).append(ap["rssi"])
    return {bssid: max(by, key=lambda b: surveydata.mean(by[b])) for bssid, by in seen.items()}


def wifi_check(rows):
    """Leave one out: for each point, the strongest of its access points that the OTHER
    points know says which building. Returns (per building {b: [right, total, unknown]},
    overall [right, total, unknown])."""
    per, overall = {}, [0, 0, 0]
    for i, r in enumerate(rows):
        aps = r["point"].get("aps") or []
        if not aps:
            continue
        known = ap_buildings(rows[:i] + rows[i + 1:])
        guess = None
        for ap in sorted(aps, key=lambda a: -a["rssi"]):
            if ap["bssid"] in known:
                guess = known[ap["bssid"]]
                break
        s = per.setdefault(r["building"], [0, 0, 0])
        for target in (s, overall):
            target[1] += 1
            if guess is None:
                target[2] += 1
            elif guess == r["building"]:
                target[0] += 1
    return per, overall


def wifi_floors(rows):
    """{(building, floor): {"points", "bssids", "ssids" [(name, count)], "strongest"}}."""
    out = {}
    for r in rows:
        key = (r["building"], r["floor"])
        e = out.setdefault(key, {"points": 0, "bssids": set(), "ssids": {}, "strongest": []})
        aps = r["point"].get("aps") or []
        e["points"] += 1
        for ap in aps:
            e["bssids"].add(ap["bssid"])
            name = ap["ssid"] or "(hidden)"
            e["ssids"][name] = e["ssids"].get(name, 0) + 1
        if aps:
            e["strongest"].append(max(ap["rssi"] for ap in aps))
    for e in out.values():
        e["ssids"] = sorted(e["ssids"].items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return out


# ---------- report ----------
def fmt_time(t):
    return datetime.fromtimestamp(t).strftime("%H:%M:%S")


def render(ctx):
    rows, table, gaps = ctx["rows"], ctx["table"], ctx["gaps"]
    L = ["# Floor survey results", ""]
    L.append("Made by `tests/survey_analyze.py` on {}. Do not edit by hand, run the script again.".format(
        datetime.now().strftime("%Y-%m-%d %H:%M")))
    L += ["", "## Setup", ""]
    L.append("| What | Value |")
    L.append("|---|---|")
    L.append("| Fob | {} |".format(ctx["device"] or "all"))
    L.append("| Phone marks | {} (`{}`) |".format(len(ctx["marks"]), os.path.basename(ctx["phone"])))
    L.append("| Survey points in the time range | {} |".format(len(ctx["points"])))
    L.append("| Matched (mark and point within {} s) | {} |".format(ctx["join_s"], len(rows)))
    L.append("| With a height | {} |".format(sum(1 for r in rows if r["height_m"] is not None)))
    L.append("| Reference readings | {} |".format(len(ctx["readings"])))
    L.append("| Sensor offset taken off | {} |".format(
        "{:+.1f} Pa (from sensor_offsets.json)".format(ctx["offset"]) if ctx["offset_found"]
        else "none (no calibration for this Fob, so heights may all be shifted)"))
    L.append("| Margin to call two floors apart | {:.1f} m |".format(ctx["margin_m"]))
    L += ["", "Heights are meters above the Reference board (academic building, floor 1). "
          "Negative means below it.", ""]

    L += ["## Heights by building and floor", ""]
    if not table:
        L.append("No point has a height yet.")
    for b in sorted(table, key=building_key):
        L += ["### {}".format(b), "", "| Floor | Points | Mean (m) | Min (m) | Max (m) | Spread (m) | Mean (Pa) |",
              "|---|---|---|---|---|---|---|"]
        for f in sorted(table[b]):
            v = table[b][f]
            L.append("| {} | {} | {:+.1f} | {:+.1f} | {:+.1f} | {:.1f} | {:+.1f} |".format(
                f, v["n"], v["mean"], v["min"], v["max"], v["sd"], v["mean_pa"]))
        L.append("")

    L += ["## Neighboring floors", ""]
    if gaps:
        L += ["Gap is the difference of the means. Clear is the lowest point of the upper floor minus the highest "
              "point of the lower floor. Split is halfway between those two, a first threshold for the floor table.", "",
              "| Building | Floors | Gap (m) | Clear (m) | Split at (m) | Told apart? |", "|---|---|---|---|---|---|"]
        for b, lo, hi, gap, clear, split, verdict in gaps:
            L.append("| {} | {} to {} | {:.1f} | {:+.1f} | {:+.1f} | {} |".format(b, lo, hi, gap, clear, split, verdict))
        L += ["", "With 3 points per floor this is a first look. A floor that is only just clear needs more points."]
    else:
        L.append("Not enough floors with a height to compare.")
    L.append("")

    L += ["## WiFi", ""]
    per, overall = ctx["wifi_check"]
    if overall[1]:
        L.append("Strongest known access point points to the right building: **{} of {}** points ({:.0f}%). "
                 "{} points heard no access point the other points knew.".format(
                     overall[0], overall[1], 100.0 * overall[0] / overall[1], overall[2]))
        L.append("Each point is checked against the other points only, so it never grades itself.")
        L += ["", "| Building | Right | Points | No known access point |", "|---|---|---|---|"]
        for b in sorted(per, key=building_key):
            s = per[b]
            L.append("| {} | {} | {} | {} |".format(b, s[0], s[1], s[2]))
    else:
        L.append("No WiFi scans in the matched points.")
    L += ["", "| Building | Floor | Points | Access points seen | Most seen networks | Strongest signal (median dBm) |",
          "|---|---|---|---|---|---|"]
    wf = ctx["wifi_floors"]
    for key in sorted(wf, key=lambda k: (building_key(k[0]), k[1])):
        e = wf[key]
        strongest = sorted(e["strongest"])
        med = strongest[len(strongest) // 2] if strongest else None
        L.append("| {} | {} | {} | {} | {} | {} |".format(
            key[0], key[1], e["points"], len(e["bssids"]),
            ", ".join("{} ({})".format(n, c) for n, c in e["ssids"]) or "none",
            "-" if med is None else med))
    L.append("")

    L += ["## Every matched point", "", "| Mark | Time | Building | Floor | Spot | Gap (s) | Fob (Pa) | Reference (Pa) | Height (m) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| {} | {} | {} | {} | {} | {:.0f} | {} | {} | {} |".format(
            r["n"], fmt_time(r["t"]), r["building"], r["floor"], r["spot"].replace("|", "/"), r["gap_s"],
            "-" if r["pressure"] is None else "{:.1f}".format(r["pressure"]),
            "-" if r["ref"] is None else "{:.1f}".format(r["ref"]),
            r["why"] if r["height_m"] is None else "{:+.1f}".format(r["height_m"])))
    L.append("")
    if ctx["lone_marks"] or ctx["lone_points"]:
        L += ["## Not matched", ""]
        for m in ctx["lone_marks"]:
            L.append("- Mark {} at {} ({}, floor {}, {}): no survey point within {} s".format(
                m["n"], fmt_time(m["t"]), m["building"], m["floor"], m["spot"], ctx["join_s"]))
        for p in ctx["lone_points"]:
            L.append("- Survey point ctr {} at {}: no mark within {} s".format(p.get("counter"), fmt_time(p["t"]), ctx["join_s"]))
        L.append("")
    return "\n".join(L)


def analyze(marks, points, readings, offset, offset_found, device=None, phone="", join_s=60, margin_m=1.0):
    matched, lone_marks, lone_points = join(marks, points, join_s)
    rows = heights(matched, readings, offset)
    table = floor_table(rows)
    ctx = {"device": device, "phone": phone, "marks": marks, "points": points, "readings": readings,
           "offset": offset, "offset_found": offset_found, "join_s": join_s, "margin_m": margin_m,
           "rows": rows, "table": table, "gaps": floor_gaps(table, margin_m), "lone_marks": lone_marks,
           "lone_points": lone_points, "wifi_check": wifi_check(rows), "wifi_floors": wifi_floors(rows)}
    return ctx


def main(argv=None, settings=True):
    if settings:
        surveydata.load_settings()               # safeping.env (DASHBOARD_PASSWORD), names only printed
    ap = argparse.ArgumentParser(description="Floor survey: Fob points + phone marks -> heights per floor")
    ap.add_argument("--phone", required=True, help="CSV from range-logger/survey.html")
    ap.add_argument("--device", help="the Fob, for example FOB-001")
    ap.add_argument("--server", default="http://localhost:5000")
    ap.add_argument("--password", default=os.environ.get("DASHBOARD_PASSWORD"))
    ap.add_argument("--points", help="JSON saved from /api/survey instead of the server")
    ap.add_argument("--reference", help="JSON saved from /api/reference instead of the server")
    ap.add_argument("--offsets", default=DEFAULT_OFFSETS)
    ap.add_argument("--join-s", type=float, default=60)
    ap.add_argument("--margin-m", type=float, default=1.0)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    marks = surveydata.read_phone_csv(args.phone)
    if not marks:
        print("No marks in", args.phone)
        return 1
    start, end = marks[0]["t"] - PAD_S, marks[-1]["t"] + PAD_S
    try:
        points = surveydata.fetch_points(args.server, args.points, start, end, args.device, args.password)
        readings = surveydata.fetch_reference(args.server, args.reference, start, end, args.password)
    except OSError as error:
        print("Could not reach the server ({}). Is it running? Or use --points and --reference.".format(error))
        return 2
    offsets = surveydata.load_offsets(args.offsets)
    entry = offsets.get(args.device) if args.device else None
    offset = float(entry["offset_pa"]) if entry else 0.0
    if not entry:
        print("WARNING: no sensor offset for {} in {}. Run tests/ref_calibrate.py first.".format(args.device, args.offsets))
    ctx = analyze(marks, points, readings, offset, entry is not None, args.device, args.phone, args.join_s, args.margin_m)
    text = render(ctx)
    print(text)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("\nWritten to", os.path.normpath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
