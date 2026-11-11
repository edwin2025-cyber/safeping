import { icons } from "./icons.js";

// Short words for labels, long words for copied text. Color is never the only
// signal: each type also has an icon and a word. key names the type color
// (--color-type-<key>) used for icons, map markers and chart lines.
export const TYPES = {
  MEDICAL: { label: "Medical", long: "Medical emergency", key: "medical", icon: icons.medical },
  SUSPICIOUS: { label: "Suspicious", long: "Suspicious person", key: "suspicious", icon: icons.suspicious },
  SILENT: { label: "Silent", long: "Silent alert", key: "silent", icon: icons.silent },
  STATUS: { label: "Status", long: "Status check", key: "status", icon: icons.status },
};

export const TYPE_ORDER = ["MEDICAL", "SUSPICIOUS", "SILENT", "STATUS"];

export function typeMeta(type) {
  return TYPES[type] || { label: type, long: type, key: "status", icon: icons.unknownType };
}

/** The CSS color of a type, for SVG and inline styles. */
export function typeColor(type) {
  return "var(--color-type-" + typeMeta(type).key + ")";
}

// MEDICAL and SILENT are the urgent types: they get the pulsing dot on Live,
// the red Live count in the sidebar and the Urgent open tile on Overview.
export const URGENT_TYPES = ["MEDICAL", "SILENT"];

export function isUrgentOpen(alert) {
  return URGENT_TYPES.includes(alert.alert_type) && alertState(alert) === "open";
}

export const STATES = {
  open: { label: "Open", color: "open" },
  acknowledged: { label: "Acknowledged", color: "green" },
  resolved: { label: "Resolved", color: "gray" },
};

export function alertState(alert) {
  if (alert.resolved) return "resolved";
  return alert.acknowledged ? "acknowledged" : "open";
}

// Only known links are shown. Older alerts and test tools have no link.
export const LINKS = {
  lora: { label: "LoRa", color: "lora", icon: icons.lora },
  wifi: { label: "WiFi", color: "wifi", icon: icons.wifi },
};

export function linkMeta(link) {
  return LINKS[link] || null;
}

/** True when the alert reached the server more than 60 s after the press (a retry from
    the Fob's queue). pressed_at is the Fob's own clock, so it is missing when its clock
    was not set. */
export function isSentLate(alert) {
  return !!alert.sent_late && alert.pressed_at !== null && alert.pressed_at !== undefined;
}

export function hasGps(alert) {
  return alert.latitude !== null && alert.latitude !== undefined && alert.longitude !== null && alert.longitude !== undefined;
}

export function isOpenMedical(alert) {
  return alert.alert_type === "MEDICAL" && alertState(alert) === "open";
}

/** Map circle radius in meters. SUSPICIOUS adds the sight radius: the area the
    student could see. It does not grow over time. */
export function zoneRadius(alert, sightRadius) {
  const acc = alert.accuracy || 0;
  if (alert.alert_type === "SUSPICIOUS") return acc + sightRadius;
  return acc;
}

const STATE_ORDER = { open: 0, acknowledged: 1, resolved: 2 };

// The Live sort control. Newest first is the default.
export const SORT_ORDERS = [
  { value: "newest", label: "Newest first" },
  { value: "urgent", label: "Most urgent first" },
];

/** Open alerts first, then acknowledged, then resolved. Inside each group:
    "newest" puts the newest alert on top. "urgent" (the old order) sorts open alerts by
    type priority, then newest; acknowledged and resolved stay newest first. */
export function sortAlerts(alerts, order = "newest") {
  return alerts.slice().sort((x, y) => {
    const sx = STATE_ORDER[alertState(x)];
    const sy = STATE_ORDER[alertState(y)];
    if (sx !== sy) return sx - sy;
    if (order === "urgent") {
      if (sx === 0 && x.priority !== y.priority) return x.priority - y.priority;
      return y.id - x.id;
    }
    return y.timestamp - x.timestamp || y.id - x.id;
  });
}
