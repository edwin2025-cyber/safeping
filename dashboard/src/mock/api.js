// Fake API for mock mode. src/lib/api.js loads this file only when Vite runs
// with --mode mock, so it is never part of a normal build.
// Answers have the same shape as the Flask routes in server/app.py.
import {
  MOCK_ALERTS,
  MOCK_CONFIG,
  MOCK_DEVICES,
  MOCK_PLACES,
  MOCK_PLACES_MAX_DISTANCE_M,
  MOCK_STATUS,
} from "./data.js";

const NEW_ALERT_MS = 45000;
const PRIORITY = { SILENT: 1, MEDICAL: 2, SUSPICIOUS: 3, STATUS: 9 };
const TYPES = Object.keys(PRIORITY);
const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const REF_PRESSURE = MOCK_STATUS.reference_pressure;

const now = () => Date.now() / 1000;
const counters = {};
let nextId = 1;

// ---------- places, same math as server/places.py ----------

function rad(d) {
  return (d * Math.PI) / 180;
}

function distanceM(lat1, lon1, lat2, lon2) {
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const a = Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(a));
}

function bearing(lat1, lon1, lat2, lon2) {
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const dl = rad(lon2 - lon1);
  const x = Math.sin(dl) * Math.cos(p2);
  const y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  const deg = ((Math.atan2(x, y) * 180) / Math.PI + 360) % 360;
  return COMPASS[Math.floor((deg + 22.5) / 45) % 8];
}

function describe(alert) {
  let best = null;
  if (alert.latitude !== null) {
    for (const p of MOCK_PLACES) {
      const d = distanceM(p.lat, p.lon, alert.latitude, alert.longitude);
      if (d <= MOCK_PLACES_MAX_DISTANCE_M && (!best || d < best.d)) best = { p, d };
    }
  }
  alert.place_name = best ? best.p.name : null;
  alert.place_distance_m = best ? Math.round(best.d) : null;
  alert.place_bearing = best ? bearing(best.p.lat, best.p.lon, alert.latitude, alert.longitude) : null;
  return alert;
}

// ---------- the in-memory alert list ----------

function makeAlert({ device, type, state, time, link, lat, lon, acc, floor }) {
  const dev = MOCK_DEVICES.find((d) => d.device_id === device);
  counters[device] = (counters[device] || 0) + 1;
  const hasGps = lat !== undefined;
  const indoors = !hasGps && floor !== undefined;
  const acked = state === "acknowledged" || state === "resolved";
  return describe({
    id: nextId++,
    device_id: device,
    student_name: dev.student_name,
    alert_type: type,
    priority: PRIORITY[type],
    timestamp: time,
    device_ts: Math.round(time),
    latitude: hasGps ? lat : null,
    longitude: hasGps ? lon : null,
    accuracy: hasGps ? acc : null,
    floor: indoors ? floor : null,
    pressure: indoors ? REF_PRESSURE - (floor - 1) * MOCK_CONFIG.pa_per_floor : REF_PRESSURE + 12,
    battery: dev.battery,
    temperature: 2150,
    counter: counters[device],
    link,
    acknowledged: acked,
    acknowledged_at: acked ? time + 60 : null,
    resolved: state === "resolved",
    resolved_at: state === "resolved" ? time + 600 : null,
    sms_sent: type !== "STATUS",
  });
}

const start = now();
const alerts = MOCK_ALERTS.slice()
  .sort((a, b) => b.minAgo - a.minAgo) // oldest first, so ids grow with time
  .map((a) => makeAlert({ ...a, time: start - a.minAgo * 60 }));

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function addRandomAlert() {
  const roll = Math.random();
  const where = {};
  if (roll < 0.6) {
    const p = pick(MOCK_PLACES);
    where.lat = p.lat + (Math.random() - 0.5) * 0.001;
    where.lon = p.lon + (Math.random() - 0.5) * 0.001;
    where.acc = 5 + Math.floor(Math.random() * 15);
  } else if (roll < 0.85) {
    where.floor = 1 + Math.floor(Math.random() * 4);
  }
  alerts.push(
    makeAlert({
      device: pick(MOCK_DEVICES).device_id,
      type: pick(TYPES),
      state: "open",
      time: now(),
      link: pick(["lora", "wifi"]),
      ...where,
    }),
  );
}

const timer = setInterval(addRandomAlert, NEW_ALERT_MS);
if (import.meta.hot) import.meta.hot.dispose(() => clearInterval(timer)); // one timer after a hot reload

// ---------- routes ----------

const copy = (a) => ({ ...a });
const newestFirst = (list) => list.slice().sort((a, b) => b.id - a.id);

function notFound() {
  throw new Error("HTTP 404");
}

function getAlerts(params) {
  const limit = Math.min(Number(params.get("limit") || 100), 500);
  const withStatus = params.get("status") === "1";
  const withResolved = params.get("resolved") === "1";
  const list = newestFirst(alerts)
    .filter((a) => (withStatus || a.alert_type !== "STATUS") && (withResolved || !a.resolved))
    .slice(0, limit)
    .map(copy);
  return { server_time: now(), alerts: list };
}

function getStatus() {
  const t = now();
  const lora = alerts.filter((a) => a.link === "lora").map((a) => a.timestamp);
  return {
    server_time: t,
    reference_age_s: MOCK_STATUS.reference_age_s,
    reference_pressure: MOCK_STATUS.reference_pressure,
    unacknowledged: alerts.filter((a) => !a.acknowledged && a.alert_type !== "STATUS").length,
    rejected_total: MOCK_STATUS.rejected_total,
    last_lora_age_s: lora.length ? Math.round(t - Math.max(...lora)) : null,
  };
}

function getDevices() {
  const devices = MOCK_DEVICES.map((d) => {
    const own = newestFirst(alerts.filter((a) => a.device_id === d.device_id));
    return {
      device_id: d.device_id,
      role: d.role,
      student_name: d.student_name,
      last_counter: own.length ? own[0].counter : null,
      last_seen: own.length ? own[0].timestamp : null,
      battery: own.length ? own[0].battery : null,
      link: own.length ? own[0].link : "unknown",
      open_alerts: own.filter((a) => !a.acknowledged && !a.resolved && a.alert_type !== "STATUS").length,
    };
  });
  return { server_time: now(), devices };
}

function getDeviceAlerts(deviceId) {
  if (!MOCK_DEVICES.some((d) => d.device_id === deviceId)) notFound();
  const list = newestFirst(alerts.filter((a) => a.device_id === deviceId)).slice(0, 200).map(copy);
  return { server_time: now(), alerts: list };
}

export async function mockGet(url) {
  const [path, query] = url.split("?");
  const params = new URLSearchParams(query || "");
  if (path === "/api/alerts") return getAlerts(params);
  if (path === "/api/status") return getStatus();
  if (path === "/api/config") return { ...MOCK_CONFIG };
  if (path === "/api/places") return { places: MOCK_PLACES.map((p) => ({ ...p })), max_distance_m: MOCK_PLACES_MAX_DISTANCE_M };
  if (path === "/api/devices") return getDevices();
  const m = path.match(/^\/api\/devices\/([^/]+)\/alerts$/);
  if (m) return getDeviceAlerts(decodeURIComponent(m[1]));
  return notFound();
}

export async function mockPost(url, body) {
  const id = body && body.id;
  if (!Number.isInteger(id)) throw new Error("HTTP 400");
  const alert = alerts.find((a) => a.id === id);
  const t = now();
  if (url === "/api/ack") {
    const changed = !!alert && !alert.acknowledged;
    if (changed) {
      alert.acknowledged = true;
      alert.acknowledged_at = t;
    }
    return { ok: true, changed };
  }
  if (url === "/api/resolve") {
    const changed = !!alert && !alert.resolved;
    if (changed) {
      alert.resolved = true;
      alert.resolved_at = t;
      if (!alert.acknowledged) {
        alert.acknowledged = true;
        alert.acknowledged_at = t;
      }
    }
    return { ok: true, changed };
  }
  return notFound();
}
