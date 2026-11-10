import { useId, useRef, useState } from "react";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import Popover from "./Popover.jsx";

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

/** Dropdown: a quiet button that opens a styled list of choices (not the browser's own list,
    which cannot be styled). Up, Down, Home and End move, Enter picks, Esc closes.
    An option can be { value, label, note, disabled }. */
export function Select({ value, options, onChange, labelledBy, label, id, align = "start" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const ownId = useId();
  const buttonId = id || "select-" + ownId.replace(/:/g, "");
  const current = options.find((o) => o.value === value) || options[0];
  return (
    <>
      <button
        ref={ref}
        id={buttonId}
        type="button"
        className="select-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={labelledBy ? labelledBy + " " + buttonId : undefined}
        aria-label={labelledBy ? undefined : (label || "Choose") + ": " + current.label}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span>{current.label}</span>
        <Icon icon={icons.chevronDown} size={12} />
      </button>
      <Popover
        anchor={ref.current}
        open={open}
        onClose={() => setOpen(false)}
        label={label || "Choices"}
        role="listbox"
        className="popover--select"
        placement={align === "end" ? "bottom-end" : "bottom-start"}
        minWidth={ref.current ? ref.current.offsetWidth : undefined}
      >
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="option"
            aria-selected={o.value === value}
            aria-disabled={o.disabled || undefined}
            className="option"
            onClick={() => {
              if (o.disabled) return;
              onChange(o.value);
              setOpen(false);
            }}
          >
            {o.label}
            {o.note && <span className="option-note">{o.note}</span>}
            {o.value === value && <Icon icon={icons.acknowledged} size={14} className="option-check" />}
          </button>
        ))}
      </Popover>
    </>
  );
}
