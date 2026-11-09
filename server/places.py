"""Named campus places. Turns a GPS point into words staff know,
like "Near the basketball courts" or "120 m NE of the front entrance".

The list lives in places.json (see docs/dashboard.md). The file is read again
whenever it changes, so there is no need to restart the server after editing it."""
import json
import math
import os
import threading

import config

MAX_DISTANCE_M = 200          # farther than this, the dashboard shows GPS accuracy instead
EARTH_RADIUS_M = 6371000
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

_lock = threading.Lock()
_cache = {"mtime": None, "places": []}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _read(path):
    try:
        with open(path, encoding="utf-8-sig") as f:      # -sig: Notepad may add a BOM
            data = json.load(f)
    except (OSError, ValueError) as error:
        print("[places] could not read {}: {}".format(path, error))
        return []
    if not isinstance(data, list):
        print("[places] {} must hold a list".format(path))
        return []
    places = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name, lat, lon = item.get("name"), item.get("lat"), item.get("lon")
        if not (isinstance(name, str) and name.strip() and _number(lat) and _number(lon)):
            print("[places] skipped a bad entry: {}".format(item))
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            print("[places] skipped an entry out of range: {}".format(item))
            continue
        places.append({"name": name.strip(), "lat": float(lat), "lon": float(lon)})
    return places


def load():
    """The list of places. Empty if the file is missing or broken."""
    path = config.PLACES_PATH
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    with _lock:
        if _cache["mtime"] != mtime:
            _cache["places"] = _read(path)
            _cache["mtime"] = mtime
        return _cache["places"]


def distance_m(lat1, lon1, lat2, lon2):
    """Haversine distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    """Compass direction (N, NE, E ...) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    degrees = (math.degrees(math.atan2(x, y)) + 360) % 360
    return COMPASS[int((degrees + 22.5) // 45) % 8]


def nearest(lat, lon):
    """(name, distance in m, direction from the place to the point) for the nearest
    place within MAX_DISTANCE_M, or None."""
    best = None
    for place in load():
        d = distance_m(place["lat"], place["lon"], lat, lon)
        if d <= MAX_DISTANCE_M and (best is None or d < best[1]):
            best = (place["name"], d, place)
    if best is None:
        return None
    name, d, place = best
    return name, round(d), bearing(place["lat"], place["lon"], lat, lon)


def describe(alert):
    """Adds place_name, place_distance_m and place_bearing to an alert dict (None when unknown)."""
    found = None
    if alert.get("latitude") is not None and alert.get("longitude") is not None:
        found = nearest(alert["latitude"], alert["longitude"])
    alert["place_name"], alert["place_distance_m"], alert["place_bearing"] = found or (None, None, None)
    return alert
