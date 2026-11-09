import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const ITEMS = '[role="menuitem"]:not([aria-disabled="true"]), [role="menuitemradio"], [role="menuitemcheckbox"]';

/** A small floating menu next to an anchor element. Closes on Esc, on a click
    outside, or when an item is picked. Arrow keys move between items. */
export default function Popover({ anchor, open, onClose, label, placement = "bottom-start", children, className = "" }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useLayoutEffect(() => {
    if (!open || !anchor || !ref.current) return;
    const a = anchor.getBoundingClientRect();
    const p = ref.current.getBoundingClientRect();
    let top = placement.startsWith("top") ? a.top - p.height - 4 : a.bottom + 4;
    if (top + p.height > window.innerHeight - 8) top = Math.max(8, a.top - p.height - 4);
    if (top < 8) top = 8;
    let left = placement.endsWith("end") ? a.right - p.width : a.left;
    left = Math.max(8, Math.min(left, window.innerWidth - p.width - 8));
    setPos({ top: Math.round(top), left: Math.round(left) });
  }, [open, anchor, placement]);

  useEffect(() => {
    if (!open) return undefined;
    const first = ref.current && (ref.current.querySelector('[aria-checked="true"]') || ref.current.querySelector(ITEMS));
    if (first) first.focus();
    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current(true);
      }
    }
    function onDown(event) {
      if (ref.current && !ref.current.contains(event.target) && !(anchor && anchor.contains(event.target))) {
        onCloseRef.current(false);
      }
    }
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onDown, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onDown, true);
    };
  }, [open, anchor]);

  // Give focus back to the button that opened the menu.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (wasOpen.current && !open && anchor && document.activeElement === document.body) anchor.focus();
    wasOpen.current = open;
  }, [open, anchor]);

  if (!open) return null;

  function onKeyDown(event) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const items = Array.from(ref.current.querySelectorAll(ITEMS));
    const i = items.indexOf(document.activeElement);
    const next = event.key === "ArrowDown" ? items[(i + 1) % items.length] : items[(i - 1 + items.length) % items.length];
    if (next) next.focus();
  }

  return createPortal(
    <div
      ref={ref}
      role="menu"
      aria-label={label}
      className={"popover " + className}
      style={pos ? { top: pos.top, left: pos.left } : { top: 0, left: 0, visibility: "hidden" }}
      onKeyDown={onKeyDown}
    >
      {children}
    </div>,
    document.body,
  );
}
