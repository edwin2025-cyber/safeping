"""Flask app: serves the dashboard and a small API.

Run it with:  python app.py
That also starts the MQTT listener (set NO_MQTT=1 to skip it).

The dashboard is the React build in ../dashboard/dist when it exists.
If it does not exist, the old dashboard in server/static is served instead."""
import functools
import hmac
import os
import time

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import config
import db

app = Flask(__name__, static_folder="static", static_url_path="/static")

PRIORITY = {"SILENT": 1, "MEDICAL": 2, "SUSPICIOUS": 3, "STATUS": 9}

DIST_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "dashboard", "dist"))

CONFIG_DEFAULTS = {"sight_radius_m": 50, "camera_before_min": 2, "camera_after_min": 5}


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
    alerts = db.list_alerts(limit, include_status, include_resolved)
    for alert in alerts:
        alert["priority"] = PRIORITY.get(alert["alert_type"], 9)
        alert["acknowledged"] = bool(alert["acknowledged"])
        alert["sms_sent"] = bool(alert["sms_sent"])
        alert["resolved"] = bool(alert["resolved"])
    return jsonify({"server_time": time.time(), "alerts": alerts})


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
    })


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


if __name__ == "__main__":
    db.init_db()
    if os.environ.get("NO_MQTT") != "1":
        import mqtt_listener
        try:
            mqtt_listener.start()
        except RuntimeError as error:
            print("[warning] MQTT listener not started: {}".format(error))
    app.run(host=config.HOST, port=config.PORT, threaded=True)
