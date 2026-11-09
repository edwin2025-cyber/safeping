import { alertState, linkMeta, STATES, typeMeta } from "../lib/alertMeta.js";

/** Small sentence-case tag: subtler background, text color from the same family. */
export function Tag({ color, Icon, children }) {
  return (
    <span className={"tag tag--" + color}>
      {Icon && <Icon size={12} strokeWidth={1.75} aria-hidden="true" />}
      {children}
    </span>
  );
}

export function TypeTag({ type }) {
  const meta = typeMeta(type);
  return (
    <Tag color={meta.color} Icon={meta.Icon}>
      {meta.label}
    </Tag>
  );
}

/** LoRa or WiFi. Nothing at all when the link is not known. */
export function LinkTag({ link }) {
  const meta = linkMeta(link);
  if (!meta) return null;
  return (
    <Tag color={meta.color} Icon={meta.Icon}>
      {meta.label}
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
