import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Centered dialog over a blurred, dimmed page. Esc, the backdrop or onClose
    closes it. Focus stays inside while open and goes back when it closes:
    to returnFocus() if that finds something, otherwise to what had focus before. */
export default function Modal({ onClose, labelledBy, className = "", returnFocus, children }) {
  const dialogRef = useRef(null);
  const [opener] = useState(() => document.activeElement);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const returnRef = useRef(returnFocus);
  returnRef.current = returnFocus;

  useEffect(() => {
    if (dialogRef.current) dialogRef.current.focus();
    function onKey(event) {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        onCloseRef.current();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      requestAnimationFrame(() => {
        const handled = returnRef.current && returnRef.current();
        if (!handled && opener && opener.isConnected && opener.focus) opener.focus();
      });
    };
  }, [opener]);

  function trapFocus(event) {
    if (event.key !== "Tab") return;
    const items = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE)).filter(
      (el) => el.offsetParent !== null || el === document.activeElement,
    );
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === dialogRef.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return createPortal(
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={"modal " + className}
        onKeyDown={trapFocus}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
