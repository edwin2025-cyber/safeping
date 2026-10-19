// SafePing staff dashboard. Polls the server every few seconds and redraws.
(function () {
  "use strict";

  var POLL_MS = 3000;
  var LABELS = {
    SILENT: "SILENT ALERT",
    MEDICAL: "MEDICAL EMERGENCY",
    SUSPICIOUS: "SUSPICIOUS PERSON",
    STATUS: "STATUS CHECK"
  };
  var MARKER_COLORS = { SILENT: "#1f2a5c", MEDICAL: "#c62828", SUSPICIOUS: "#e0a800", STATUS: "#8a91a5" };

  var alertsEl = document.getElementById("alerts");
  var emptyEl = document.getElementById("empty");
  var countEl = document.getElementById("open-count");
  var linkPill = document.getElementById("pill-link");
  var refPill = document.getElementById("pill-ref");
  var mapNote = document.getElementById("map-note");
  var statusToggle = document.getElementById("show-status");

  var seenIds = null;          // alert ids already on screen, so only new ones pulse
  var markers = {};            // alert id -> Leaflet marker
  var map = null;
  var clockSkew = 0;           // server time minus browser time, in seconds

  // ---------- small helpers ----------
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
  function load(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;   // textContent, never innerHTML
    return node;
  }

  function ago(seconds) {
    seconds = Math.max(0, Math.round(seconds));
    if (seconds < 60) return seconds + " s ago";
    if (seconds < 3600) return Math.floor(seconds / 60) + " min ago";
    return Math.floor(seconds / 3600) + " h " + Math.floor((seconds % 3600) / 60) + " min ago";
  }

  function whereText(a) {
    if (a.latitude !== null && a.longitude !== null) {
      var text = "GPS " + a.latitude.toFixed(5) + ", " + a.longitude.toFixed(5);
      if (a.accuracy !== null) text += " (within " + a.accuracy + " m)";
      return text;
    }
    if (a.floor !== null) return "Floor " + a.floor;
    return "Location unknown";
  }

  // ---------- map ----------
  function setupMap() {
    var mapEl = document.getElementById("map");
    if (typeof L === "undefined") {
      mapNote.textContent = "Map could not load. Check the internet connection. Alerts still work.";
      return;
    }
    map = L.map(mapEl).setView([34.7304, -86.5861], 16);   // Huntsville, until an alert has GPS
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
  }

  function updateMarkers(alerts) {
    if (!map) return;
    var wanted = {};
    var points = [];
    alerts.forEach(function (a) {
      if (a.latitude === null || a.longitude === null) return;
      wanted[a.id] = true;
      var color = MARKER_COLORS[a.alert_type] || "#8a91a5";
      var latlng = [a.latitude, a.longitude];
      if (!markers[a.id]) {
        markers[a.id] = L.circleMarker(latlng, {
          radius: 10, color: "#ffffff", weight: 3, fillColor: color, fillOpacity: 1
        }).addTo(map);
      }
      markers[a.id].setStyle({ fillColor: color, opacity: a.acknowledged ? 0.5 : 1, fillOpacity: a.acknowledged ? 0.5 : 1 });
      markers[a.id].bindTooltip((a.student_name || a.device_id) + ": " + (LABELS[a.alert_type] || a.alert_type));
      if (!a.acknowledged) points.push(latlng);
    });
    Object.keys(markers).forEach(function (id) {
      if (!wanted[id]) { map.removeLayer(markers[id]); delete markers[id]; }
    });
    if (points.length && !map._userMoved) map.fitBounds(points, { maxZoom: 18, padding: [40, 40] });
    var floorOnly = alerts.filter(function (a) { return !a.acknowledged && a.latitude === null && a.floor !== null; }).length;
    mapNote.textContent = floorOnly ? floorOnly + " open alert(s) are indoors and show a floor, not a map point." : "";
  }

  // ---------- alert cards ----------
  function buildCard(a, nowServer, isNew) {
    var card = el("article", "card type-" + a.alert_type);
    card.classList.add(a.acknowledged ? "acked" : "open");
    if (isNew && !a.acknowledged) card.classList.add("fresh");
    card.dataset.id = a.id;

    var top = el("div", "card-top");
    top.appendChild(el("span", "type-label", LABELS[a.alert_type] || a.alert_type));
    top.appendChild(el("span", "age", ago(nowServer - a.timestamp)));
    card.appendChild(top);

    card.appendChild(el("div", "who", a.student_name || a.device_id));

    var meta = el("div", "meta");
    var where = el("span"); where.appendChild(el("strong", null, whereText(a)));
    meta.appendChild(where);
    meta.appendChild(el("span", null, "Device " + a.device_id));
    if (a.battery !== null) meta.appendChild(el("span", null, "Battery " + a.battery + "%"));
    card.appendChild(meta);

    var bottom = el("div", "card-bottom");
    if (a.acknowledged) {
      bottom.appendChild(el("span", "acked-text", "Acknowledged " + ago(nowServer - a.acknowledged_at)));
    } else {
      var btn = el("button", "ack-btn", "Acknowledge");
      btn.type = "button";
      btn.addEventListener("click", function (event) {
        event.stopPropagation();
        acknowledge(a.id, btn);
      });
      bottom.appendChild(btn);
    }
    if (a.alert_type !== "STATUS") {
      bottom.appendChild(el("span", a.sms_sent ? "sms" : "sms bad", a.sms_sent ? "Text sent" : "Text not sent"));
    }
    card.appendChild(bottom);

    card.addEventListener("click", function () {
      if (map && markers[a.id]) { map.setView(markers[a.id].getLatLng(), Math.max(map.getZoom(), 18)); }
    });
    return card;
  }

  function render(data) {
    var nowServer = Date.now() / 1000 + clockSkew;
    var alerts = data.alerts;
    var firstLoad = seenIds === null;
    if (firstLoad) seenIds = {};

    alertsEl.textContent = "";
    var open = 0;
    // Open alerts first (most urgent type first, then newest), then acknowledged ones.
    var sorted = alerts.slice().sort(function (x, y) {
      if (x.acknowledged !== y.acknowledged) return x.acknowledged ? 1 : -1;
      if (!x.acknowledged && x.priority !== y.priority) return x.priority - y.priority;
      return y.id - x.id;
    });
    sorted.forEach(function (a) {
      if (!a.acknowledged && a.alert_type !== "STATUS") open += 1;
      var isNew = !firstLoad && !seenIds[a.id];
      seenIds[a.id] = true;
      alertsEl.appendChild(buildCard(a, nowServer, isNew));
    });

    emptyEl.style.display = alerts.length ? "none" : "block";
    countEl.textContent = open + " open";
    document.title = (open ? "(" + open + ") " : "") + "SafePing Staff Dashboard";
    updateMarkers(alerts);
  }

  // ---------- talking to the server ----------
  function setLink(ok) {
    linkPill.textContent = ok ? "Connected" : "Connection problem";
    linkPill.className = "pill " + (ok ? "pill-ok" : "pill-warn");   // orange means connection issue
  }

  function fetchJson(url, options) {
    return fetch(url, options).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function refresh() {
    var status = statusToggle.checked ? "1" : "0";
    return fetchJson("/api/alerts?limit=100&status=" + status).then(function (data) {
      clockSkew = data.server_time - Date.now() / 1000;
      setLink(true);
      render(data);
    }).catch(function () { setLink(false); });
  }

  function refreshStatus() {
    return fetchJson("/api/status").then(function (s) {
      if (s.reference_age_s === null) {
        refPill.textContent = "Reference: no reading";
        refPill.className = "pill pill-muted";
      } else {
        refPill.textContent = "Reference: " + s.reference_age_s + " s ago";
        refPill.className = "pill " + (s.reference_age_s <= 60 ? "pill-ok" : "pill-warn");
      }
    }).catch(function () {});
  }

  function acknowledge(id, button) {
    button.disabled = true;
    fetchJson("/api/ack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id })
    }).then(refresh).catch(function () { button.disabled = false; setLink(false); });
  }

  // ---------- start ----------
  statusToggle.checked = load("showStatus") === "1";
  statusToggle.addEventListener("change", function () {
    store("showStatus", statusToggle.checked ? "1" : "0");
    refresh();
  });

  setupMap();
  if (map) map.on("dragstart zoomstart", function (e) { if (e.type === "dragstart") map._userMoved = true; });
  refresh();
  refreshStatus();
  setInterval(refresh, POLL_MS);
  setInterval(refreshStatus, 5000);
})();
