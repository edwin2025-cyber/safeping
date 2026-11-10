// "Show an empty dashboard" (Settings > About > Testing): this browser tab shows SafePing as it
// looks on its first day, with no Fobs, alerts, readings or places, so every empty state can be
// checked. Nothing on the server changes. lib/api.js asks emptyAnswer() before every request.
// It lives in sessionStorage: only this tab, until Exit preview or the tab closes. The app shows
// a banner the whole time, so nobody mistakes it for the real dashboard.
import { addDays, dayCount, isoDay } from "./dates.js";

const KEY = "safeping.emptyPreview";
const TYPES = ["MEDICAL", "SUSPICIOUS", "SILENT", "STATUS"];

/** Returned by emptyAnswer for requests that should still reach the server (settings, not data). */
export const PASS_THROUGH = Symbol("pass-through");

export const CSV_HEADER =
  "Received,Type,Student,Fob ID,Status,Place,Floor,Latitude,Longitude,Accuracy (m),Battery (%),Link,Acknowledged,Resolved";

export function isEmptyPreview() {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function startEmptyPreview() {
  try {
    sessionStorage.setItem(KEY, "1");
  } catch {
    // storage blocked: nothing to start
  }
  window.location.reload();
}

export function stopEmptyPreview() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
  window.location.reload();
}

function zeros() {
  return Object.fromEntries(TYPES.map((t) => [t, 0]));
}

/** /api/stats for a database with nothing in it, in the same shape as server/stats.py. */
function emptyStats(params) {
  const today = isoDay(new Date());
  const from = params.get("from") || today;
  const to = params.get("to") || today;
  const days = Math.max(1, dayCount(from, to) || 1);
  const prevFrom = addDays(from, -days);
  return {
    server_time: Date.now() / 1000,
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    tz_offset_min: -new Date().getTimezoneOffset(),
    from,
    to,
    days,
    previous_from: prevFrom,
    previous_to: addDays(from, -1),
    total: 0,
    previous_total: 0,
    per_day: Array.from({ length: days }, (_, i) => ({
      date: addDays(from, i),
      count: 0,
      by_type: zeros(),
      previous_date: addDays(prevFrom, i),
      previous_count: 0,
    })),
    per_hour: days === 1 ? Array.from({ length: 24 }, (_, hour) => ({ hour, count: 0, by_type: zeros(), previous_count: 0 })) : null,
    weekday_hour: Array.from({ length: 7 }, () => Array(24).fill(0)),
    flow: { received: 0, acknowledged: 0, resolved: 0, median_ack_s: null, median_resolve_s: null, ack_timed: 0, resolve_timed: 0 },
    open_now: 0,
    open_medical_now: 0,
    fobs_active: 0,
    fobs_total: 0,
    low_battery: 0,
    median_ack_by_type: {},
    hotspots: { places: [], more_count: 0 },
    delivery: { lora: 0, wifi: 0, unknown: 0 },
    duplicates: null,
    rejected: { total: 0, by_reason: {} },
    stale_fobs: [],
    low_battery_fobs: [],
    reference_age_s: null,
    open_by_type: { MEDICAL: 0, SUSPICIOUS: 0, SILENT: 0 },
    urgent_open: [],
    last_alert: null,
    today_count: 0,
    usual_per_day: 0,
    points: [],
    indoor_count: 0,
    recent_events: [],
  };
}

/** What a first-day server would answer, or PASS_THROUGH for /api/config. */
export function emptyAnswer(url) {
  const [path, query] = url.split("?");
  const params = new URLSearchParams(query || "");
  const now = Date.now() / 1000;
  if (path === "/api/config") return PASS_THROUGH;
  if (path === "/api/alerts") return { server_time: now, alerts: [] };
  if (path === "/api/status") {
    return { server_time: now, reference_age_s: null, reference_pressure: null, unacknowledged: 0, rejected_total: 0, last_lora_age_s: null };
  }
  if (path === "/api/devices") return { server_time: now, devices: [] };
  if (path === "/api/places") return { places: [], max_distance_m: 200 };
  if (path === "/api/search") return { server_time: now, query: (params.get("q") || "").trim(), students: [], alerts: [] };
  if (path === "/api/stats") return emptyStats(params);
  throw new Error("HTTP 404"); // one alert, one device's history: none exist
}
