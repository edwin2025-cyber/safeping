// TEMPORARY: color math for the Suspicious color test (components/SuspiciousColorPicker.jsx).
// Delete this file together with the picker.
//
// Contrast: WCAG 2 relative luminance and contrast ratio.
// Shades: OKLCH (Bjorn Ottosson's OKLab in polar form). Darkening or lightening changes only
// the lightness L and keeps the hue h. Chroma C is kept too, and only lowered when the color
// would leave the sRGB range.
// Difference: OKLab distance (Euclidean, deltaE OK). About 0.02 is just visible; under 0.10
// two chart colors are easy to mix up.

export function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

// ---------- hex, rgb, hsv ----------

/** "#ebc20c", "ebc20c" or "#ec0" to [235, 194, 12]. null when it is not a color. */
export function parseHex(text) {
  let s = String(text || "").trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(s)) s = s.replace(/./g, (c) => c + c);
  if (!/^[0-9a-f]{6}$/i.test(s)) return null;
  return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16));
}

export function toHex(rgb) {
  return "#" + rgb.map((n) => Math.round(clamp(n, 0, 255)).toString(16).padStart(2, "0")).join("").toUpperCase();
}

/** The format tokens.css uses: rgb(235, 194, 12) */
export function toCssRgb(rgb) {
  return "rgb(" + rgb.map((n) => Math.round(clamp(n, 0, 255))).join(", ") + ")";
}

/** h 0 to 360, s and v 0 to 1 */
export function hsvToRgb({ h, s, v }) {
  const f = (n) => {
    const k = (n + h / 60) % 6;
    return v - v * s * Math.max(0, Math.min(k, 4 - k, 1));
  };
  return [f(5), f(3), f(1)].map((x) => Math.round(x * 255));
}

export function rgbToHsv(rgb) {
  const [r, g, b] = rgb.map((n) => n / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d > 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s: max === 0 ? 0 : d / max, v: max };
}

// ---------- WCAG contrast ----------

function toLinear(c) {
  c /= 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function fromLinear(c) {
  const v = c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055;
  return v * 255;
}

export function luminance(rgb) {
  const [r, g, b] = rgb.map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// ---------- OKLab and OKLCH ----------

export function rgbToOklab(rgb) {
  const [r, g, b] = rgb.map(toLinear);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

/** Linear sRGB, not clamped, so the caller can tell when a color is out of range. */
function oklabToLinear([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

export function rgbToOklch(rgb) {
  const [L, a, b] = rgbToOklab(rgb);
  let h = (Math.atan2(b, a) * 180) / Math.PI;
  if (h < 0) h += 360;
  return { L, C: Math.hypot(a, b), h };
}

function inGamut(lin) {
  return lin.every((c) => c >= -0.0001 && c <= 1.0001);
}

/** OKLCH to sRGB 0 to 255. Lowers the chroma just enough to stay inside sRGB. */
export function oklchToRgb({ L, C, h }) {
  const rad = (h * Math.PI) / 180;
  const at = (c) => oklabToLinear([L, c * Math.cos(rad), c * Math.sin(rad)]);
  let lin = at(C);
  if (!inGamut(lin)) {
    let lo = 0;
    let hi = C;
    for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      if (inGamut(at(mid))) lo = mid;
      else hi = mid;
    }
    lin = at(lo);
  }
  return lin.map((c) => Math.round(clamp(fromLinear(clamp(c, 0, 1)), 0, 255)));
}

/** OKLab distance (deltaE OK) between two sRGB colors. */
export function oklabDistance(x, y) {
  const a = rgbToOklab(x);
  const b = rgbToOklab(y);
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

// ---------- shades that pass ----------

/** The lowest contrast of a color against every background in the list. */
export function worstContrast(rgb, backgrounds) {
  return Math.min(...backgrounds.map((bg) => contrast(rgb, bg)));
}

/** The same hue, darker (toward: "dark") or lighter (toward: "light"), changed as little as
    possible until it reaches target contrast on every background. Unchanged when it already
    passes. Returns the color and whether the target was reached. */
export function reachContrast(rgb, backgrounds, target, toward) {
  if (worstContrast(rgb, backgrounds) >= target) return { rgb, ok: true };
  const lch = rgbToOklch(rgb);
  const end = toward === "dark" ? 0 : 1;
  const passes = (L) => worstContrast(oklchToRgb({ ...lch, L }), backgrounds) >= target;
  if (!passes(end)) return { rgb: oklchToRgb({ ...lch, L: end }), ok: false };
  // Binary search between the color (fails) and the end (passes) for the nearest L that passes.
  let fail = lch.L;
  let pass = end;
  for (let i = 0; i < 30; i++) {
    const mid = (fail + pass) / 2;
    if (passes(mid)) pass = mid;
    else fail = mid;
  }
  return { rgb: oklchToRgb({ ...lch, L: pass }), ok: true };
}

/** A soft tint of the same hue for chips (type tags): very light in the light theme,
    deep in the dark theme. */
export function tint(rgb, theme) {
  const { C, h } = rgbToOklch(rgb);
  if (theme === "dark") return oklchToRgb({ L: 0.29, C: Math.min(C * 0.4, 0.06), h });
  return oklchToRgb({ L: 0.955, C: Math.min(C * 0.35, 0.05), h });
}
