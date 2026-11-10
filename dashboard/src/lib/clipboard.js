// The Clipboard API only works on https or localhost. On a plain http address
// (the laptop's IP on school WiFi) fall back to the older copy command.
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  const active = document.activeElement;
  area.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(area);
  if (active && active.focus) active.focus();
  if (!ok) throw new Error("copy failed");
}

/** Copies plain text and a formatted (HTML) version together. Excel, Word and email paste the
    formatted table; a text message or Notepad gets the plain lines, unchanged. Works on http too:
    there the copy command fills both formats through the copy event. */
export async function copyRich(text, html) {
  if (!html) return copyText(text);
  if (navigator.clipboard && window.isSecureContext && window.ClipboardItem) {
    try {
      await navigator.clipboard.write([
        new window.ClipboardItem({
          "text/plain": new Blob([text], { type: "text/plain" }),
          "text/html": new Blob([html], { type: "text/html" }),
        }),
      ]);
      return;
    } catch {
      // Some browsers refuse HTML here: try the copy event below.
    }
  }
  let filled = false;
  const onCopy = (event) => {
    event.clipboardData.setData("text/plain", text);
    event.clipboardData.setData("text/html", html);
    event.preventDefault();
    filled = true;
  };
  document.addEventListener("copy", onCopy, { once: true });
  const ok = document.execCommand("copy");
  document.removeEventListener("copy", onCopy);
  if (!ok || !filled) await copyText(text);
}
