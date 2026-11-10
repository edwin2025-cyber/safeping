import { alertState, linkMeta, STATES, typeMeta } from "../lib/alertMeta.js";
import Icon from "./Icon.jsx";

/** Small sentence-case tag: subtler background, text color from the same family.
    The icon takes the tag's text color. */
export function Tag({ color, icon, children }) {
  return (
    <span className={"tag tag--" + color}>
      {icon && <Icon icon={icon} size={14} />}
      {children}
    </span>
  );
}

export function TypeTag({ type }) {
  const meta = typeMeta(type);
  return (
    <Tag color={meta.color} icon={meta.icon}>
      {meta.label}
    </Tag>
  );
}

/** LoRa or WiFi. Nothing at all when the link is not known. */
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

/** A dot and a word: Open (orange), Acknowledged (green), Resolved (gray). */
export function StatusDot({ alert, state }) {
  const s = STATES[state || alertState(alert)];
  return (
    <span className="status">
      <span className={"dot dot--" + s.color} aria-hidden="true" />
      {s.label}
    </span>
  );
}
