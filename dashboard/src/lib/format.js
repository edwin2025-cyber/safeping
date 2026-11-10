import { alertState, hasGps, linkMeta, STATES, typeMeta, zoneRadius } from "./alertMeta.js";

export const NEAR_M = 40; // closer than this: "Near the front entrance"

export function ago(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return seconds + " s ago";
  if (seconds < 3600) return Math.floor(seconds / 60) + " min ago";
  if (seconds < 86400) return Math.floor(seconds / 3600) + " h " + Math.floor((seconds % 3600) / 60) + " min ago";
  return Math.floor(seconds / 86400) + " d ago";
}

/** Shorter, for the top bar: "40 s ago", "12 min ago", "3 h ago", "2 d ago". At most "59 min ago". */
export function agoShort(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return seconds + " s ago";
  if (seconds < 3600) return Math.floor(seconds / 60) + " min ago";
  if (seconds < 86400) return Math.floor(seconds / 3600) + " h ago";
  return Math.floor(seconds / 86400) + " d ago";
}

/** Where, in a few words, for feeds and search: the named place ("the bus loop"),
    "Indoors, floor 3", "GPS" or null. */
export function placeShort(alert) {
  if (hasGps(alert)) return alert.place_name || "GPS";
  if (alert.floor !== null && alert.floor !== undefined) return "Indoors, floor " + alert.floor;
  return null;
}

function hour12(timeFormat) {
  return timeFormat !== "24";
}

/** 3:04:05 PM or 15:04:05 */
export function formatClock(unixSeconds, timeFormat) {
  return new Date(unixSeconds * 1000).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: hour12(timeFormat),
  });
}

/** 3:04 PM or 15:04 */
export function formatTime(unixSeconds, timeFormat) {
  return new Date(unixSeconds * 1000).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    hour12: hour12(timeFormat),
  });
}

/** Nov 8, 2026 */
export function formatDate(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** Nov 8, 2026, 3:04:05 PM (seconds optional) */
export function formatDateTime(unixSeconds, timeFormat, withSeconds = true) {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: withSeconds ? "2-digit" : undefined,
    hour12: hour12(timeFormat),
  });
}

export function formatNumber(n) {
  return Number(n).toLocaleString();
}

/** A median time: "45 s", "1.8 min", "12 min", "1.5 h". */
export function formatDuration(seconds) {
  if (seconds < 60) return Math.round(seconds) + " s";
  const min = seconds / 60;
  if (min < 10) return min.toFixed(1) + " min";
  if (min < 60) return Math.round(min) + " min";
  return (min / 60).toFixed(1) + " h";
}

export function coords(alert) {
  return alert.latitude.toFixed(6) + ", " + alert.longitude.toFixed(6);
}

export function googleMapsUrl(alert) {
  return "https://www.google.com/maps/search/?api=1&query=" + alert.latitude.toFixed(6) + "," + alert.longitude.toFixed(6);
}

export function studentName(alert) {
  return alert.student_name || alert.device_id;
}

/** The place in words, or null when nothing is known ("Unknown" is shown muted).
    Within 40 m of a named place: "Near the basketball courts".
    40 to 200 m: "120 m NE of the front entrance" (the server only sends places within 200 m).
    Otherwise GPS accuracy, then the floor. */
export function placeText(alert) {
  if (hasGps(alert)) {
    if (alert.place_name) {
      const d = alert.place_distance_m;
      if (d <= NEAR_M) return "Near " + alert.place_name;
      return Math.round(d / 10) * 10 + " m " + alert.place_bearing + " of " + alert.place_name;
    }
    return alert.accuracy !== null ? "GPS, about " + alert.accuracy + " m" : "GPS";
  }
  if (alert.floor !== null && alert.floor !== undefined) return "Indoors, floor " + alert.floor;
  return null;
}

/** "Area: 62 m (GPS 12 m + sight 50 m)" */
export function areaLine(alert, sightRadius) {
  if (!hasGps(alert)) return null;
  const r = zoneRadius(alert, sightRadius);
  if (alert.alert_type === "SUSPICIOUS") {
    const gps = alert.accuracy !== null ? alert.accuracy + " m" : "accuracy not sent";
    return "Area: " + r + " m (GPS " + gps + " + sight " + sightRadius + " m)";
  }
  if (alert.accuracy === null) return "Area: GPS accuracy not sent";
  return "Area: " + r + " m (GPS accuracy)";
}

export function temperatureText(hundredths) {
  if (hundredths === null || hundredths === undefined) return null;
  return (hundredths / 100).toFixed(1) + " °C";
}

/** The camera review window and area for a SUSPICIOUS alert, plus the text "Copy for security" copies. */
export function cameraInfo(alert, settings) {
  const received = alert.timestamp;
  const start = received - settings.cameraBefore * 60;
  const end = received + settings.cameraAfter * 60;
  const place = placeText(alert);
  let area;
  if (hasGps(alert)) {
    area = "within " + zoneRadius(alert, settings.sightRadius) + " m of " + coords(alert);
  } else if (alert.floor !== null && alert.floor !== undefined) {
    area = "Indoors, floor " + alert.floor;
  } else {
    area = "Location unknown";
  }
  const lines = [
    "SafePing SUSPICIOUS alert",
    "Student: " + (alert.student_name || "Unknown") + " (" + alert.device_id + ")",
    "Pressed: " + formatDateTime(received, settings.timeFormat),
  ];
  if (alert.place_name) lines.push("Place: " + place);
  lines.push("Review cameras: " + formatDateTime(start, settings.timeFormat, false) + " to " + formatDateTime(end, settings.timeFormat, false));
  lines.push("Area: " + area);
  return { start, end, area, place: alert.place_name ? place : null, text: lines.join("\n") };
}

/** Plain text for "Copy details". */
export function detailsText(alert, settings) {
  const lines = [
    "SafePing " + typeMeta(alert.alert_type).long.toUpperCase() + " alert",
    "Student: " + (alert.student_name || "Unknown") + " (" + alert.device_id + ")",
    "Pressed: " + formatDateTime(alert.timestamp, settings.timeFormat),
    "Place: " + (placeText(alert) || "Unknown"),
  ];
  if (hasGps(alert)) {
    lines.push("GPS: " + coords(alert) + (alert.accuracy !== null ? ", within " + alert.accuracy + " m" : ""));
    lines.push("Map: " + googleMapsUrl(alert));
  }
  if (alert.battery !== null) lines.push("Battery: " + alert.battery + "%");
  const link = linkMeta(alert.link);
  if (link) lines.push("Link: " + link.label);
  lines.push("Status: " + STATES[alertState(alert)].label);
  return lines.join("\n");
}
