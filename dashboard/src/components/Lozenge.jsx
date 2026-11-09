import "./Lozenge.css";
import { linkMeta, STATES, typeMeta } from "../lib/alertMeta.js";

/** Small pill: subtler background, text color from the same family, icon and word. */
export function Lozenge({ color, Icon, label, size = "normal" }) {
  return (
    <span className={`lozenge lozenge--${color} lozenge--${size}`}>
      {Icon && <Icon size={size === "small" ? 12 : 14} strokeWidth={2.25} aria-hidden="true" />}
      <span>{label}</span>
    </span>
  );
}

export function TypeLozenge({ type }) {
  const meta = typeMeta(type);
  return <Lozenge color={meta.color} Icon={meta.Icon} label={meta.label} />;
}

export function StateLozenge({ acknowledged }) {
  const meta = acknowledged ? STATES.acknowledged : STATES.open;
  return <Lozenge color={meta.color} Icon={meta.Icon} label={meta.label} size="small" />;
}

export function LinkLozenge({ link }) {
  const meta = linkMeta(link);
  return <Lozenge color={meta.color} Icon={meta.Icon} label={meta.label} size="small" />;
}

/** Rounded status pill for the top bar. */
export function Pill({ color, Icon, children, title, label }) {
  return (
    <span className={`pill pill--${color}`} title={title} aria-label={label}>
      {Icon && <Icon size={14} strokeWidth={2.25} aria-hidden="true" />}
      <span className="num">{children}</span>
    </span>
  );
}
