"""Numbers for the Overview page (/api/stats) and the CSV export (/api/export.csv).

Days and hours are in the time zone of the machine the server runs on.
STATUS check-ins are left out of every count except the per-type numbers and
the delivery counts (System health is about the radio path, and check-ins use it
too), the same way the Live page leaves them out of its open count. The CSV
export has every alert, STATUS included, with a Type column."""
import csv
import io
import re
import statistics
import time
from datetime import datetime, timedelta

import db
import places

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_DAYS = 366
TYPES = ("MEDICAL", "SUSPICIOUS", "SILENT", "STATUS")
LOW_BATTERY = 20              # percent; under this counts as low, like the Devices page
ACTIVE_S = 24 * 3600          # a Fob seen this recently counts as active
NEAR_M = 40                   # same rule as the dashboard: closer than this reads "Near ..."
HOTSPOT_TOP = 5               # Hotspots lists this many places, then "and N more places"
SHOWN_TYPES = ("MEDICAL", "SUSPICIOUS", "SILENT")   # the types Overview counts (STATUS left out)
URGENT_TYPES = ("MEDICAL", "SILENT")
RECENT_EVENTS = 10            # Recent activity on Overview shows this many events
MAX_POINTS = 2000             # at most this many GPS alerts on the Overview map, newest kept
EVENT_ORDER = {"received": 0, "acknowledged": 1, "resolved": 2}


class BadRange(ValueError):
    """The from or to date is missing or wrong. The message is safe to show."""


def parse_range(args):
    """(first day, last day) from ?from=YYYY-MM-DD&to=YYYY-MM-DD. Both days are included."""
    days = []
    for name in ("from", "to"):
        raw = args.get(name)
        if not raw:
            raise BadRange("from and to are required, like ?from=2026-11-02&to=2026-11-08")
        if not DATE_RE.match(raw):
            raise BadRange("{} must be a date like 2026-11-02".format(name))
        try:
            days.append(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            raise BadRange("{} is not a real date".format(name)) from None
    first, last = days
    if first > last:
        raise BadRange("from must be on or before to")
    if (last - first).days + 1 > MAX_DAYS:
        raise BadRange("the range can be at most {} days".format(MAX_DAYS))
    return first, last


def _midnight(day):
    """Unix time of local midnight at the start of this day."""
    return datetime(day.year, day.month, day.day).timestamp()


def _median(values):
    return statistics.median(values) if values else None


def _not_status(counts, key):
    """Sum of every type except STATUS for one day or hour."""
    return sum(n for (k, t), n in counts.items() if k == key and t != "STATUS")


def _by_type(counts, key):
    return {t: counts.get((key, t), 0) for t in TYPES}


def _hotspots(start, end):
    """Where alerts happen, STATUS left out. Alerts with GPS count for the nearest named
    place within 200 m (the same rule as the dashboard). The rest are grouped as
    "GPS, no named place", "Indoors, floor N" or "No location"."""
    counts = {}
    for lat, lon, floor in db.alert_locations(start, end):
        if lat is not None and lon is not None:
            found = places.nearest(lat, lon)
            key = (found[0][:1].upper() + found[0][1:], "place") if found else ("GPS, no named place", "gps")
        elif floor is not None:
            key = ("Indoors, floor {}".format(floor), "floor")
        else:
            key = ("No location", "none")
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0][0]))
    return {
        "places": [{"label": label, "kind": kind, "count": n} for (label, kind), n in ranked[:HOTSPOT_TOP]],
        "more_count": max(0, len(ranked) - HOTSPOT_TOP),
    }


def _place_short(lat, lon, floor):
    """Where, in a few words: the nearest named place within 200 m ("the bus loop"),
    "Indoors, floor 3", "GPS" when there is no named place close, or None."""
    if lat is not None and lon is not None:
        found = places.nearest(lat, lon)
        return found[0] if found else "GPS"
    if floor is not None:
        return "Indoors, floor {}".format(floor)
    return None


def _usual_per_day(per_day, today):
    """Median alerts per day (STATUS left out) over the days of the range before today.
    When the range has no such day (Today), the 7 days before today are used."""
    counts = [d["count"] for d in per_day if d["date"] < today.isoformat()]
    if not counts:
        week = db.count_by_day_and_type(_midnight(today - timedelta(days=7)), _midnight(today))
        counts = [_not_status(week, (today - timedelta(days=i)).isoformat()) for i in range(1, 8)]
    return _median(counts)


def _overview_v5(start, end, per_day, now):
    """Fields added in dashboard v5: open alerts by type, urgent open alerts, the last alert,
    today's count and the usual count, GPS points for the map, and Recent activity."""
    open_rows = db.open_alerts()
    today = datetime.fromtimestamp(now).date()
    today_counts = db.count_by_day_and_type(_midnight(today), _midnight(today + timedelta(days=1)))

    latest = db.latest_alert()
    last_alert = None
    if latest is not None:
        last_alert = {
            "id": latest["id"],
            "time": latest["timestamp"],
            "type": latest["alert_type"],
            "name": _device_name(latest),
            "place": _place_short(latest["latitude"], latest["longitude"], latest["floor"]),
        }

    points, indoor, events = [], 0, []
    for a in db.alert_events(start, end):
        name = _device_name(a)
        place = _place_short(a["latitude"], a["longitude"], a["floor"])
        base = {"alert_id": a["id"], "type": a["alert_type"], "name": name, "place": place}
        if start <= a["timestamp"] < end:
            if a["latitude"] is not None and a["longitude"] is not None:
                points.append({"id": a["id"], "type": a["alert_type"], "lat": a["latitude"], "lon": a["longitude"],
                               "name": name, "place": place, "time": a["timestamp"]})
            else:
                indoor += 1
            events.append(dict(base, kind="received", time=a["timestamp"]))
        ack, res = a["acknowledged_at"], a["resolved_at"]
        # Resolving an alert nobody acknowledged sets both times at once. Show only Resolved then.
        if ack is not None and start <= ack < end and ack != res:
            events.append(dict(base, kind="acknowledged", time=ack))
        if res is not None and start <= res < end:
            events.append(dict(base, kind="resolved", time=res))
    events.sort(key=lambda e: (e["time"], EVENT_ORDER[e["kind"]], e["alert_id"]), reverse=True)
    points.sort(key=lambda p: (p["time"], p["id"]))

    return {
        "open_by_type": {t: sum(1 for a in open_rows if a["alert_type"] == t) for t in SHOWN_TYPES},
        "urgent_open": [{"id": a["id"], "name": _device_name(a), "type": a["alert_type"]}
                        for a in open_rows if a["alert_type"] in URGENT_TYPES],
        "last_alert": last_alert,
        "today_count": _not_status(today_counts, today.isoformat()),
        "usual_per_day": _usual_per_day(per_day, today),
        "points": points[-MAX_POINTS:],
        "indoor_count": indoor,
        "recent_events": events[:RECENT_EVENTS],
    }


def build(first, last, now=None):
    """Everything the Overview page shows, in one answer."""
    now = time.time() if now is None else now
    n_days = (last - first).days + 1
    prev_first = first - timedelta(days=n_days)
    start, end = _midnight(first), _midnight(last + timedelta(days=1))
    prev_start = _midnight(prev_first)          # the previous period ends where this one starts

    days = [first + timedelta(days=i) for i in range(n_days)]
    prev_days = [prev_first + timedelta(days=i) for i in range(n_days)]
    cur = db.count_by_day_and_type(start, end)
    prev = db.count_by_day_and_type(prev_start, start)
    per_day = []
    for d, p in zip(days, prev_days):
        per_day.append({
            "date": d.isoformat(),
            "count": _not_status(cur, d.isoformat()),
            "by_type": _by_type(cur, d.isoformat()),
            "previous_date": p.isoformat(),
            "previous_count": _not_status(prev, p.isoformat()),
        })

    # One day: hourly buckets too, so the line charts have more than one point.
    per_hour = None
    if n_days == 1:
        cur_h = db.count_by_hour_and_type(start, end)
        prev_h = db.count_by_hour_and_type(prev_start, start)
        per_hour = [{
            "hour": h,
            "count": _not_status(cur_h, h),
            "by_type": _by_type(cur_h, h),
            "previous_count": _not_status(prev_h, h),
        } for h in range(24)]

    grid = [[0] * 24 for _ in range(7)]          # rows Monday to Sunday, columns hour 0 to 23
    for weekday, hour, n in db.count_by_weekday_hour(start, end):
        grid[(weekday + 6) % 7][hour] += n

    received, acknowledged, resolved = db.flow_counts(start, end)
    ack_s = db.ack_seconds(start, end)
    resolve_s = db.resolve_seconds(start, end)
    open_now, open_medical = db.count_open()

    ack_by_type = db.ack_seconds_by_type(start, end)

    fobs = [d for d in db.list_devices() if d["role"] != "REF"]
    seen = [d for d in fobs if d["last_seen"] is not None and now - d["last_seen"] <= ACTIVE_S]
    stale = [d for d in fobs if d not in seen]
    low = sorted((d for d in fobs if d["battery"] is not None and d["battery"] < LOW_BATTERY),
                 key=lambda d: d["battery"])
    by_reason = db.rejected_by_reason(start, end)
    ref = db.latest_reference()

    local_now = datetime.now().astimezone()
    result = {
        "server_time": now,
        "tz": local_now.tzname(),
        "tz_offset_min": int(local_now.utcoffset().total_seconds() // 60),
        "from": first.isoformat(),
        "to": last.isoformat(),
        "days": n_days,
        "previous_from": prev_first.isoformat(),
        "previous_to": (first - timedelta(days=1)).isoformat(),
        "total": sum(d["count"] for d in per_day),
        "previous_total": sum(d["previous_count"] for d in per_day),
        "per_day": per_day,
        "per_hour": per_hour,
        "weekday_hour": grid,
        "flow": {
            "received": received,
            "acknowledged": acknowledged,
            "resolved": resolved,
            "median_ack_s": _median(ack_s),
            "median_resolve_s": _median(resolve_s),
            "ack_timed": len(ack_s),
            "resolve_timed": len(resolve_s),
        },
        "open_now": open_now,
        "open_medical_now": open_medical,
        "fobs_active": len(seen),
        "fobs_total": len(fobs),
        "low_battery": len(low),
        # Added in dashboard v4. The per-day breakdown by type for the tooltip is per_day[].by_type.
        "median_ack_by_type": {t: _median(s) for t, s in ack_by_type.items() if s},
        "hotspots": _hotspots(start, end),
        "delivery": db.count_by_link(start, end),
        # The server cannot tell a Fob resending the same message from someone replaying it:
        # both fail the counter check and are counted under rejected as "replay". So
        # duplicates are not tracked on their own.
        "duplicates": None,
        "rejected": {"total": sum(by_reason.values()), "by_reason": by_reason},
        "stale_fobs": sorted(_device_name(d) for d in stale),
        "low_battery_fobs": [{"name": _device_name(d), "pct": d["battery"]} for d in low],
        "reference_age_s": None if ref is None else round(now - ref["timestamp"]),
    }
    result.update(_overview_v5(start, end, per_day, now))
    return result


def _device_name(device):
    return device["student_name"] or device["device_id"]


# ---------- CSV export ----------

CSV_COLUMNS = [
    "Received", "Type", "Student", "Fob ID", "Status", "Place", "Floor",
    "Latitude", "Longitude", "Accuracy (m)", "Battery (%)", "Link",
    "Acknowledged", "Resolved",
]
LINKS = {"lora": "LoRa", "wifi": "WiFi"}


def _local(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts is not None else ""


def _text(value):
    """A text cell. A leading = + - @ would make a spreadsheet run it as a formula."""
    if value is None:
        return ""
    value = str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _blank(value):
    """A number cell: empty when missing, and 15 rather than 15.0."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _place(alert):
    """The named place in words, the same way the dashboard says it. Empty when there is none."""
    name = alert.get("place_name")
    if not name:
        return ""
    d = alert["place_distance_m"]
    if d <= NEAR_M:
        return "Near " + name
    return "{} m {} of {}".format(int(round(d / 10.0) * 10), alert["place_bearing"], name)


def _status(alert):
    if alert["resolved"]:
        return "Resolved"
    return "Acknowledged" if alert["acknowledged"] else "Open"


def _coord(value):
    return "" if value is None else "{:.6f}".format(value)


def export_filename(first, last):
    return "safeping-alerts-{}-to-{}.csv".format(first.isoformat(), last.isoformat())


def export_csv(first, last):
    """Every alert in the range as CSV text, oldest first. Starts with a BOM so Excel reads UTF-8."""
    start, end = _midnight(first), _midnight(last + timedelta(days=1))
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")       # quotes commas, quotes and line breaks
    writer.writerow(CSV_COLUMNS)
    for alert in db.alerts_between(start, end):
        places.describe(alert)
        writer.writerow([
            _local(alert["timestamp"]),
            alert["alert_type"],
            _text(alert.get("student_name")),
            _text(alert["device_id"]),
            _status(alert),
            _text(_place(alert)),
            _blank(alert["floor"]),
            _coord(alert["latitude"]),
            _coord(alert["longitude"]),
            _blank(alert["accuracy"]),
            _blank(alert["battery"]),
            LINKS.get(alert.get("link"), ""),
            _local(alert["acknowledged_at"]),
            _local(alert.get("resolved_at")),
        ])
    return "﻿" + out.getvalue()
