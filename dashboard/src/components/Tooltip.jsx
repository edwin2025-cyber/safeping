import { Children, cloneElement } from "react";
import { hideTooltip, showTooltip } from "../lib/tooltip.js";

/** Wraps one element and shows a dark tooltip on hover or keyboard focus.
    shortcut is a small hint such as "Ctrl+\". The tooltip is visual only:
    icon buttons still need their own aria-label. */
export default function Tooltip({ label, shortcut, children }) {
  const child = Children.only(children);
  const info = { label, shortcut };
  const p = child.props;
  return cloneElement(child, {
    "data-tooltip": label,
    onMouseEnter: (e) => {
      p.onMouseEnter && p.onMouseEnter(e);
      showTooltip(e.currentTarget, info);
    },
    onMouseLeave: (e) => {
      p.onMouseLeave && p.onMouseLeave(e);
      hideTooltip(e.currentTarget);
    },
    onFocus: (e) => {
      p.onFocus && p.onFocus(e);
      if (e.currentTarget.matches(":focus-visible")) showTooltip(e.currentTarget, info, 0);
    },
    onBlur: (e) => {
      p.onBlur && p.onBlur(e);
      hideTooltip(e.currentTarget);
    },
  });
}
