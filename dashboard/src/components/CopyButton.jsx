import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { copyText } from "../lib/clipboard.js";

/** Neutral button that copies text and says "Copied" in place for a moment. */
export default function CopyButton({ getText, label = "Copy" }) {
  const [state, setState] = useState("idle"); // idle, copied, failed
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function onClick() {
    try {
      await copyText(getText());
      setState("copied");
    } catch {
      setState("failed");
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  }

  return (
    <button type="button" className="btn copy-btn" onClick={onClick}>
      {state === "copied" ? (
        <Check size={16} aria-hidden="true" className="copy-ok" />
      ) : (
        <Copy size={16} aria-hidden="true" />
      )}
      <span aria-live="polite">
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label}
      </span>
    </button>
  );
}
