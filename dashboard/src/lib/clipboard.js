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
