// Fake API for mock mode. src/lib/api.js loads this file only when Vite runs
// with --mode mock, so it is never part of a normal build.
// Answers have the same shape as the Flask routes in server/app.py.
import {
  MOCK_ALERTS,
  MOCK_BOOTS,
  MOCK_CONFIG,
  MOCK_DEVICES,
  MOCK_DUPLICATES,
  MOCK_PLACES,
  MOCK_PLACES_MAX_DISTANCE_M,
  MOCK_REJECTIONS,
  MOCK_STATUS,
} from "./data.js";
import { addDays, dayCount, isoDay, parseDay } from "../lib/dates.js";

const NEW_ALERT_MS = 45000;
const HISTORY_DAYS = 60;
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

function makeAlert({ device, type, state, time, link, lat, lon, acc, floor, ackAfter = 60, resolveAfter = 540, lateS = 0 }) {
  const dev = MOCK_DEVICES.find((d) => d.device_id === device);
  counters[device] = (counters[device] || 0) + 1;
  const hasGps = lat !== undefined;
  const indoors = !hasGps && floor !== undefined;
  const acked = state === "acknowledged" || state === "resolved";
  const pressed = Math.round(time - lateS); // lateS: the Fob's retry queue sent it this much later
  return describe({
    id: nextId++,
    device_id: device,
    student_name: dev.student_name,
    alert_type: type,
    priority: PRIORITY[type],
    timestamp: time,
    device_ts: pressed,
    pressed_at: pressed,
    late_s: Math.round(time - pressed),
    sent_late: time - pressed > 60,
    late_over_max: time - pressed > 900,
    // Mock mode acts as if MQTT is on: acknowledging sends the help message
    help_sent_at: acked && type !== "STATUS" ? time + ackAfter : null,
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
    acknowledged_at: acked ? time + ackAfter : null,
    resolved: state === "resolved",
    resolved_at: state === "resolved" ? time + ackAfter + resolveAfter : null,
    sms_sent: type !== "STATUS",
  });
}

// ---------- 60 days of history for Overview ----------
// Seeded by the date, so a given day always has the same alerts.

function seeded(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 0 to 6 alerts a day, more on weekdays between 7 AM and 4 PM, mostly STATUS.
    All resolved, with acknowledge and resolve times. The last 4 hours are left
    to MOCK_ALERTS. */
function history(startS) {
  const out = [];
  const today = isoDay(new Date(startS * 1000));
  for (let back = HISTORY_DAYS; back >= 0; back--) {
    const day = addDays(today, -back);
    const midnight = parseDay(day).getTime() / 1000;
    const rand = seeded(Number(day.replaceAll("-", "")));
    const weekday = parseDay(day).getDay() % 6 !== 0;
    const n = weekday ? 1 + Math.floor(rand() * 6) : Math.floor(rand() * 3);
    for (let i = 0; i < n; i++) {
      const hour = weekday && rand() < 0.8 ? 7 + Math.floor(rand() * 9) : Math.floor(rand() * 24);
      const time = midnight + hour * 3600 + Math.floor(rand() * 3600);
      const r = rand();
      const type = r < 0.55 ? "STATUS" : r < 0.72 ? "MEDICAL" : r < 0.86 ? "SUSPICIOUS" : "SILENT";
      const where = {};
      const w = rand();
      if (w < 0.6) {
        const p = MOCK_PLACES[Math.floor(rand() * MOCK_PLACES.length)];
        where.lat = p.lat + (rand() - 0.5) * 0.001;
        where.lon = p.lon + (rand() - 0.5) * 0.001;
        where.acc = 5 + Math.floor(rand() * 15);
      } else if (w < 0.85) {
        where.floor = 1 + Math.floor(rand() * 4);
      }
      const alert = {
        device: MOCK_DEVICES[Math.floor(rand() * MOCK_DEVICES.length)].device_id,
        type,
        state: "resolved",
        time,
        link: rand() < 0.5 ? "lora" : "wifi",
        ackAfter: Math.round(30 + 270 * rand() ** 2),
        resolveAfter: Math.round(180 + 2400 * rand() ** 2),
        ...where,
      };
      if (time < startS - 4 * 3600) out.push(alert);
    }
  }
  return out.sort((a, b) => a.time - b.time);
}

const start = now();
const alerts = [
  ...history(start),
  ...MOCK_ALERTS.slice()
    .sort((a, b) => b.minAgo - a.minAgo)
    .map((a) => ({ ...a, time: start - a.minAgo * 60 })),
].map(makeAlert); // oldest first, so ids grow with time

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
      last_boot: d.role === "REF" ? null : bootsFor(d.device_id)[0] || null,
    };
  });
  return { server_time: now(), devices };
}

// Same words as RESET_WORDS in server/validate.py
const RESET_WORDS = {
  1: "Power on",
  2: "Restarted after a crash",
  3: "Restarted by the watchdog",
  4: "Woke from deep sleep",
  5: "Soft reset (Thonny or Ctrl+D)",
};

/** Boot reports, same shape as /api/devices/<id>/boots. Newest first, up to 10. */
function bootsFor(deviceId) {
  const plan = MOCK_BOOTS[deviceId] || [];
  return plan.map((b, i) => ({
    time: start - b.minAgo * 60,
    device_ts: Math.round(start - b.minAgo * 60),
    counter: 100 - i,
    all_passed: b.failed.length === 0,
    failed: b.failed.slice(),
    wifi: b.wifi,
    firmware: "2026.11.11b",
    link: b.wifi ? "wifi" : "lora",
    reset_cause: b.reset || 1,
    reset_words: RESET_WORDS[b.reset || 1],
    crashed: b.reset === 2,
  }));
}

function getDeviceBoots(deviceId) {
  if (!MOCK_DEVICES.some((d) => d.device_id === deviceId)) notFound();
  return { server_time: now(), boots: bootsFor(deviceId).slice(0, 10) };
}

function getDeviceAlerts(deviceId) {
  if (!MOCK_DEVICES.some((d) => d.device_id === deviceId)) notFound();
  const list = newestFirst(alerts.filter((a) => a.device_id === deviceId)).slice(0, 200).map(copy);
  return { server_time: now(), alerts: list };
}

/** Same as /api/alerts/<id> in server/app.py. */
function getAlert(id) {
  const alert = alerts.find((a) => a.id === id);
  if (!alert) notFound();
  return { server_time: now(), alert: copy(alert) };
}

/** Same rules as /api/search in server/app.py: Fobs and alerts whose student name or
    Fob ID contains q. An empty q gives every Fob and the 5 newest alerts. */
function search(params) {
  const q = (params.get("q") || "").trim().slice(0, 100);
  const withStatus = params.get("status") === "1";
  const needle = q.toLowerCase();
  const matches = (name, id) => !needle || (name || "").toLowerCase().includes(needle) || id.toLowerCase().includes(needle);
  const counted = (a) => withStatus || a.alert_type !== "STATUS";
  const students = MOCK_DEVICES.filter((d) => d.role !== "REF" && matches(d.student_name, d.device_id))
    .map((d) => {
      const last = newestFirst(alerts.filter((a) => a.device_id === d.device_id && counted(a)))[0];
      return {
        device_id: d.device_id,
        student_name: d.student_name,
        last_alert: last ? { id: last.id, type: last.alert_type, time: last.timestamp } : null,
      };
    })
    .sort((x, y) => (x.student_name || x.device_id).toLowerCase().localeCompare((y.student_name || y.device_id).toLowerCase()));
  const list = newestFirst(alerts)
    .filter((a) => counted(a) && matches(a.student_name, a.device_id))
    .slice(0, q ? 8 : 5)
    .map(copy);
  return { server_time: now(), query: q, students, alerts: list };
}

// ---------- Overview numbers and CSV, same rules as server/stats.py ----------

const TYPE_ORDER = ["MEDICAL", "SUSPICIOUS", "SILENT", "STATUS"];
const notStatus = (a) => a.alert_type !== "STATUS";
const startOfDay = (iso) => parseDay(iso).getTime() / 1000;

function badRequest() {
  throw new Error("HTTP 400");
}

function parseRange(from, to) {
  if (!parseDay(from) || !parseDay(to) || from > to || dayCount(from, to) > 366) badRequest();
  return [from, to];
}

function median(values) {
  if (!values.length) return null;
  const s = values.slice().sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function byType(list) {
  return Object.fromEntries(TYPE_ORDER.map((t) => [t, list.filter((a) => a.alert_type === t).length]));
}

function between(startS, endS) {
  return alerts.filter((a) => a.timestamp >= startS && a.timestamp < endS);
}

function getStats(params) {
  const [from, to] = parseRange(params.get("from"), params.get("to"));
  const days = dayCount(from, to);
  const prevFrom = addDays(from, -days);
  const startS = startOfDay(from);
  const endS = startOfDay(addDays(to, 1));
  const cur = between(startS, endS);
  const prev = between(startOfDay(prevFrom), startS);
  const dayOf = (a) => isoDay(new Date(a.timestamp * 1000));
  const hourOf = (a) => new Date(a.timestamp * 1000).getHours();

  const perDay = [];
  for (let i = 0; i < days; i++) {
    const d = addDays(from, i);
    const p = addDays(prevFrom, i);
    const today = cur.filter((a) => dayOf(a) === d);
    perDay.push({
      date: d,
      count: today.filter(notStatus).length,
      by_type: byType(today),
      previous_date: p,
      previous_count: prev.filter((a) => dayOf(a) === p && notStatus(a)).length,
    });
  }
  const perHour =
    days === 1
      ? Array.from({ length: 24 }, (_, h) => {
          const inHour = cur.filter((a) => hourOf(a) === h);
          return {
            hour: h,
            count: inHour.filter(notStatus).length,
            by_type: byType(inHour),
            previous_count: prev.filter((a) => hourOf(a) === h && notStatus(a)).length,
          };
        })
      : null;

  const grid = Array.from({ length: 7 }, () => Array(24).fill(0)); // Monday first
  const counted = cur.filter(notStatus);
  counted.forEach((a) => {
    const d = new Date(a.timestamp * 1000);
    grid[(d.getDay() + 6) % 7][d.getHours()] += 1;
  });
  const ackS = counted.filter((a) => a.acknowledged && a.acknowledged_at !== null).map((a) => Math.max(0, a.acknowledged_at - a.timestamp));
  const resolveS = counted
    .filter((a) => a.resolved && a.resolved_at !== null && a.acknowledged_at !== null)
    .map((a) => Math.max(0, a.resolved_at - a.acknowledged_at));
  const open = alerts.filter((a) => !a.acknowledged && !a.resolved && notStatus(a));
  const t = now();
  const fobs = getDevices().devices.filter((d) => d.role !== "REF");
  const seen = fobs.filter((d) => d.last_seen !== null && t - d.last_seen <= 86400);
  const low = fobs.filter((d) => d.battery !== null && d.battery < 20).sort((x, y) => x.battery - y.battery);
  const name = (d) => d.student_name || d.device_id;

  const ackByType = {};
  counted
    .filter((a) => a.acknowledged && a.acknowledged_at !== null)
    .forEach((a) => (ackByType[a.alert_type] = ackByType[a.alert_type] || []).push(Math.max(0, a.acknowledged_at - a.timestamp)));

  const inRange = (minAgo) => {
    const ts = start - minAgo * 60;
    return ts >= startS && ts < endS;
  };
  const byReason = {};
  MOCK_REJECTIONS.filter((r) => inRange(r.minAgo)).forEach((r) => (byReason[r.reason] = (byReason[r.reason] || 0) + 1));

  const delivery = { lora: 0, wifi: 0, unknown: 0 };
  cur.forEach((a) => (delivery[a.link === "lora" || a.link === "wifi" ? a.link : "unknown"] += 1));

  return {
    server_time: t,
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    tz_offset_min: -new Date().getTimezoneOffset(),
    from,
    to,
    days,
    previous_from: prevFrom,
    previous_to: addDays(from, -1),
    total: perDay.reduce((s, d) => s + d.count, 0),
    previous_total: perDay.reduce((s, d) => s + d.previous_count, 0),
    per_day: perDay,
    per_hour: perHour,
    weekday_hour: grid,
    flow: {
      received: counted.length,
      acknowledged: counted.filter((a) => a.acknowledged).length,
      resolved: counted.filter((a) => a.resolved).length,
      median_ack_s: median(ackS),
      median_resolve_s: median(resolveS),
      ack_timed: ackS.length,
      resolve_timed: resolveS.length,
    },
    open_now: open.length,
    open_medical_now: open.filter((a) => a.alert_type === "MEDICAL").length,
    fobs_active: seen.length,
    fobs_total: fobs.length,
    low_battery: low.length,
    median_ack_by_type: Object.fromEntries(Object.entries(ackByType).map(([type, s]) => [type, median(s)])),
    hotspots: hotspots(counted),
    delivery,
    duplicates: MOCK_DUPLICATES.filter((d) => inRange(d.minAgo)).length,
    late_over_max: cur.filter((a) => a.late_over_max).length,
    rejected: { total: Object.values(byReason).reduce((s, n) => s + n, 0), by_reason: byReason },
    stale_fobs: fobs.filter((d) => !seen.includes(d)).map(name).sort(),
    low_battery_fobs: low.map((d) => ({ name: name(d), pct: d.battery })),
    reference_age_s: MOCK_STATUS.reference_age_s,
    ...overviewV5(startS, endS, perDay),
  };
}

// ---------- fields added in v5, same rules as _overview_v5 in server/stats.py ----------

const SHOWN_TYPES = ["MEDICAL", "SUSPICIOUS", "SILENT"];
const URGENT_TYPES = ["MEDICAL", "SILENT"];
const EVENT_ORDER = { received: 0, acknowledged: 1, resolved: 2 };

const alertName = (a) => a.student_name || a.device_id;

function placeShort(a) {
  if (a.latitude !== null) return a.place_name || "GPS";
  if (a.floor !== null) return "Indoors, floor " + a.floor;
  return null;
}

function countOnDay(day) {
  return between(startOfDay(day), startOfDay(addDays(day, 1))).filter(notStatus).length;
}

function overviewV5(startS, endS, perDay) {
  const openRows = newestFirst(alerts.filter((a) => !a.acknowledged && !a.resolved && notStatus(a)));
  const today = isoDay(new Date(now() * 1000));
  let counts = perDay.filter((d) => d.date < today).map((d) => d.count);
  if (!counts.length) counts = [1, 2, 3, 4, 5, 6, 7].map((i) => countOnDay(addDays(today, -i)));
  const latest = alerts.filter(notStatus).sort((x, y) => y.timestamp - x.timestamp || y.id - x.id)[0];
  const inRange = (ts) => ts !== null && ts >= startS && ts < endS;

  const points = [];
  const events = [];
  let indoor = 0;
  alerts.filter(notStatus).forEach((a) => {
    const base = { alert_id: a.id, type: a.alert_type, name: alertName(a), place: placeShort(a) };
    if (inRange(a.timestamp)) {
      if (a.latitude !== null) {
        points.push({ id: a.id, type: a.alert_type, lat: a.latitude, lon: a.longitude, name: base.name, place: base.place, time: a.timestamp });
      } else {
        indoor += 1;
      }
      events.push({ ...base, kind: "received", time: a.timestamp });
    }
    // Resolving an alert nobody acknowledged sets both times at once. Show only Resolved then.
    if (inRange(a.acknowledged_at) && a.acknowledged_at !== a.resolved_at) events.push({ ...base, kind: "acknowledged", time: a.acknowledged_at });
    if (inRange(a.resolved_at)) events.push({ ...base, kind: "resolved", time: a.resolved_at });
  });
  events.sort((x, y) => y.time - x.time || EVENT_ORDER[y.kind] - EVENT_ORDER[x.kind] || y.alert_id - x.alert_id);
  points.sort((x, y) => x.time - y.time || x.id - y.id);

  return {
    open_by_type: Object.fromEntries(SHOWN_TYPES.map((t) => [t, openRows.filter((a) => a.alert_type === t).length])),
    urgent_open: openRows.filter((a) => URGENT_TYPES.includes(a.alert_type)).map((a) => ({ id: a.id, name: alertName(a), type: a.alert_type })),
    last_alert: latest
      ? { id: latest.id, time: latest.timestamp, type: latest.alert_type, name: alertName(latest), place: placeShort(latest) }
      : null,
    today_count: countOnDay(today),
    usual_per_day: median(counts),
    points: points.slice(-2000),
    indoor_count: indoor,
    recent_events: events.slice(0, 10),
  };
}

/** Same rules as _hotspots in server/stats.py. */
function hotspots(list) {
  const counts = new Map();
  list.forEach((a) => {
    let key;
    if (a.latitude !== null) key = a.place_name ? [a.place_name.charAt(0).toUpperCase() + a.place_name.slice(1), "place"] : ["GPS, no named place", "gps"];
    else if (a.floor !== null) key = ["Indoors, floor " + a.floor, "floor"];
    else key = ["No location", "none"];
    const id = key.join("|");
    const row = counts.get(id) || { label: key[0], kind: key[1], count: 0 };
    row.count += 1;
    counts.set(id, row);
  });
  const ranked = [...counts.values()].sort((x, y) => y.count - x.count || x.label.localeCompare(y.label));
  return { places: ranked.slice(0, 5), more_count: Math.max(0, ranked.length - 5) };
}

const CSV_COLUMNS = [
  "Received", "Type", "Student", "Fob ID", "Status", "Place", "Floor",
  "Latitude", "Longitude", "Accuracy (m)", "Battery (%)", "Link", "Acknowledged", "Resolved",
  "Pressed (Fob clock)", "Sent late",
];

function localTime(ts) {
  if (ts === null || ts === undefined) return "";
  const d = new Date(ts * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return isoDay(d) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
}

function csvCell(value) {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function csvText(value) {
  const s = value === null || value === undefined ? "" : String(value);
  return /^[=+\-@\t\r]/.test(s) ? "'" + s : s; // a spreadsheet would run these as formulas
}

function csvPlace(a) {
  if (!a.place_name) return "";
  if (a.place_distance_m <= 40) return "Near " + a.place_name;
  return Math.round(a.place_distance_m / 10) * 10 + " m " + a.place_bearing + " of " + a.place_name;
}

/** The CSV the server's /api/export.csv would send, made from the mock rows. */
export function mockExportCsv(from, to) {
  parseRange(from, to);
  const rows = between(startOfDay(from), startOfDay(addDays(to, 1))).sort((a, b) => a.timestamp - b.timestamp || a.id - b.id);
  const lines = [CSV_COLUMNS.map(csvCell).join(",")];
  rows.forEach((a) => {
    lines.push(
      [
        localTime(a.timestamp),
        a.alert_type,
        csvText(a.student_name),
        csvText(a.device_id),
        a.resolved ? "Resolved" : a.acknowledged ? "Acknowledged" : "Open",
        csvText(csvPlace(a)),
        a.floor ?? "",
        a.latitude !== null ? a.latitude.toFixed(6) : "",
        a.longitude !== null ? a.longitude.toFixed(6) : "",
        a.accuracy ?? "",
        a.battery ?? "",
        { lora: "LoRa", wifi: "WiFi" }[a.link] || "",
        localTime(a.acknowledged_at),
        localTime(a.resolved_at),
        localTime(a.pressed_at),
        a.late_over_max ? "Yes, over 15 min, " + a.late_s + " s" : a.sent_late ? "Yes, " + a.late_s + " s" : "",
      ]
        .map(csvCell)
        .join(","),
    );
  });
  return { filename: "safeping-alerts-" + from + "-to-" + to + ".csv", text: "﻿" + lines.join("\r\n") + "\r\n" };
}

export async function mockGet(url) {
  const [path, query] = url.split("?");
  const params = new URLSearchParams(query || "");
  if (path === "/api/stats") return getStats(params);
  if (path === "/api/alerts") return getAlerts(params);
  if (path === "/api/search") return search(params);
  const one = path.match(/^\/api\/alerts\/(\d+)$/);
  if (one) return getAlert(Number(one[1]));
  if (path === "/api/status") return getStatus();
  if (path === "/api/config") return { ...MOCK_CONFIG };
  if (path === "/api/places") return { places: MOCK_PLACES.map((p) => ({ ...p })), max_distance_m: MOCK_PLACES_MAX_DISTANCE_M };
  if (path === "/api/devices") return getDevices();
  const m = path.match(/^\/api\/devices\/([^/]+)\/alerts$/);
  if (m) return getDeviceAlerts(decodeURIComponent(m[1]));
  const b = path.match(/^\/api\/devices\/([^/]+)\/boots$/);
  if (b) return getDeviceBoots(decodeURIComponent(b[1]));
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
      alert.help_sent_at = t; // as if MQTT is on: "Help message sent to Fob"
    }
    return { ok: true, changed, help_sent: changed };
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
