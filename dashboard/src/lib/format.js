import { hasGps, typeMeta, linkMeta, zoneRadius } from "./alertMeta.js";

export function ago(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return seconds + " s ago";
  if (seconds < 3600) return Math.floor(seconds / 60) + " min ago";
  if (seconds < 86400) return Math.floor(seconds / 3600) + " h " + Math.floor((seconds % 3600) / 60) + " min ago";
  return Math.floor(seconds / 86400) + " d ago";
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

export function coords(alert) {
  return alert.latitude.toFixed(6) + ", " + alert.longitude.toFixed(6);
}

/** Short location line for cards and the camera box. */
export function locationLine(alert) {
  if (hasGps(alert)) {
    return alert.accuracy !== null ? "GPS, about " + alert.accuracy + " m" : "GPS";
  }
  if (alert.floor !== null && alert.floor !== undefined) return "Indoors, floor " + alert.floor;
  return "Location unknown";
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

export function studentName(alert) {
  return alert.student_name || alert.device_id;
}

/** Plain text for the camera review box. Format given in the dashboard spec. */
export function cameraText(alert, settings) {
  const received = alert.timestamp;
  const start = received - settings.cameraBefore * 60;
  const end = received + settings.cameraAfter * 60;
  let area;
  if (hasGps(alert)) {
    area = "within " + zoneRadius(alert, settings.sightRadius) + " m of " + coords(alert);
  } else if (alert.floor !== null && alert.floor !== undefined) {
    area = "Indoors, floor " + alert.floor;
  } else {
    area = "Location unknown";
  }
  return {
    start,
    end,
    area,
    text: [
      "SafePing SUSPICIOUS alert",
      "Student: " + (alert.student_name || "Unknown") + " (" + alert.device_id + ")",
      "Pressed: " + formatDateTime(received, settings.timeFormat),
      "Review cameras: " + formatDateTime(start, settings.timeFormat, false) + " to " +
        formatDateTime(end, settings.timeFormat, false),
      "Area: " + area,
    ].join("\n"),
  };
}

/** Plain text for "Copy details" in the peek. */
export function detailsText(alert, settings) {
  const lines = [
    "SafePing " + typeMeta(alert.alert_type).label.toUpperCase() + " alert",
    "Student: " + (alert.student_name || "Unknown") + " (" + alert.device_id + ")",
    "Received: " + formatDateTime(alert.timestamp, settings.timeFormat),
  ];
  if (alert.device_ts) lines.push("Fob time: " + formatDateTime(alert.device_ts, settings.timeFormat));
  if (hasGps(alert)) {
    lines.push("Location: " + coords(alert) + (alert.accuracy !== null ? " (within " + alert.accuracy + " m)" : ""));
    const area = areaLine(alert, settings.sightRadius);
    if (area) lines.push(area);
  } else {
    lines.push("Location: " + locationLine(alert));
  }
  if (alert.battery !== null) lines.push("Battery: " + alert.battery + "%");
  lines.push("Link: " + linkMeta(alert.link).label);
  lines.push("Status: " + (alert.acknowledged ? "Acknowledged" : "Open"));
  return lines.join("\n");
}
