// One tooltip element for the whole app, moved next to whatever is hovered or
// keyboard focused. Used by the <Tooltip> wrapper and by map markers.

let node = null;
let timer = null;
let current = null;
let lastHidden = 0;

function ensureNode() {
  if (!node) {
    node = document.createElement("div");
    node.className = "tooltip";
    node.setAttribute("role", "tooltip");
    node.dataset.visible = "false";
    document.body.appendChild(node);
    // Anything that moves the page hides it.
    window.addEventListener("scroll", () => hideTooltip(), true);
    window.addEventListener("pointerdown", () => hideTooltip(), true);
    window.addEventListener("keydown", (e) => e.key === "Escape" && hideTooltip(), true);
  }
  return node;
}

function place(el, target) {
  const r = target.getBoundingClientRect();
  el.style.transform = "translate(0px, 0px)";
  const t = el.getBoundingClientRect();
  let top = r.bottom + 8;
  if (top + t.height > window.innerHeight - 8) top = r.top - t.height - 8;
  let left = r.left + r.width / 2 - t.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - t.width - 8));
  el.style.transform = "translate(" + Math.round(left) + "px, " + Math.round(top) + "px)";
}

/** Shows { label, shortcut } next to target after a short wait. Moving between
    neighbours shows the next one at once, like Notion. */
export function showTooltip(target, info, delay) {
  if (!target || !info || !info.label) return;
  clearTimeout(timer);
  current = target;
  const wait = delay ?? (Date.now() - lastHidden < 400 ? 0 : 450);
  timer = setTimeout(() => {
    if (current !== target || !target.isConnected) return;
    const el = ensureNode();
    el.textContent = "";
    const main = document.createElement("span");
    main.textContent = info.label;
    el.appendChild(main);
    if (info.shortcut) {
      const hint = document.createElement("span");
      hint.className = "tooltip-shortcut";
      hint.textContent = info.shortcut;
      el.appendChild(hint);
    }
    el.dataset.visible = "true";
    place(el, target);
  }, wait);
}

/** Hides the tooltip. With a target, only if it belongs to that target. */
export function hideTooltip(target) {
  if (target && current !== target) return;
  clearTimeout(timer);
  if (current && node && node.dataset.visible === "true") lastHidden = Date.now();
  current = null;
  if (node) node.dataset.visible = "false";
}
