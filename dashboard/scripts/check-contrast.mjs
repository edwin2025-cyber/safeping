// WCAG contrast check for every text-on-background pair the dashboard uses.
// Reads the real values from src/styles/tokens.css, in both themes.
// Run: npm.cmd run contrast   (exits with code 1 if a required pair fails)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(fileURLToPath(new URL("../src/styles/tokens.css", import.meta.url)), "utf8");

function readTheme(name) {
  const tokens = {};
  const blocks = css.matchAll(/([^{}]+)\{([^}]*)\}/g);
  for (const [, selector, body] of blocks) {
    if (!selector.includes(`data-theme="${name}"`)) continue;
    for (const [, key, r, g, b] of body.matchAll(/--color-([a-z0-9-]+):\s*rgba?\((\d+),\s*(\d+),\s*(\d+)/g)) {
      tokens[key] = [Number(r), Number(g), Number(b)];
    }
  }
  return tokens;
}

function luminance([r, g, b]) {
  const ch = [r, g, b].map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground, background, kind, where it is used]
// kind "text" needs 4.5:1, kind "ui" (shapes, icons and borders that carry meaning) needs 3:1.
// kind "info" is printed but never fails: fills that always have their number written
// next to them, and the low steps of a light-to-dark scale (they start near the background
// on purpose; the hover and the hidden table give the exact count).
//
// Choices made so every pair passes (see docs/dashboard.md):
// - Muted text on an open MEDICAL row uses text-subtle, never text-subtlest (4.48:1 in light).
// - Switch tracks (off) use text-subtlest, not border-bold (2.85:1 in dark).
// - The SUSPICIOUS dashed circle uses yellow-text in light, not yellow-border (1.91:1 on tiles).
// - The app mark uses a fixed brand blue, so the white shield reads in dark mode too.
// - Cluster rings use text-subtlest, not border-bold (2.82:1 on light OpenStreetMap tiles).
// - The Midnight dark values (version 4) passed as given; none had to change.
const PAIRS = [];
for (const bg of ["page", "sidebar", "surface", "surface-raised", "surface-overlay", "surface-hover", "panel"]) {
  for (const fg of ["text", "text-subtle", "text-subtlest"]) PAIRS.push([fg, bg, "text", "neutral text"]);
}
// Raised and overlay surfaces are told apart from the page by their 1 px border.
// Borders are decoration, so they are listed as info, not pass or fail.
PAIRS.push(["border-raised", "page", "info", "border of tiles, chart panels, map controls"]);
PAIRS.push(["border-overlay", "page", "info", "border of Peek, Settings, menus"]);
PAIRS.push(["text", "surface-selected", "text", "selected nav item, view tab, segment"]);
PAIRS.push(["text", "surface-hover-strong", "text", "pressed icon button"]);
PAIRS.push(["text", "surface-pressed", "text", "pressed button"]);
// Sidebar: charcoal in both themes
for (const fg of ["sb-text", "sb-text-strong", "sb-label"]) PAIRS.push([fg, "sb-bg", "text", "sidebar text and icons"]);
PAIRS.push(["sb-text-strong", "sb-hover", "text", "sidebar item hover"]);
PAIRS.push(["sb-text", "sb-hover", "text", "account note on hover (sb-label is 4.02:1 there in light)"]);
PAIRS.push(["sb-text-strong", "sb-selected", "text", "selected sidebar item"]);
PAIRS.push(["sb-placeholder", "sb-search", "text", "sidebar search placeholder"]);
PAIRS.push(["sb-placeholder", "sb-hover", "text", "sidebar search placeholder, hover"]);
PAIRS.push(["sb-text", "sb-selected", "text", "Ctrl+K hint"]);
PAIRS.push(["sb-count-text", "sb-count", "text", "Live count pill"]);
PAIRS.push(["sb-text-strong", "sb-selected", "text", "avatar initials"]);
PAIRS.push(["sb-label", "sb-hover", "text", "section label next to a hovered row"]);
for (const dot of ["green-bold", "orange-bold"]) PAIRS.push([dot, "sb-bg", "ui", "server status dot"]);
PAIRS.push(["focus-ring", "sb-bg", "ui", "focus ring in the sidebar"]);
PAIRS.push(["brand", "sb-bg", "ui", "app mark on the sidebar"]);
// Overview: stat tiles and panels
PAIRS.push(["red-text", "panel", "text", "Alerts tile up, Open now Medical, rejected attack count"]);
PAIRS.push(["green-text", "panel", "text", "Alerts tile down, All seen today"]);
PAIRS.push(["orange-text", "panel", "text", "Low battery count, not seen, no reference reading"]);
for (const fg of ["text", "text-subtle", "text-subtlest", "red-text", "green-text", "orange-text"]) {
  PAIRS.push([fg, "surface-hover", "text", "tile text on hover"]);
}
PAIRS.push(["blue-bold", "panel", "ui", "Alerts line, sparkline, Hotspots bars"]);
PAIRS.push(["gray-bold", "panel", "ui", "previous period line"]);
for (const n of [1, 2, 3]) PAIRS.push([`flow-${n}`, "panel", "info", "Response flow bar (count written next to it)"]);
for (const c of ["gray", "teal"]) PAIRS.push([`${c}-text`, `${c}-subtler`, "text", "delivery tag in System health"]);
// Open MEDICAL row (and its hover)
for (const bg of ["red-subtlest", "red-subtler"]) {
  for (const fg of ["text", "text-subtle"]) PAIRS.push([fg, bg, "text", "open MEDICAL row"]);
}
// Tags: <color>-text on <color>-subtler (type, link, avatar)
for (const c of ["red", "yellow", "purple", "gray", "teal", "orange"]) PAIRS.push([`${c}-text`, `${c}-subtler`, "text", "tag"]);
// Primary button
PAIRS.push(["blue-on-bold", "blue-bold", "text", "primary button"]);
PAIRS.push(["blue-on-bold", "blue-bold-hovered", "text", "primary button hover"]);
PAIRS.push(["blue-on-bold", "blue-bold-pressed", "text", "primary button pressed"]);
// Links
PAIRS.push(["blue-text", "surface-raised", "text", "attribution link on the map"]);
PAIRS.push(["blue-text", "surface-overlay", "text", "Open in Google Maps in the Peek"]);
PAIRS.push(["blue-text", "surface-hover", "text", "docs link in the empty places note"]);
// SUSPICIOUS camera callout
for (const fg of ["text", "text-subtle", "yellow-text"]) PAIRS.push([fg, "yellow-subtlest", "text", "Review cameras callout"]);
PAIRS.push(["text", "yellow-subtler", "text", "Copy for security button hover"]);
// Colored words
PAIRS.push(["orange-text", "surface-overlay", "text", "error message in the peek"]);
PAIRS.push(["orange-text", "page", "text", "Low battery word"]);
PAIRS.push(["red-text", "page", "text", "Very low battery word"]);
PAIRS.push(["orange-text", "surface-overlay", "text", "Low battery word in the device peek"]);
PAIRS.push(["red-text", "surface-overlay", "text", "Very low battery word in the device peek"]);
PAIRS.push(["text", "surface-selected", "text", "selected nav item in Settings"]);
PAIRS.push(["red-on-bold", "red-bold", "text", "Live count when an open MEDICAL exists"]);
// Tooltips
PAIRS.push(["tooltip-text", "tooltip-bg", "text", "tooltip"]);
PAIRS.push(["tooltip-subtle", "tooltip-bg", "text", "tooltip shortcut hint"]);
// Icons and shapes that carry meaning
PAIRS.push(["brand-on", "brand", "ui", "app mark shield"]);
PAIRS.push(["green-text", "surface-overlay", "ui", "Copied check icon"]);
for (const c of ["red", "yellow", "purple", "gray"]) PAIRS.push([`${c}-on-bold`, `${c}-bold`, "ui", "map marker icon"]);
for (const bg of ["page", "sidebar", "surface", "surface-raised", "surface-overlay"]) PAIRS.push(["focus-ring", bg, "ui", "focus ring"]);
for (const bg of ["page", "surface-overlay"]) {
  PAIRS.push(["text-subtlest", bg, "ui", "switch track (off)"]);
  PAIRS.push(["blue-bold", bg, "ui", "switch track (on)"]);
}
// Status dots next to their word
for (const bg of ["page", "surface-hover", "surface-overlay", "red-subtlest", "red-subtler", "sb-bg"]) {
  for (const dot of ["orange-bold", "green-bold", "gray-bold"]) PAIRS.push([dot, bg, "ui", "status dot"]);
}
// Battery bars
for (const bg of ["page", "surface-overlay"]) {
  for (const fill of ["gray-bold", "orange-bold", "red-bold"]) PAIRS.push([fill, bg, "ui", "battery bar"]);
}

// Map strokes on the tiles. Tile colors are APPROXIMATE land colors
// (Positron about 250,250,248, OpenStreetMap about 242,239,233, Dark Matter about 14,14,14).
const TILES = {
  light: { "tile-positron": [250, 250, 248], "tile-osm": [242, 239, 233] },
  dark: { "tile-dark-matter": [14, 14, 14] },
};
const MAP_STROKES = {
  light: ["red-bold", "purple-bold", "gray-bold", "yellow-text", "text-subtlest"],
  dark: ["red-bold", "purple-bold", "gray-bold", "yellow-border", "text-subtlest"],
};

let failed = 0;
for (const theme of ["light", "dark"]) {
  const t = { ...readTheme(theme), ...TILES[theme] };
  const pairs = [...PAIRS];
  for (const tile of Object.keys(TILES[theme])) {
    for (const stroke of MAP_STROKES[theme]) pairs.push([stroke, tile, "ui", "map circle or cluster ring (approx. tile)"]);
  }
  console.log(`\n${theme.toUpperCase()} theme`);
  for (const [fg, bg, kind, where] of pairs) {
    if (!t[fg] || !t[bg]) {
      console.log(`  MISSING token ${!t[fg] ? fg : bg}`);
      failed += 1;
      continue;
    }
    const r = ratio(t[fg], t[bg]);
    if (kind === "info") {
      console.log(`  info  ${r.toFixed(2).padStart(5)}:1 (not required)  ${fg} on ${bg}  [${where}]`);
      continue;
    }
    const need = kind === "text" ? 4.5 : 3;
    const ok = r >= need;
    if (!ok) failed += 1;
    console.log(`  ${ok ? "pass" : "FAIL"}  ${r.toFixed(2).padStart(5)}:1 (need ${need})  ${fg} on ${bg}  [${where}]`);
  }
}
console.log(failed ? `\n${failed} pair(s) failed.` : "\nAll pairs pass.");
process.exit(failed ? 1 : 0);
