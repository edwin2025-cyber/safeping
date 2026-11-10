import { icons } from "./icons.js";

// Short words for tags, long words for copied text. Color is never the only
// signal: each type also has an icon and a word.
export const TYPES = {
  MEDICAL: { label: "Medical", long: "Medical emergency", color: "red", icon: icons.medical },
  SUSPICIOUS: { label: "Suspicious", long: "Suspicious person", color: "yellow", icon: icons.suspicious },
  SILENT: { label: "Silent", long: "Silent alert", color: "purple", icon: icons.silent },
  STATUS: { label: "Status", long: "Status check", color: "gray", icon: icons.status },
};

export const TYPE_ORDER = ["MEDICAL", "SUSPICIOUS", "SILENT", "STATUS"];

export function typeMeta(type) {
  return TYPES[type] || { label: type, long: type, color: "gray", icon: icons.unknownType };
}

export const STATES = {
  open: { label: "Open", color: "orange" },
  acknowledged: { label: "Acknowledged", color: "green" },
  resolved: { label: "Resolved", color: "gray" },
};

export function alertState(alert) {
  if (alert.resolved) return "resolved";
  return alert.acknowledged ? "acknowledged" : "open";
}

// Only known links are shown. Older alerts and test tools have no link.
export const LINKS = {
  lora: { label: "LoRa", color: "gray", icon: icons.lora },
  wifi: { label: "WiFi", color: "teal", icon: icons.wifi },
};

export function linkMeta(link) {
  return LINKS[link] || null;
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

/** Open alerts first, by type priority, then newest. Then acknowledged, then resolved, newest first. */
export function sortAlerts(alerts) {
  return alerts.slice().sort((x, y) => {
    const sx = STATE_ORDER[alertState(x)];
    const sy = STATE_ORDER[alertState(y)];
    if (sx !== sy) return sx - sy;
    if (sx === 0 && x.priority !== y.priority) return x.priority - y.priority;
    return y.id - x.id;
  });
}
