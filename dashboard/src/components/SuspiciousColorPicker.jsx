// TEMPORARY: "Suspicious color (for testing)" in Settings > Appearance > Development.
// Everything for it is in this file, src/components/suspiciousColor.css and src/lib/colorTools.js.
// To remove it later, delete those three files and:
//   - in src/main.jsx, the applySavedSuspiciousColor import and its call
//   - in src/components/SettingsModal.jsx, the suspiciousColorRow import and its line in buildRows
// Two small fallbacks stay useful after that and can be kept or removed:
//   - src/styles/base.css: .type-icon--suspicious reads --color-type-suspicious-icon first
//   - src/components/map.css: .alert-marker--suspicious reads --color-marker-icon-suspicious first
// Without an override both fall back to the old variables, so nothing changes.
import { useMemo, useRef, useState } from "react";
import {
  clamp,
  contrast,
  hsvToRgb,
  oklabDistance,
  parseHex,
  reachContrast,
  rgbToHsv,
  tint,
  toCssRgb,
  toHex,
} from "../lib/colorTools.js";
import { icons } from "../lib/icons.js";
import CopyButton from "./CopyButton.jsx";
import Icon from "./Icon.jsx";
import { TypeIcon, TypeTag } from "./Tags.jsx";
import "./suspiciousColor.css";

const KEY = "safeping.suspiciousColorTest";
const STYLE_ID = "suspicious-color-test";
const SUGGESTED = "#EBC20C"; // the Fob LED yellow, as a starting point
const DEFAULT_HEX = "#FFC300"; // the Suspicious fill in tokens.css (v6), shown when nothing is picked
const TOO_CLOSE = 0.1; // OKLab distance: under this, warn
const A_BIT_CLOSE = 0.15; // under this, a softer note

// The neutrals and the other type fills of each theme, copied from src/styles/tokens.css.
// Used for the contrast numbers and to draw both previews side by side.
const THEMES = {
  light: {
    label: "Light",
    page: [255, 255, 255],
    panel: [255, 255, 255],
    panelBorder: [221, 222, 225],
    text: [30, 31, 33],
    subtle: [80, 82, 88],
    subtlest: [107, 110, 118],
    hover: [240, 241, 242],
    map: [236, 236, 232],
    ring: [255, 255, 255],
    markerIcon: [255, 255, 255],
    onLight: [30, 31, 33],
    medical: [211, 18, 58],
    silent: [122, 60, 245],
  },
  dark: {
    label: "Dark (Midnight)",
    page: [15, 16, 18],
    panel: [22, 23, 26],
    panelBorder: [38, 40, 45],
    text: [237, 237, 239],
    subtle: [180, 183, 190],
    subtlest: [138, 143, 152],
    hover: [30, 31, 34],
    map: [32, 33, 37],
    ring: [15, 16, 18],
    markerIcon: [15, 16, 18],
    onLight: [15, 16, 18],
    medical: [255, 107, 122],
    silent: [168, 139, 250],
  },
};

// ---------- the colors worked out from one pick ----------

/** White or near black, whichever reads better on the marker disc. */
function markerIconFor(fill, theme) {
  const light = [255, 255, 255];
  const dark = THEMES[theme].onLight;
  return contrast(light, fill) >= contrast(dark, fill) ? light : dark;
}

/** Every Suspicious color for both themes, from the one picked color. */
export function deriveColors(picked) {
  const L = THEMES.light;
  const D = THEMES.dark;

  const lightTint = tint(picked, "light");
  const light = {
    fill: picked, // the color itself
    tint: lightTint,
    text: reachContrast(picked, [L.page, L.panel, lightTint], 4.5, "dark"),
    icon: reachContrast(picked, [L.page, L.panel], 3, "dark"),
  };
  light.markerIcon = markerIconFor(light.fill, "light");

  // Dark: the color itself, lightened only if it would be under 3:1 on Midnight.
  const darkFill = reachContrast(picked, [D.page, D.panel], 3, "light").rgb;
  const darkTint = tint(picked, "dark");
  const dark = {
    fill: darkFill,
    tint: darkTint,
    text: reachContrast(darkFill, [D.page, D.panel, darkTint], 4.5, "light"),
    icon: reachContrast(darkFill, [D.page, D.panel], 3, "light"),
  };
  dark.markerIcon = markerIconFor(dark.fill, "dark");
  return { light, dark };
}

/** The CSS variables the app reads for Suspicious, for one theme. */
function cssVars(c) {
  return {
    "--color-type-suspicious": toCssRgb(c.fill),
    "--color-type-suspicious-icon": toCssRgb(c.icon.rgb),
    "--color-tag-suspicious-bg": toCssRgb(c.tint),
    "--color-tag-suspicious-text": toCssRgb(c.text.rgb),
    "--color-marker-icon-suspicious": toCssRgb(c.markerIcon),
  };
}

function block(selector, vars) {
  return selector + " {\n" + Object.entries(vars).map(([k, v]) => "  " + k + ": " + v + ";").join("\n") + "\n}";
}

// ---------- saved pick and the live override ----------

function loadHex() {
  try {
    const saved = localStorage.getItem(KEY);
    return parseHex(saved) ? toHex(parseHex(saved)) : null;
  } catch {
    return null;
  }
}

function saveHex(hex) {
  try {
    if (hex) localStorage.setItem(KEY, hex);
    else localStorage.removeItem(KEY);
  } catch {
    // storage blocked: the color still applies until reload
  }
}

/** Puts the override in a style tag after tokens.css, or removes it (null). Same selectors as
    tokens.css, so it wins by coming later. */
function apply(hex) {
  let style = document.getElementById(STYLE_ID);
  if (!hex) {
    if (style) style.remove();
    return;
  }
  const c = deriveColors(parseHex(hex));
  if (!style) {
    style = document.createElement("style");
    style.id = STYLE_ID;
    document.head.appendChild(style);
  }
  style.textContent = block(':root,\n:root[data-theme="light"]', cssVars(c.light)) + "\n" + block(':root[data-theme="dark"]', cssVars(c.dark));
}

/** Called once from main.jsx, so the picked color is back after a reload. */
export function applySavedSuspiciousColor() {
  const hex = loadHex();
  if (hex) apply(hex);
}

/** What "Copy values" copies: the final variables for both themes, ready for tokens.css. */
function copyBlock(hex, c) {
  const hexNoHash = (rgb) => toHex(rgb).slice(1);
  return [
    "/* Suspicious, picked " + hex + " in the Settings color test. Shades worked out in OKLCH, same hue. */",
    "",
    "/* tokens.css, light block (:root, :root[data-theme=\"light\"]) */",
    ...Object.entries(cssVars(c.light)).map(([k, v]) => k + ": " + v + ";"),
    "",
    "/* tokens.css, dark block (:root[data-theme=\"dark\"]) */",
    ...Object.entries(cssVars(c.dark)).map(([k, v]) => k + ": " + v + ";"),
    "",
    "/* Not CSS variables, for the same change (light theme values): */",
    "/* src/lib/copyHtml.js TITLE.SUSPICIOUS: \"" + toHex(c.light.text.rgb) + "\" */",
    "/* src/lib/exportXlsx.js Suspicious: { fill: \"FF" + hexNoHash(c.light.tint) + "\", font: \"FF" + hexNoHash(c.light.text.rgb) + "\" } */",
  ].join("\n");
}

// ---------- the picker: square, hue slider, hex box ----------

const KEY_STEP = 0.01;
const KEY_STEP_BIG = 0.1;

/** Drag for saturation (left to right) and brightness (bottom to top). Arrow keys move the
    handle by 1%, with Shift by 10%. */
function SvSquare({ hsv, onChange }) {
  const ref = useRef(null);
  const hsvRef = useRef(hsv);
  hsvRef.current = hsv;

  function fromPoint(x, y) {
    const r = ref.current.getBoundingClientRect();
    onChange({ ...hsvRef.current, s: clamp((x - r.left) / r.width, 0, 1), v: 1 - clamp((y - r.top) / r.height, 0, 1) });
  }

  function onPointerDown(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    const el = event.currentTarget;
    el.focus();
    el.setPointerCapture(event.pointerId);
    fromPoint(event.clientX, event.clientY);
    const move = (e) => fromPoint(e.clientX, e.clientY);
    const up = () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }

  function onKeyDown(event) {
    const step = event.shiftKey ? KEY_STEP_BIG : KEY_STEP;
    let { s, v } = hsv;
    if (event.key === "ArrowLeft") s -= step;
    else if (event.key === "ArrowRight") s += step;
    else if (event.key === "ArrowUp") v += step;
    else if (event.key === "ArrowDown") v -= step;
    else return;
    event.preventDefault();
    onChange({ ...hsv, s: clamp(s, 0, 1), v: clamp(v, 0, 1) });
  }

  const pure = toHex(hsvToRgb({ h: hsv.h, s: 1, v: 1 }));
  return (
    <div
      ref={ref}
      className="scp-square"
      style={{ backgroundColor: pure }}
      role="slider"
      tabIndex={0}
      aria-label="Saturation and brightness"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(hsv.s * 100)}
      aria-valuetext={"Saturation " + Math.round(hsv.s * 100) + "%, brightness " + Math.round(hsv.v * 100) + "%"}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
    >
      <span
        className="scp-square-handle"
        style={{ left: hsv.s * 100 + "%", top: (1 - hsv.v) * 100 + "%", backgroundColor: toHex(hsvToRgb(hsv)) }}
        aria-hidden="true"
      />
    </div>
  );
}

/** Hue, 0 to 359 degrees. Arrow keys move 1 degree, with Shift or Page keys 10. */
function HueSlider({ hsv, onChange }) {
  const hsvRef = useRef(hsv);
  hsvRef.current = hsv;

  function fromX(el, x) {
    const r = el.getBoundingClientRect();
    onChange({ ...hsvRef.current, h: clamp(((x - r.left) / r.width) * 360, 0, 359.9) });
  }

  function onPointerDown(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    const el = event.currentTarget;
    el.focus();
    el.setPointerCapture(event.pointerId);
    fromX(el, event.clientX);
    const move = (e) => fromX(el, e.clientX);
    const up = () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }

  function onKeyDown(event) {
    const big = event.shiftKey || event.key === "PageUp" || event.key === "PageDown";
    const step = big ? 10 : 1;
    let h = Math.round(hsv.h);
    if (event.key === "ArrowLeft" || event.key === "ArrowDown" || event.key === "PageDown") h -= step;
    else if (event.key === "ArrowRight" || event.key === "ArrowUp" || event.key === "PageUp") h += step;
    else if (event.key === "Home") h = 0;
    else if (event.key === "End") h = 359;
    else return;
    event.preventDefault();
    onChange({ ...hsv, h: ((h % 360) + 360) % 360 });
  }

  return (
    <div
      className="scp-hue"
      role="slider"
      tabIndex={0}
      aria-label="Hue"
      aria-valuemin={0}
      aria-valuemax={359}
      aria-valuenow={Math.round(hsv.h)}
      aria-valuetext={Math.round(hsv.h) + " degrees"}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
    >
      <span
        className="scp-hue-handle"
        style={{ left: (hsv.h / 360) * 100 + "%", backgroundColor: toHex(hsvToRgb({ h: hsv.h, s: 1, v: 1 })) }}
        aria-hidden="true"
      />
    </div>
  );
}

/** Type a hex color. Six digits apply as you type; three digits (EC0) apply on Enter or
    when you leave the box. Anything else goes back to the current color. */
function HexBox({ hex, onHex }) {
  const [text, setText] = useState(null); // null: show the current color
  function commit() {
    if (text !== null && /^([0-9a-f]{3}|[0-9a-f]{6})$/i.test(text)) onHex(toHex(parseHex(text)));
    setText(null);
  }
  return (
    <span className="scp-hex">
      <span className="scp-hex-hash" aria-hidden="true">
        #
      </span>
      <input
        className="input num"
        value={text ?? hex.slice(1)}
        maxLength={7}
        spellCheck={false}
        autoComplete="off"
        aria-label="Hex color"
        onChange={(e) => {
          const value = e.target.value.replace(/[^0-9a-f]/gi, "").slice(0, 6);
          setText(value);
          if (value.length === 6) onHex(toHex(parseHex(value)));
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape" && text !== null) {
            e.stopPropagation(); // keep Settings open
            setText(null);
          }
        }}
      />
    </span>
  );
}

// ---------- preview and checks ----------

function previewStyle(theme, c) {
  const t = THEMES[theme];
  return {
    "--color-panel": toCssRgb(t.panel),
    "--color-surface": toCssRgb(t.panel),
    "--color-page": toCssRgb(t.page),
    "--color-panel-border": toCssRgb(t.panelBorder),
    "--color-border": toCssRgb(t.panelBorder),
    "--color-text": toCssRgb(t.text),
    "--color-text-subtle": toCssRgb(t.subtle),
    "--color-text-subtlest": toCssRgb(t.subtlest),
    "--color-surface-hover": toCssRgb(t.hover),
    "--color-marker-ring": toCssRgb(t.ring),
    "--color-marker-icon": toCssRgb(t.markerIcon),
    "--color-type-medical": toCssRgb(t.medical),
    "--color-type-silent": toCssRgb(t.silent),
    "--scp-map": toCssRgb(t.map),
    ...cssVars(c),
    background: toCssRgb(t.panel),
    color: toCssRgb(t.text),
    colorScheme: theme,
  };
}

/** The same things the dashboard draws in Suspicious, in one theme. */
function Preview({ theme, c }) {
  return (
    <div className="scp-preview" style={previewStyle(theme, c)}>
      <div className="scp-preview-title">{THEMES[theme].label}</div>

      <div className="tile scp-tile">
        <span className="tile-top">
          <TypeIcon type="SUSPICIOUS" size={16} />
          <span className="tile-label">Suspicious</span>
        </span>
        <span className="tile-value num">3</span>
      </div>

      <div className="scp-samples">
        <div className="scp-sample">
          <div className="scp-bars" aria-hidden="true">
            <span className="scp-bar">
              <span className="scp-seg scp-seg--silent is-top" style={{ height: 14 }} />
              <span className="scp-seg scp-seg--suspicious" style={{ height: 22 }} />
              <span className="scp-seg scp-seg--medical" style={{ height: 12 }} />
            </span>
            <span className="scp-bar">
              <span className="scp-seg scp-seg--suspicious is-top" style={{ height: 36 }} />
            </span>
          </div>
          <span className="scp-sample-label">Chart bar</span>
        </div>
        <div className="scp-sample">
          <span className="scp-map" aria-hidden="true">
            <span className="scp-marker">
              <Icon icon={icons.suspicious} size={13} />
            </span>
          </span>
          <span className="scp-sample-label">Map marker</span>
        </div>
        <div className="scp-sample">
          <span className="scp-led-wrap" aria-hidden="true">
            <span className="scp-led" />
          </span>
          <span className="scp-sample-label">LED dot</span>
        </div>
      </div>

      <div className="scp-row">
        <TypeTag type="SUSPICIOUS" />
        <span className="scp-row-name">Jordan Lee</span>
        <span className="scp-row-id">MOCK-FOB-02</span>
        <span className="scp-row-time num">34 s ago</span>
      </div>
    </div>
  );
}

function Verdict({ ratio, target }) {
  const pass = ratio >= target - 1e-9;
  return (
    <span className={"scp-verdict " + (pass ? "is-pass" : "is-fail")}>
      <Icon icon={pass ? icons.acknowledged : icons.warning} size={12} />
      {pass ? "Pass" : "Fail"}
    </span>
  );
}

function ContrastTable({ c }) {
  const rows = [];
  for (const theme of ["light", "dark"]) {
    const t = THEMES[theme];
    const x = c[theme];
    const worstSurface = (rgb) => Math.min(contrast(rgb, t.page), contrast(rgb, t.panel));
    rows.push({ theme, what: "Text on the surface", color: x.text.rgb, ratio: worstSurface(x.text.rgb), target: 4.5 });
    rows.push({ theme, what: "Text on the tint (type tag)", color: x.text.rgb, ratio: contrast(x.text.rgb, x.tint), target: 4.5 });
    rows.push({ theme, what: "Icon on the surface", color: x.icon.rgb, ratio: worstSurface(x.icon.rgb), target: 3 });
    rows.push({ theme, what: "Fill on the surface (bars, dots)", color: x.fill, ratio: worstSurface(x.fill), target: 3, note: true });
  }
  return (
    <table className="table scp-table">
      <thead>
        <tr>
          <th scope="col">Theme</th>
          <th scope="col">Check</th>
          <th scope="col">Color</th>
          <th scope="col" className="right">
            Ratio
          </th>
          <th scope="col">Needs</th>
          <th scope="col">Result</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{THEMES[r.theme].label}</td>
            <td>{r.what}</td>
            <td>
              <span className="scp-chip" style={{ background: toCssRgb(r.color) }} aria-hidden="true" />
              <span className="num">{toHex(r.color)}</span>
            </td>
            <td className="num right">{r.ratio.toFixed(2)}:1</td>
            <td className="num">{r.target}:1</td>
            <td>{<Verdict ratio={r.ratio} target={r.target} />}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Closeness({ c }) {
  const pairs = [];
  for (const theme of ["light", "dark"]) {
    for (const other of ["medical", "silent"]) {
      pairs.push({ theme, other, d: oklabDistance(c[theme].fill, THEMES[theme][other]) });
    }
  }
  const worst = pairs.reduce((a, b) => (b.d < a.d ? b : a));
  const name = (p) => (p.other === "medical" ? "Medical" : "Silent") + ", " + (p.theme === "dark" ? "dark" : "light") + " theme";
  let note = null;
  if (worst.d < TOO_CLOSE) {
    note = (
      <p className="scp-warn is-bad" role="status">
        <Icon icon={icons.warning} size={14} />
        Too close to {name(worst)}. People could mix them up on the chart and the map.
      </p>
    );
  } else if (worst.d < A_BIT_CLOSE) {
    note = (
      <p className="scp-warn is-soft" role="status">
        <Icon icon={icons.warning} size={14} />
        A bit close to {name(worst)}. Check the chart and the map.
      </p>
    );
  }
  return (
    <div className="scp-close">
      <p className="set-desc">
        Distance to the other type colors, measured as OKLab distance (deltaE OK). Under {TOO_CLOSE.toFixed(2)} is too close.
        For comparison, the old magenta was 0.10 from Medical.
      </p>
      <ul className="scp-distances num">
        {pairs.map((p) => (
          <li key={p.theme + p.other} className={p.d < TOO_CLOSE ? "is-bad" : p.d < A_BIT_CLOSE ? "is-soft" : undefined}>
            <TypeIcon type={p.other.toUpperCase()} size={12} />
            {name(p)}: {p.d.toFixed(3)}
          </li>
        ))}
      </ul>
      {note}
    </div>
  );
}

// ---------- the whole tool ----------

function SuspiciousColorTool({ labelledBy }) {
  const [hsv, setHsv] = useState(() => rgbToHsv(parseHex(loadHex() || DEFAULT_HEX)));
  const [active, setActive] = useState(() => loadHex() !== null);
  const rgb = hsvToRgb(hsv);
  const hex = toHex(rgb);
  const colors = useMemo(() => deriveColors(parseHex(hex)), [hex]);

  function pickHsv(next) {
    setHsv(next);
    setActive(true);
    const h = toHex(hsvToRgb(next));
    saveHex(h);
    apply(h);
  }
  function pickHex(h) {
    // Keep the hue when the typed color is a gray, so the square does not jump to red.
    const next = rgbToHsv(parseHex(h));
    pickHsv(next.s === 0 ? { ...next, h: hsv.h } : next);
  }
  function resetColor() {
    saveHex(null);
    apply(null);
    setActive(false);
    setHsv(rgbToHsv(parseHex(DEFAULT_HEX)));
  }

  return (
    <div className="scp" role="group" aria-labelledby={labelledBy}>
      <div className="scp-top">
        <div className="scp-picker">
          <SvSquare hsv={hsv} onChange={pickHsv} />
          <HueSlider hsv={hsv} onChange={pickHsv} />
          <div className="scp-picker-row">
            <span className="scp-swatch" style={{ background: hex }} aria-hidden="true" />
            <HexBox hex={hex} onHex={pickHex} />
          </div>
        </div>
        <div className="scp-side">
          <p className="scp-state">
            {active ? (
              <>
                Showing <span className="num">{hex}</span> across the dashboard.
              </>
            ) : (
              <>The dashboard uses its default Suspicious colors. Drag, type a hex or start from the LED yellow.</>
            )}
          </p>
          <div className="scp-actions">
            <button type="button" className="btn btn-secondary" onClick={() => pickHex(SUGGESTED)}>
              <span className="scp-swatch scp-swatch--sm" style={{ background: SUGGESTED }} aria-hidden="true" />
              Start from <span className="num">{SUGGESTED}</span>
            </button>
            <button type="button" className="btn btn-secondary" onClick={resetColor} disabled={!active}>
              Reset to default
            </button>
            <CopyButton label="Copy values" getText={() => copyBlock(hex, colors)} />
          </div>
          <dl className="scp-values num">
            {["light", "dark"].map((theme) => (
              <div key={theme} className="scp-values-col">
                <dt>{THEMES[theme].label}</dt>
                {[
                  ["Fill", colors[theme].fill],
                  ["Text", colors[theme].text.rgb],
                  ["Icon", colors[theme].icon.rgb],
                  ["Tint", colors[theme].tint],
                ].map(([k, v]) => (
                  <dd key={k}>
                    <span className="scp-chip" style={{ background: toCssRgb(v) }} aria-hidden="true" />
                    <span className="scp-values-key">{k}</span>
                    {toHex(v)}
                  </dd>
                ))}
              </div>
            ))}
          </dl>
        </div>
      </div>

      <div className="scp-previews">
        <Preview theme="light" c={colors.light} />
        <Preview theme="dark" c={colors.dark} />
      </div>

      <h4 className="scp-heading">Contrast</h4>
      <p className="set-desc">
        Text needs 4.5:1 and icons 3:1 (WCAG 2). Text and icons are the picked hue, darkened (light theme) or lightened (dark
        theme) only as much as needed. The fill is the picked color itself, so it can fail on white; bars and markers still have
        their icon, word and position.
      </p>
      <ContrastTable c={colors} />

      <h4 className="scp-heading">Difference from Medical and Silent</h4>
      <Closeness c={colors} />
    </div>
  );
}

/** The row for Settings > Appearance, under Development. */
export function suspiciousColorRow() {
  return {
    section: "appearance",
    group: "Development",
    id: "suspicious-color",
    name: "Suspicious color (for testing)",
    desc: "Find the exact yellow for Suspicious. Changes the whole dashboard as you drag. Saved in this browser. This setting will be removed.",
    body: (id) => <SuspiciousColorTool labelledBy={id} />,
  };
}
