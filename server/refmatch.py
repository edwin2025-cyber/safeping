"""The Reference board's pressure at a given time, and the difference to a Fob's
(message-format.md, "Reference readings").

  reference_at(t)          the reference pressure at time t, or None
  for_pressure(id, t, p)   what an alert stores: ref_pressure, ref_diff, ref_offset
  offset_for(id)           the Fob's fixed sensor offset from sensor_offsets.json, or None
  height_m(diff, ref)      a pressure difference as meters above the reference

No floors are worked out here yet. That comes from the survey data.
"""
import json
import math
import os

import config
import db

R_DRY_AIR = 287.05       # J/(kg K)
G = 9.80665              # m/s^2
DEFAULT_TEMP_C = 15.0    # used when the reference has no temperature

_offsets_cache = {"path": None, "mtime": None, "data": {}}


def reading_pa(row):
    """A reference row's pressure in pascals, to one decimal when the board sent pd."""
    if row.get("pressure_dpa") is not None:
        return row["pressure_dpa"] / 10
    return float(row["pressure"])


def reference_at(t, window_s=None):
    """The reference pressure at time t (Unix seconds).

    The two readings around t (by the time each stands for), interpolated, when both are
    within window_s (REF_MATCH_S, 60 s). Otherwise the nearest one within window_s.
    Returns {"pressure": Pa, "temperature": hundredths of C or None, "time": t used,
    "how": "interpolated" or "nearest"} or None when there is no reading near t."""
    window_s = config.REF_MATCH_S if window_s is None else window_s
    before, after = db.reference_around(t, window_s)
    if before is None and after is None:
        return None
    if before is not None and after is not None and after["ref_time"] > before["ref_time"]:
        f = (t - before["ref_time"]) / (after["ref_time"] - before["ref_time"])
        pb, pa = reading_pa(before), reading_pa(after)
        temps = [r["temperature"] for r in (before, after) if r.get("temperature") is not None]
        return {"pressure": round(pb + f * (pa - pb), 1),
                "temperature": round(sum(temps) / len(temps)) if temps else None,
                "time": t, "how": "interpolated"}
    if before is not None and after is not None:
        row = before                                        # same reading on both sides
    elif before is not None:
        row = before
    else:
        row = after
    return {"pressure": round(reading_pa(row), 1), "temperature": row.get("temperature"),
            "time": row["ref_time"], "how": "nearest"}


def load_offsets(path=None):
    """{device_id: offset in Pa} from sensor_offsets.json. Read again only when the file
    changes. A missing or broken file means no offsets."""
    path = path or config.SENSOR_OFFSETS_PATH
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cache = _offsets_cache
    if cache["path"] == path and cache["mtime"] == mtime:
        return cache["data"]
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        for device_id, entry in raw.items():
            if isinstance(entry, dict) and isinstance(entry.get("offset_pa"), (int, float)):
                data[device_id] = float(entry["offset_pa"])
    except (OSError, ValueError, AttributeError) as error:
        print("[refmatch] sensor_offsets.json not read: {}".format(error))
        data = {}
    cache.update(path=path, mtime=mtime, data=data)
    return data


def offset_for(device_id):
    return load_offsets().get(device_id)


def height_m(diff_pa, ref_pa, temp_hundredths=None):
    """Meters above the reference for a pressure difference (Fob minus reference, Pa).
    Positive is above. The hypsometric formula with the reference temperature: about
    11.5 Pa per meter at 98.8 kPa and 20 C."""
    if diff_pa is None or ref_pa is None or ref_pa <= 0 or ref_pa + diff_pa <= 0:
        return None
    temp_c = DEFAULT_TEMP_C if temp_hundredths is None else temp_hundredths / 100
    return R_DRY_AIR * (temp_c + 273.15) / G * math.log(ref_pa / (ref_pa + diff_pa))


def for_pressure(device_id, t, pressure_pa):
    """What an alert with pressure stores. Never raises: a problem here must never stop
    an alert, so it gives None."""
    if pressure_pa is None:
        return None
    try:
        ref = reference_at(t)
        if ref is None:
            return None
        return {"ref_pressure": ref["pressure"],
                "ref_diff": round(pressure_pa - ref["pressure"], 1),
                "ref_offset": offset_for(device_id)}
    except Exception as error:
        print("[refmatch] reference not matched: {}".format(error))
        return None


def describe(ref_pressure, ref_diff, ref_offset, ref_temp=None):
    """The API fields for an alert: the difference with the offset taken off, and meters."""
    if ref_pressure is None or ref_diff is None:
        return {"ref_pressure": None, "ref_diff_pa": None, "ref_offset_pa": None,
                "ref_diff_adj_pa": None, "ref_height_m": None}
    adj = ref_diff - (ref_offset or 0.0)
    h = height_m(adj, ref_pressure, ref_temp)
    return {"ref_pressure": ref_pressure, "ref_diff_pa": ref_diff, "ref_offset_pa": ref_offset,
            "ref_diff_adj_pa": round(adj, 1), "ref_height_m": None if h is None else round(h, 1)}
