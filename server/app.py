"""Flask app: serves the dashboard and a small API.

Run it with:  python app.py
That also starts the MQTT listener (set NO_MQTT=1 to skip it).

The dashboard is the React build in ../dashboard/dist when it exists.
If it does not exist, the old dashboard in server/static is served instead."""
import functools
import hmac
import os
import subprocess
import time

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import config
import db
import places
import stats

app = Flask(__name__, static_folder="static", static_url_path="/static")

VERSION = "2.0"   # bump by hand when the server changes in a way people should know about

PRIORITY = {"SILENT": 1, "MEDICAL": 2, "SUSPICIOUS": 3, "STATUS": 9}

HERE = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.normpath(os.path.join(HERE, "..", "dashboard", "dist"))

CONFIG_DEFAULTS = {"sight_radius_m": 50, "camera_before_min": 2, "camera_after_min": 5}

SEARCH_ALERTS = 8     # alerts a search returns, newest first
SEARCH_RECENT = 5     # alerts an empty search returns (the newest)


def _git_commit():
    """Short commit the server runs from, for Settings > About. None without git."""
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                                capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


COMMIT = _git_commit()


def _alert_out(alert):
    """Shapes one alert row for the API: true/false flags, priority and the nearest place."""
    alert["priority"] = PRIORITY.get(alert["alert_type"], 9)
    alert["acknowledged"] = bool(alert["acknowledged"])
    alert["sms_sent"] = bool(alert["sms_sent"])
    alert["resolved"] = bool(alert["resolved"])
    return places.describe(alert)


@app.before_request
def check_login():
    """Optional shared password. Set DASHBOARD_PASSWORD to turn it on."""
    if not config.DASHBOARD_PASSWORD:
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", config.DASHBOARD_PASSWORD):
        return None
    return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="SafePing"'})


# ---------------------------------------------------------------------------
# Login and 2FA go here. Must be checked on the server, not only in the page.
#
# require_login wraps every /api/* route and every dashboard route. Right now it
# lets everything through. To add a real login, check the session here and
# return a 401 (for /api/*) or a redirect to the login page (for pages) when the
# user is not signed in. A check that only runs in the browser can be skipped by
# anyone who calls the API directly, so it has to live here.
# ---------------------------------------------------------------------------
def require_login(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        return view(*args, **kwargs)
    return wrapper


def _dist_ready():
    return os.path.isfile(os.path.join(DIST_DIR, "index.html"))


@app.route("/")
@require_login
def index():
    if _dist_ready():
        return send_from_directory(DIST_DIR, "index.html")
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:filename>")
@require_login
def dashboard_files(filename):
    """Files from the React build (assets, fonts). /api and /static match first."""
    if filename.startswith("api/") or not _dist_ready():
        abort(404)
    return send_from_directory(DIST_DIR, filename)


@app.route("/api/alerts")
@require_login
def api_alerts():
    limit = min(int(request.args.get("limit", 100)), 500)
    include_status = request.args.get("status") == "1"
    include_resolved = request.args.get("resolved") == "1"
    alerts = [_alert_out(a) for a in db.list_alerts(limit, include_status, include_resolved)]
    return jsonify({"server_time": time.time(), "alerts": alerts})


@app.route("/api/alerts/<int:alert_id>")
@require_login
def api_alert(alert_id):
    """One alert, in the same shape as /api/alerts. For opening an older alert from
    Overview or search. 404 when there is no such alert."""
    alert = db.get_alert(alert_id)
    if alert is None:
        return jsonify({"ok": False, "error": "unknown alert"}), 404
    return jsonify({"server_time": time.time(), "alert": _alert_out(alert)})


@app.route("/api/search")
@require_login
def api_search():
    """Find a student: Fobs and alerts whose student name or Fob ID contains q.
    An empty q gives every Fob and the 5 newest alerts. status=1 includes STATUS check-ins."""
    query = (request.args.get("q") or "").strip()[:100]
    include_status = request.args.get("status") == "1"
    needle = query.lower()
    students = []
    for device in db.list_devices():
        if device["role"] == "REF":
            continue
        name = device["student_name"] or ""
        if needle and needle not in name.lower() and needle not in device["device_id"].lower():
            continue
        last = db.last_alert_of(device["device_id"], include_status)
        students.append({
            "device_id": device["device_id"],
            "student_name": device["student_name"],
            "last_alert": None if last is None else {
                "id": last["id"], "type": last["alert_type"], "time": last["timestamp"]},
        })
    students.sort(key=lambda s: ((s["student_name"] or s["device_id"]).lower(), s["device_id"]))
    alerts = db.search_alerts(query, include_status, SEARCH_ALERTS if query else SEARCH_RECENT)
    return jsonify({
        "server_time": time.time(),
        "query": query,
        "students": students,
        "alerts": [_alert_out(a) for a in alerts],
    })


@app.route("/api/ack", methods=["POST"])
@require_login
def api_ack():
    data = request.get_json(silent=True) or {}
    alert_id = data.get("id")
    if not isinstance(alert_id, int):
        return jsonify({"ok": False, "error": "id must be a whole number"}), 400
    changed = db.ack_alert(alert_id, time.time())
    return jsonify({"ok": True, "changed": changed})


@app.route("/api/resolve", methods=["POST"])
@require_login
def api_resolve():
    data = request.get_json(silent=True) or {}
    alert_id = data.get("id")
    if not isinstance(alert_id, int):
        return jsonify({"ok": False, "error": "id must be a whole number"}), 400
    changed = db.resolve_alert(alert_id, time.time())
    return jsonify({"ok": True, "changed": changed})


@app.route("/api/status")
@require_login
def api_status():
    ref = db.latest_reference()
    now = time.time()
    last_lora = db.last_alert_time("lora")
    return jsonify({
        "server_time": now,
        "reference_age_s": None if ref is None else round(now - ref["timestamp"]),
        "reference_pressure": None if ref is None else ref["pressure"],
        "unacknowledged": db.count_unacknowledged(),
        "rejected_total": db.count_rejected(),
        "last_lora_age_s": None if last_lora is None else round(now - last_lora),
    })


@app.route("/api/config")
@require_login
def api_config():
    return jsonify({
        "carto_key": config.CARTO_KEY or None,
        "pa_per_floor": config.PA_PER_FLOOR,
        "ref_max_age_s": config.REF_MAX_AGE_S,
        "defaults": CONFIG_DEFAULTS,
        "version": VERSION,
        "commit": COMMIT,
    })


@app.route("/api/places")
@require_login
def api_places():
    """The named campus places from places.json. Read only."""
    return jsonify({"places": places.load(), "max_distance_m": places.MAX_DISTANCE_M})


@app.route("/api/devices")
@require_login
def api_devices():
    devices = db.list_devices()
    for device in devices:
        if device["last_counter"] is not None and device["last_counter"] < 0:
            device["last_counter"] = None     # -1 means nothing accepted yet
        if device["link"] is None:
            device["link"] = "unknown"
    return jsonify({"server_time": time.time(), "devices": devices})


@app.route("/api/devices/<device_id>/alerts")
@require_login
def api_device_alerts(device_id):
    """One device's alert history: all types and states, newest first, up to 200."""
    if db.get_device(device_id) is None:
        return jsonify({"ok": False, "error": "unknown device"}), 404
    alerts = [_alert_out(a) for a in db.list_device_alerts(device_id, 200)]
    return jsonify({"server_time": time.time(), "alerts": alerts})


@app.route("/api/stats")
@require_login
def api_stats():
    """Everything the Overview page shows. ?from=2026-11-02&to=2026-11-08, both days included."""
    try:
        first, last = stats.parse_range(request.args)
    except stats.BadRange as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify(stats.build(first, last))


@app.route("/api/export.csv")
@require_login
def api_export_csv():
    """Every alert in the range as a CSV download. Same from and to as /api/stats."""
    try:
        first, last = stats.parse_range(request.args)
    except stats.BadRange as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    name = stats.export_filename(first, last)
    return Response(
        stats.export_csv(first, last),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="{}"'.format(name), "Cache-Control": "no-store"},
    )


if __name__ == "__main__":
    db.init_db()
    if os.environ.get("NO_MQTT") != "1":
        import mqtt_listener
        try:
            mqtt_listener.start()
        except RuntimeError as error:
            print("[warning] MQTT listener not started: {}".format(error))
    app.run(host=config.HOST, port=config.PORT, threaded=True)
