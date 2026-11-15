"""Shared by tests/ref_calibrate.py and tests/survey_analyze.py (laptop only).

  fetch(...)            survey points and reference readings from the server's API,
                        or from JSON files saved from it (/api/survey, /api/reference)
  ref_at(t, readings)   the reference pressure at time t: the two readings around t
                        interpolated when both are within 60 s, else the nearest within
                        60 s, else None. The same rule as server/refmatch.py
  read_phone_csv(path)  the marks from range-logger/survey.html
  height_m(...)         from server/refmatch.py (one formula for the dashboard and here)
"""
import base64
import bisect
import csv
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(HERE, "..", "server")
if SERVER_DIR not in sys.path:
    sys.path.append(SERVER_DIR)
import envfile   # noqa: E402  (safeping.env, shared with the server)
import refmatch  # noqa: E402  (height_m; importing it opens no database)

height_m = refmatch.height_m


def load_settings():
    envfile.load()
MATCH_S = 60


def _get_json(url, password=None):
    req = urllib.request.Request(url)
    if password:
        token = base64.b64encode((":" + password).encode()).decode()
        req.add_header("Authorization", "Basic " + token)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_file(path, key):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data[key] if isinstance(data, dict) else data


def fetch_points(server=None, path=None, start=None, end=None, device=None, password=None):
    """Survey points as the /api/survey "points" list, oldest first."""
    if path:
        points = _load_file(path, "points")
    else:
        query = {"start": start, "end": end}
        if device:
            query["device"] = device
        points = _get_json(server.rstrip("/") + "/api/survey?" + urllib.parse.urlencode(query), password)["points"]
    out = []
    for p in points:
        if device and p.get("device_id") != device:
            continue
        t = p.get("time") or p.get("received")
        if start is not None and end is not None and not (start <= t < end):
            continue
        out.append(dict(p, t=t))
    out.sort(key=lambda p: p["t"])
    return out


def fetch_reference(server=None, path=None, start=None, end=None, password=None):
    """Reference readings as the /api/reference "readings" list, sorted by time."""
    if path:
        readings = _load_file(path, "readings")
    else:
        query = urllib.parse.urlencode({"start": start - 3600, "end": end + 3600})
        readings = _get_json(server.rstrip("/") + "/api/reference?" + query, password)["readings"]
    readings = [r for r in readings if r.get("pressure") is not None and r.get("time") is not None]
    readings.sort(key=lambda r: r["time"])
    return readings


def ref_at(t, readings, window_s=MATCH_S):
    """(pressure Pa, temperature hundredths or None) at time t, or None."""
    times = [r["time"] for r in readings]
    i = bisect.bisect_right(times, t)
    before = readings[i - 1] if i > 0 and t - readings[i - 1]["time"] <= window_s else None
    after = readings[i] if i < len(readings) and readings[i]["time"] - t <= window_s else None
    if before is not None and after is not None and after["time"] > before["time"]:
        f = (t - before["time"]) / (after["time"] - before["time"])
        p = before["pressure"] + f * (after["pressure"] - before["pressure"])
        temps = [r["temperature"] for r in (before, after) if r.get("temperature") is not None]
        return p, (sum(temps) / len(temps) if temps else None)
    row = before or after
    if row is None:
        return None
    return row["pressure"], row.get("temperature")


def read_phone_csv(path):
    """Marks from survey.html: n, building, floor, spot, iso, epoch_ms. Adds t (Unix s)."""
    marks = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                marks.append({"n": int(row["n"]), "building": row["building"].strip(), "floor": int(row["floor"]),
                              "spot": row.get("spot", "").strip(), "t": int(row["epoch_ms"]) / 1000.0})
            except (KeyError, ValueError):
                continue
    marks.sort(key=lambda m: m["t"])
    return marks


def load_offsets(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def sd(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
