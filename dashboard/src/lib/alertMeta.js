import { BellOff, Check, CircleCheck, CircleDot, CircleHelp, Eye, HeartPulse, RadioTower, Wifi } from "lucide-react";

// Same words as the old dashboard. Color is never the only signal: each type has an icon and a word.
export const TYPES = {
  MEDICAL: { label: "Medical emergency", color: "red", Icon: HeartPulse },
  SUSPICIOUS: { label: "Suspicious person", color: "yellow", Icon: Eye },
  SILENT: { label: "Silent alert", color: "purple", Icon: BellOff },
  STATUS: { label: "Status check", color: "gray", Icon: CircleCheck },
};

export const TYPE_ORDER = ["MEDICAL", "SUSPICIOUS", "SILENT", "STATUS"];

export function typeMeta(type) {
  return TYPES[type] || { label: type, color: "gray", Icon: CircleHelp };
}

export const STATES = {
  open: { label: "Open", color: "orange", Icon: CircleDot },
  acknowledged: { label: "Acknowledged", color: "green", Icon: Check },
};

export const LINKS = {
  lora: { label: "LoRa", color: "gray", Icon: RadioTower },
  wifi: { label: "WiFi", color: "teal", Icon: Wifi },
  unknown: { label: "Link unknown", color: "gray", Icon: CircleHelp },
};

export function linkMeta(link) {
  return LINKS[link] || LINKS.unknown;
}

export function hasGps(alert) {
  return alert.latitude !== null && alert.longitude !== null && alert.latitude !== undefined;
}

/** Map circle radius in meters. SUSPICIOUS adds the sight radius: the area the
    student could see. It does not grow over time. */
export function zoneRadius(alert, sightRadius) {
  const acc = alert.accuracy || 0;
  if (alert.alert_type === "SUSPICIOUS") return acc + sightRadius;
  return acc;
}

/** Open alerts first. Open ones by type priority, then newest. Same as the old dashboard. */
export function sortAlerts(alerts) {
  return alerts.slice().sort((x, y) => {
    if (x.acknowledged !== y.acknowledged) return x.acknowledged ? 1 : -1;
    if (!x.acknowledged && x.priority !== y.priority) return x.priority - y.priority;
    return y.id - x.id;
  });
}
