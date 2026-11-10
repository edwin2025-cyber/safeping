import { useEffect, useRef, useState } from "react";
import { copyRich, copyText } from "../lib/clipboard.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";

/** Button that copies text and says "Copied" in place for a moment. With getHtml it also
    copies a formatted table, for pasting into Excel, Word or email. */
export default function CopyButton({ getText, getHtml, label = "Copy", variant = "secondary" }) {
  const [state, setState] = useState("idle"); // idle, copied, failed
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function onClick() {
    try {
      if (getHtml) await copyRich(getText(), getHtml());
      else await copyText(getText());
      setState("copied");
    } catch {
      setState("failed");
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  }

  return (
    <button type="button" className={"btn btn-" + variant} onClick={onClick}>
      {state === "copied" ? <Icon icon={icons.acknowledged} className="copy-ok" /> : <Icon icon={icons.copy} />}
      <span aria-live="polite">{state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label}</span>
    </button>
  );
}
