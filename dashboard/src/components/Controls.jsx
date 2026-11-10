import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";

/** On and off switch. Name it with labelledBy (the id of its label). */
export function Switch({ checked, onChange, labelledBy, disabled = false }) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      aria-disabled={disabled || undefined}
      onClick={() => !disabled && onChange(!checked)}
    />
  );
}

/** A few choices side by side. Behaves like a radio group. */
export function Segmented({ value, options, onChange, label, labelledBy }) {
  function onKeyDown(event) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const i = options.findIndex((o) => o.value === value);
    const next = options[(i + (event.key === "ArrowRight" ? 1 : options.length - 1)) % options.length];
    onChange(next.value);
    const buttons = event.currentTarget.querySelectorAll("button");
    buttons[options.indexOf(next)].focus();
  }
  return (
    <div className="segmented" role="radiogroup" aria-label={label} aria-labelledby={labelledBy} onKeyDown={onKeyDown}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Dropdown: a native select with a quiet look. */
export function Select({ value, options, onChange, labelledBy, label, id }) {
  return (
    <span className="select">
      <select
        id={id}
        value={value}
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : label}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <Icon icon={icons.chevronDown} size={12} />
    </span>
  );
}
