import { alertState, isSentLate, linkMeta, STATES, typeMeta } from "../lib/alertMeta.js";
import { formatDateTime } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import Tooltip from "./Tooltip.jsx";

/** Small sentence-case tag: a tinted rectangle, with the icon and word in a darker
    shade of the same color. */
export function Tag({ color, icon, children }) {
  return (
    <span className={"tag tag--" + color}>
      {icon && <Icon icon={icon} size={14} />}
      {children}
    </span>
  );
}

/** An alert type as a tag: rose Medical, amber Suspicious, violet Silent, gray Status. */
export function TypeTag({ type }) {
  const meta = typeMeta(type);
  return (
    <Tag color={meta.key} icon={meta.icon}>
      {meta.label}
    </Tag>
  );
}

/** Just the type icon, in its color, for legends, search and Overview lines.
    Name it with label when no word is next to it. */
export function TypeIcon({ type, size = 14, label }) {
  const meta = typeMeta(type);
  return <Icon icon={meta.icon} size={size} fixed className={"type-icon--" + meta.key} label={label} />;
}

/** LoRa (gray) or WiFi (teal). Nothing at all when the link is not known. */
export function LinkTag({ link, children }) {
  const meta = linkMeta(link);
  if (!meta) return null;
  return (
    <Tag color={meta.color} icon={meta.icon}>
      {meta.label}
      {children}
    </Tag>
  );
}

/** "Pressed 10:01:12 AM, arrived 10:07:40 AM": both times of a late alert. */
export function lateText(alert, timeFormat) {
  return "Pressed " + formatDateTime(alert.pressed_at, timeFormat) + ", arrived " + formatDateTime(alert.timestamp, timeFormat);
}

/** "Sent late" (gray) when the alert reached the server more than 60 s after the press,
    "Sent late (over 15 min)" (yellow) after more than 15 minutes. The tooltip has both
    times. Nothing for alerts on time. */
export function LateTag({ alert, timeFormat }) {
  if (!isSentLate(alert)) return null;
  const overMax = !!alert.late_over_max;
  return (
    <Tooltip label={lateText(alert, timeFormat)}>
      <span className="late-tag">
        <Tag color={overMax ? "yellow" : "unknown"} icon={overMax ? icons.warning : icons.late}>
          {overMax ? "Sent late (over 15 min)" : "Sent late"}
        </Tag>
        <span className="visually-hidden">. {lateText(alert, timeFormat)}</span>
      </span>
    </Tooltip>
  );
}

/** A dot and a word: Open (orange), Acknowledged (green), Resolved (gray). The word stays neutral. */
export function StatusDot({ alert, state }) {
  const s = STATES[state || alertState(alert)];
  return (
    <span className="status">
      <span className={"dot dot--" + s.color} aria-hidden="true" />
      {s.label}
    </span>
  );
}
