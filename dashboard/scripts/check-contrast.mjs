// WCAG contrast check for every text-on-background pair the dashboard uses.
// Reads the real values from src/styles/tokens.css, in both themes.
// Run: npm run contrast   (exits with code 1 if a required pair fails)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(fileURLToPath(new URL("../src/styles/tokens.css", import.meta.url)), "utf8");

function readTheme(name) {
  const tokens = {};
  const blocks = css.matchAll(/([^{}]+)\{([^}]*)\}/g);
  for (const [, selector, body] of blocks) {
    if (!selector.includes(`data-theme="${name}"`)) continue;
    for (const [, key, r, g, b] of body.matchAll(/--color-([a-z-]+):\s*rgba?\((\d+),\s*(\d+),\s*(\d+)/g)) {
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
//
// Changes made after the first run (see docs/dashboard.md):
// - Open MEDICAL card: time ago uses text-subtle, not text-subtlest (4.48:1 in light).
// - Open MEDICAL card border uses red-bold, not red-border (2.78 light, 2.87 dark).
// - Switch track and checkbox borders use text-subtlest, not border-bold (2.85 dark).
// - SUSPICIOUS dashed circle uses yellow-text in light, not yellow-border (1.91 on tiles).
// - text-subtlest is never placed on surface-pressed (pressed buttons use text).
const PAIRS = [];
for (const bg of ["page", "sidebar", "surface", "surface-raised", "surface-hover"]) {
  for (const fg of ["text", "text-subtle", "text-subtlest"]) {
    PAIRS.push([fg, bg, "text", "neutral text"]);
  }
}
PAIRS.push(["text", "surface-pressed", "text", "pressed neutral button"]);
// Open MEDICAL card (whole card is red-subtlest)
for (const fg of ["text", "text-subtle"]) {
  PAIRS.push([fg, "red-subtlest", "text", "open MEDICAL card"]);
}
// Lozenges and status pills: <color>-text on <color>-subtler
for (const c of ["red", "yellow", "purple", "gray", "green", "orange", "blue", "teal"]) {
  PAIRS.push([`${c}-text`, `${c}-subtler`, "text", "lozenge / pill"]);
}
// Primary (blue bold) button
PAIRS.push(["blue-on-bold", "blue-bold", "text", "primary button"]);
PAIRS.push(["blue-on-bold", "blue-bold-hovered", "text", "primary button hover"]);
PAIRS.push(["blue-on-bold", "blue-bold-pressed", "text", "primary button pressed"]);
// Selected nav item, links
PAIRS.push(["blue-text", "blue-subtlest", "text", "selected nav item"]);
PAIRS.push(["blue-text", "surface-raised", "text", "link in peek"]);
// Colored words on neutral surfaces
PAIRS.push(["yellow-text", "surface-raised", "text", "Review cameras title"]);
PAIRS.push(["green-text", "surface-raised", "text", "Copied confirmation"]);
PAIRS.push(["orange-text", "surface", "text", "low battery word"]);
PAIRS.push(["red-text", "surface", "text", "very low battery word"]);
PAIRS.push(["orange-text", "surface-raised", "text", "action error message in peek"]);
PAIRS.push(["orange-text", "page", "text", "settings note"]);
// Map markers: type icon on the marker fill
for (const c of ["red", "yellow", "purple", "gray"]) {
  PAIRS.push([`${c}-on-bold`, `${c}-bold`, "ui", "map marker icon"]);
}
// Shapes and borders that carry meaning
for (const bg of ["page", "surface", "surface-raised", "sidebar"]) {
  PAIRS.push(["focus-ring", bg, "ui", "focus ring"]);
}
PAIRS.push(["red-bold", "page", "ui", "open MEDICAL card border"]);
PAIRS.push(["text-subtlest", "surface", "ui", "switch track (off), checkbox border"]);
PAIRS.push(["text-subtlest", "surface-raised", "ui", "switch track (off) in peek"]);
PAIRS.push(["blue-bold", "surface", "ui", "switch track (on), selected option"]);
PAIRS.push(["gray-bold", "surface", "ui", "battery bar"]);
PAIRS.push(["orange-bold", "surface", "ui", "battery bar, below 20 percent"]);
PAIRS.push(["red-bold", "surface", "ui", "battery bar, below 10 percent"]);

// Map circle strokes on the tiles. Tile colors are APPROXIMATE land colors
// (Positron about 250,250,248, OpenStreetMap about 242,239,233, Dark Matter about 14,14,14).
const TILES = {
  light: { "tile-positron": [250, 250, 248], "tile-osm": [242, 239, 233] },
  dark: { "tile-dark-matter": [14, 14, 14] },
};
const ZONE_STROKES = {
  light: ["red-bold", "purple-bold", "gray-bold", "yellow-text"],
  dark: ["red-bold", "purple-bold", "gray-bold", "yellow-border"],
};

let failed = 0;
for (const theme of ["light", "dark"]) {
  const t = { ...readTheme(theme), ...TILES[theme] };
  const pairs = [...PAIRS];
  for (const tile of Object.keys(TILES[theme])) {
    for (const stroke of ZONE_STROKES[theme]) pairs.push([stroke, tile, "ui", "map circle stroke (approx. tile)"]);
  }
  console.log(`\n${theme.toUpperCase()} theme`);
  for (const [fg, bg, kind, where] of pairs) {
    if (!t[fg] || !t[bg]) {
      console.log(`  MISSING token ${!t[fg] ? fg : bg}`);
      failed += 1;
      continue;
    }
    const r = ratio(t[fg], t[bg]);
    const need = kind === "text" ? 4.5 : 3;
    const ok = r >= need;
    if (!ok) failed += 1;
    const line = `${ok ? "pass" : "FAIL"}  ${r.toFixed(2).padStart(5)}:1 (need ${need})  ${fg} on ${bg}  [${where}]`;
    console.log("  " + line);
  }
}
console.log(failed ? `\n${failed} pair(s) failed.` : "\nAll pairs pass.");
process.exit(failed ? 1 : 0);
