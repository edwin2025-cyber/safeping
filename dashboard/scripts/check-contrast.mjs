// WCAG contrast check for every text-on-background pair the dashboard uses.
// Reads the real values from src/styles/tokens.css, in both themes.
// Run: npm.cmd run contrast   (exits with code 1 if a required pair fails)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(fileURLToPath(new URL("../src/styles/tokens.css", import.meta.url)), "utf8");

/** Blend a color with alpha over a solid background. */
function over([r, g, b, a], [br, bg, bb]) {
  return [r * a + br * (1 - a), g * a + bg * (1 - a), b * a + bb * (1 - a)];
}

/** Tokens of one theme. An rgba token (like surface-hover, 3% black) is checked as it
    looks on the page. Some pairs sit on other surfaces; those get their own blended
    tokens below (panel-hover, overlay-hover). */
function readTheme(name) {
  const raw = {};
  const blocks = css.matchAll(/([^{}]+)\{([^}]*)\}/g);
  for (const [, selector, body] of blocks) {
    if (!selector.includes(`data-theme="${name}"`)) continue;
    for (const [, key, r, g, b, a] of body.matchAll(/--color-([a-z0-9-]+):\s*rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/g)) {
      raw[key] = [Number(r), Number(g), Number(b), a === undefined ? 1 : Number(a)];
    }
  }
  const tokens = {};
  for (const [key, c] of Object.entries(raw)) tokens[key] = c[3] === 1 ? c.slice(0, 3) : over(c, raw.page);
  if (raw["surface-hover"]) {
    tokens["panel-hover"] = over(raw["surface-hover"], raw.panel); // a stat tile under the pointer
    tokens["overlay-hover"] = over(raw["surface-hover"], raw["surface-overlay"]); // a feed or menu row in a panel
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
// kind "text" needs 4.5:1, kind "ui" (icons, shapes and borders that carry meaning) needs 3:1.
// kind "info" is printed but never fails (decoration, or a fill with its number next to it).
//
// Choices made so every pair passes (see docs/dashboard.md, Look and colors):
// - The Live count in the sidebar uses text-subtle, not text-subtlest (3.7:1 on the selected row).
// - The active row in Find a student uses surface-hover, not surface-selected (the gold icon
//   is 2.7:1 on surface-selected in light).
// - Switch tracks (off) use text-subtlest, not border-bold.
// - Map marker icons are white in light and the Midnight page color in dark (a white icon
//   is under 3:1 on the dark-theme type colors).
// - Only Medical and Silent words are ever colored as text (the Suspicious yellow is far under 4.5:1 in light).
// - Cluster rings use text-subtlest, not border-bold (2.82:1 on light OpenStreetMap tiles).
// - Suspicious (v6): the fill is the Fob LED yellow #FFC300, about 1.6:1 on white. It is
//   checked as info only (chart bars, marker discs, map dots: they also have an icon, a word
//   and a position). Suspicious icons on their own use type-suspicious-icon (deep amber), and
//   the icon inside a yellow marker uses marker-icon-suspicious (near black).
const TYPES = ["type-medical", "type-suspicious-icon", "type-silent", "type-status"]; // as icons
const FILLS = ["type-medical", "type-silent", "type-status"]; // marker discs with marker-icon
const PAIRS = [];

// Neutral text on every surface it sits on
for (const bg of ["page", "sidebar", "surface", "surface-raised", "surface-overlay", "surface-hover", "panel", "panel-hover", "overlay-hover"]) {
  for (const fg of ["text", "text-subtle", "text-subtlest"]) PAIRS.push([fg, bg, "text", "neutral text"]);
}
for (const fg of ["text", "text-subtle"]) {
  PAIRS.push([fg, "surface-selected", "text", "selected row, tab, segment, Settings nav"]);
  PAIRS.push([fg, "sidebar-selected", "text", "selected sidebar row and its Live count"]);
}
for (const fg of ["text", "text-subtle", "text-subtlest"]) {
  PAIRS.push([fg, "sidebar-hover", "text", "sidebar row hover (Ctrl+K hint and account note are subtlest)"]);
}
PAIRS.push(["text", "avatar", "text", "initials in the account circle"]);
PAIRS.push(["avatar", "sidebar-hover", "info", "account circle on the hovered row (it also has a 1 px ring)"]);
PAIRS.push(["text", "surface-hover-strong", "text", "pressed icon button"]);
PAIRS.push(["text", "surface-pressed", "text", "pressed button"]);
PAIRS.push(["border-raised", "page", "info", "border of tiles, chart panels, map controls"]);
PAIRS.push(["border-overlay", "page", "info", "border of Peek, Settings, menus, palette"]);

// Type icons on their own (legends, search, Overview lines, the filter menu): 3:1 on every background they sit on.
for (const t of TYPES) {
  for (const bg of ["page", "surface-raised", "surface-overlay", "surface-hover", "panel", "panel-hover", "overlay-hover"]) {
    PAIRS.push([t, bg, "ui", "type icon, legend"]);
  }
}
for (const t of FILLS) PAIRS.push(["marker-icon", t, "ui", "map marker icon on its disc"]);
PAIRS.push(["marker-icon-suspicious", "type-suspicious", "ui", "map marker icon on the yellow disc"]);
// Type and link tags: icon and word in a darker shade on a tint of the same color
for (const t of ["medical", "suspicious", "silent"]) PAIRS.push([`tag-${t}-text`, `tag-${t}-bg`, "text", "type tag"]);
PAIRS.push(["gray-text", "gray-subtler", "text", "Status and LoRa tags"]);
PAIRS.push(["wifi-text", "wifi-bg", "text", "WiFi tag (dark gray)"]);
PAIRS.push(["lora-text", "lora-bg", "text", "LoRa tag (middle gray)"]);
PAIRS.push(["unknown-text", "unknown-bg", "text", "Unknown tag (light gray)"]);
// Busy hours: one blue from faint to deep. A sequential scale starts near the background on
// purpose; the bar height and the tooltip and table give the count. The deepest step must stand out.
for (const n of [1, 2, 3, 4, 5]) PAIRS.push([`heat-${n}`, "panel", "info", "Busy hours shade " + n]);
PAIRS.push(["heat-6", "panel", "ui", "Busy hours deepest shade (the busiest hour)"]);
PAIRS.push(["bar-empty", "panel", "info", "Busy hours empty hour (a dash; the tooltip and table give 0)"]);
// Open status and the Mock data tag: magenta
PAIRS.push(["magenta-text", "magenta-bg", "text", "Mock data tag"]);
// Custom date calendar: days in a range, today's number, and the picked ends
for (const bg of ["blue-subtlest", "blue-subtler"]) PAIRS.push(["text", bg, "text", "calendar day inside a range"]);
PAIRS.push(["blue-text", "surface-overlay", "text", "calendar: today's number"]);
// Alert panel: Review cameras icon tile and the timeline dots
PAIRS.push(["camera-text", "camera-bg", "ui", "Review cameras icon (blue)"]);
PAIRS.push(["orange-text", "orange-subtler", "text", "empty dashboard preview banner"]);
PAIRS.push(["text-subtle", "surface-overlay", "ui", "timeline step done (filled dot)"]);
PAIRS.push(["text-subtlest", "surface-overlay", "ui", "timeline step not yet (ring)"]);
// Colored type words (urgent counts on Overview tiles) and the rose Urgent open number
for (const t of ["type-medical", "type-silent"]) {
  for (const bg of ["panel", "panel-hover"]) PAIRS.push([t, bg, "text", "urgent type word or number on a tile"]);
}
PAIRS.push(["type-suspicious", "panel", "info", "Suspicious fill: map marker and dot, never text or a lone icon"]);
// Alerts chart bars (own tokens: type colors in light, a calmer set in dark). The yellow is the accepted fail in light.
for (const t of ["chart-medical", "chart-silent"]) PAIRS.push([t, "panel", "ui", "Alerts chart bar"]);
PAIRS.push(["chart-suspicious", "panel", "info", "Alerts chart bar, Suspicious yellow"]);

// Sidebar
PAIRS.push(["red-on-bold", "red-bold", "text", "Live count pill when an urgent alert is open"]);
for (const dot of ["green-bold", "orange-bold"]) PAIRS.push([dot, "sidebar", "ui", "server status dot"]);
PAIRS.push(["blue-bold", "page", "ui", "Split view divider while dragging"]);
PAIRS.push(["focus-ring", "sidebar", "ui", "focus ring in the sidebar"]);

// Overview
PAIRS.push(["orange-text", "panel", "text", "Today tile when today is twice the usual"]);
PAIRS.push(["orange-text", "panel-hover", "text", "Today tile on hover"]);
PAIRS.push(["gray-bold", "panel", "ui", "previous period dashed line"]);
PAIRS.push(["green-bold", "panel", "ui", "Recent activity: acknowledged check"]);
PAIRS.push(["gray-bold", "panel", "ui", "Recent activity: resolved check"]);
PAIRS.push(["border-bold", "panel", "info", "chart guide line"]);

// Primary button
PAIRS.push(["blue-on-bold", "blue-bold", "text", "primary button"]);
PAIRS.push(["blue-on-bold", "blue-bold-hovered", "text", "primary button hover"]);
PAIRS.push(["blue-on-bold", "blue-bold-pressed", "text", "primary button pressed"]);
// Links
PAIRS.push(["blue-text", "surface-raised", "text", "attribution link on the map"]);
PAIRS.push(["blue-text", "surface-overlay", "text", "Open in Google Maps in the Peek"]);
PAIRS.push(["blue-text", "surface-hover", "text", "docs link in the empty places note"]);
PAIRS.push(["blue-text", "page", "text", "Live filter icon when a filter is on"]);
// Colored words
PAIRS.push(["orange-text", "surface-overlay", "text", "error in the Peek, Health rows"]);
PAIRS.push(["orange-text", "page", "text", "Devices summary problem part, top bar Server not reachable"]);
PAIRS.push(["red-text", "surface-overlay", "text", "Health: rejected messages with an attack"]);
// Tooltips
PAIRS.push(["tooltip-text", "tooltip-bg", "text", "tooltip"]);
PAIRS.push(["tooltip-subtle", "tooltip-bg", "text", "tooltip shortcut hint"]);
// Icons and shapes that carry meaning
PAIRS.push(["green-text", "surface-overlay", "ui", "Copied check icon"]);
for (const bg of ["page", "sidebar", "surface", "surface-raised", "surface-overlay"]) PAIRS.push(["focus-ring", bg, "ui", "focus ring"]);
for (const bg of ["page", "surface-overlay"]) {
  PAIRS.push(["text-subtlest", bg, "ui", "switch track (off)"]);
  PAIRS.push(["blue-bold", bg, "ui", "switch track (on)"]);
}
// Status dots next to their word
for (const bg of ["page", "surface-hover", "surface-selected", "surface-overlay", "sidebar"]) {
  for (const dot of ["open", "green-bold", "gray-bold"]) PAIRS.push([dot, bg, "ui", "status dot (Open is teal)"]);
}
// Battery: the word tags carry the meaning (the number is next to them too), so they must pass as text.
// The bars are a visual aid: a yellow that reads as yellow cannot reach 3:1 on white.
for (const lvl of ["good", "low", "critical"]) {
  for (const bg of ["page", "surface-hover", "surface-overlay", "panel", "panel-hover"]) PAIRS.push([`battery-${lvl}-text`, bg, "text", "battery word and low battery count"]);
  for (const bg of ["page", "surface-hover", "surface-selected", "surface-overlay"]) {
    PAIRS.push([`battery-${lvl}`, bg, "info", "battery bar (the number and word give the level)"]);
  }
}

// Map strokes and dots on the tiles. Tile colors are APPROXIMATE land colors
// (Positron about 250,250,248, OpenStreetMap about 242,239,233, Dark Matter about 14,14,14).
const TILES = {
  light: { "tile-positron": [250, 250, 248], "tile-osm": [242, 239, 233] },
  dark: { "tile-dark-matter": [14, 14, 14] },
};
const MAP_STROKES = [...FILLS, "text-subtlest"];

let failed = 0;
for (const theme of ["light", "dark"]) {
  const t = { ...readTheme(theme), ...TILES[theme] };
  const pairs = [...PAIRS];
  for (const tile of Object.keys(TILES[theme])) {
    for (const stroke of MAP_STROKES) pairs.push([stroke, tile, "ui", "marker disc, circle, Overview dot or cluster ring (approx. tile)"]);
    pairs.push(["type-suspicious", tile, "info", "yellow marker disc, circle or Overview dot (the accepted fail in light)"]);
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
