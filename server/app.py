"""Flask app: serves the dashboard and a small API.

Run it with:  python app.py
That also starts the MQTT listener (set NO_MQTT=1 to skip it)."""
import hmac
import os
import time

from flask import Flask, Response, jsonify, request, send_from_directory

import config
import db

app = Flask(__name__, static_folder="static", static_url_path="/static")

PRIORITY = {"SILENT": 1, "MEDICAL": 2, "SUSPICIOUS": 3, "STATUS": 9}


@app.before_request
def check_login():
    """Optional shared password. Set DASHBOARD_PASSWORD to turn it on."""
    if not config.DASHBOARD_PASSWORD:
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", config.DASHBOARD_PASSWORD):
        return None
    return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="SafePing"'})


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/alerts")
def api_alerts():
    limit = min(int(request.args.get("limit", 100)), 500)
    include_status = request.args.get("status") == "1"
    alerts = db.list_alerts(limit, include_status)
    for alert in alerts:
        alert["priority"] = PRIORITY.get(alert["alert_type"], 9)
        alert["acknowledged"] = bool(alert["acknowledged"])
        alert["sms_sent"] = bool(alert["sms_sent"])
    return jsonify({"server_time": time.time(), "alerts": alerts})


@app.route("/api/ack", methods=["POST"])
def api_ack():
    data = request.get_json(silent=True) or {}
    alert_id = data.get("id")
    if not isinstance(alert_id, int):
        return jsonify({"ok": False, "error": "id must be a whole number"}), 400
    changed = db.ack_alert(alert_id, time.time())
    return jsonify({"ok": True, "changed": changed})


@app.route("/api/status")
def api_status():
    ref = db.latest_reference()
    now = time.time()
    return jsonify({
        "server_time": now,
        "reference_age_s": None if ref is None else round(now - ref["timestamp"]),
        "reference_pressure": None if ref is None else ref["pressure"],
        "unacknowledged": db.count_unacknowledged(),
        "rejected_total": db.count_rejected(),
    })


if __name__ == "__main__":
    db.init_db()
    if os.environ.get("NO_MQTT") != "1":
        import mqtt_listener
        try:
            mqtt_listener.start()
        except RuntimeError as error:
            print("[warning] MQTT listener not started: {}".format(error))
    app.run(host=config.HOST, port=config.PORT, threaded=True)
