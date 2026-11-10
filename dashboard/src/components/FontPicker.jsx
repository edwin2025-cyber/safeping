// TEMPORARY: "Font (for testing)" in Settings > Appearance.
// Everything for it is in this file. To remove it later, delete this file and:
//   - in src/main.jsx, the applySavedFont import and its call
//   - in src/components/SettingsModal.jsx, the fontRow import and its line in buildRows
// The default stays: "SafePing Sans" (Satoshi letters, General Sans digits) and plain Satoshi
// have their @font-face rules in src/styles/base.css, not here.
import { useEffect, useState } from "react";
import { Select } from "./Controls.jsx";

const KEY = "safeping.fontTest";
const DEFAULT_ID = "satoshi-numbers";
const FALLBACK = 'system-ui, "Segoe UI", sans-serif';

// Satoshi and General Sans come from Fontshare files in public/fonts/. The rest come from
// @fontsource-variable packages and load only when picked (a lazy import of their CSS).
const FONTS = [
  {
    id: "satoshi-numbers",
    label: "Satoshi, General Sans numbers",
    family: '"SafePing Sans"',
    files: ["/fonts/satoshi/Satoshi-Variable.woff2", "/fonts/general-sans/GeneralSans-Variable.woff2"],
  },
  { id: "satoshi", label: "Satoshi", family: '"Satoshi"', files: ["/fonts/satoshi/Satoshi-Variable.woff2"] },
  {
    id: "general-sans",
    label: "General Sans",
    family: '"General Sans"',
    files: ["/fonts/general-sans/GeneralSans-Variable.woff2", "/fonts/general-sans/GeneralSans-VariableItalic.woff2"],
    css:
      '@font-face { font-family: "General Sans"; src: url("/fonts/general-sans/GeneralSans-Variable.woff2") format("woff2"); font-weight: 200 700; font-style: normal; font-display: swap; }\n' +
      '@font-face { font-family: "General Sans"; src: url("/fonts/general-sans/GeneralSans-VariableItalic.woff2") format("woff2"); font-weight: 200 700; font-style: italic; font-display: swap; }',
  },
  { id: "inter", label: "Inter", family: '"Inter Variable"', load: () => import("@fontsource-variable/inter") },
  { id: "geist", label: "Geist", family: '"Geist Variable"', load: () => import("@fontsource-variable/geist") },
  { id: "ibm-plex-sans", label: "IBM Plex Sans", family: '"IBM Plex Sans Variable"', load: () => import("@fontsource-variable/ibm-plex-sans") },
  { id: "manrope", label: "Manrope", family: '"Manrope Variable"', load: () => import("@fontsource-variable/manrope") },
  { id: "dm-sans", label: "DM Sans", family: '"DM Sans Variable"', load: () => import("@fontsource-variable/dm-sans") },
];

function loadId() {
  try {
    const id = localStorage.getItem(KEY);
    return FONTS.some((f) => f.id === id) ? id : DEFAULT_ID;
  } catch {
    return DEFAULT_ID;
  }
}

function saveId(id) {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    // storage blocked: the font still applies until reload
  }
}

/** True when every file of a local font is there (a font file, not a fallback page). */
async function filesPresent(font) {
  if (!font.files) return true;
  try {
    const answers = await Promise.all(font.files.map((url) => fetch(url, { method: "HEAD", cache: "no-store" })));
    return answers.every((r) => r.ok && !(r.headers.get("content-type") || "").includes("text/html"));
  } catch {
    return false;
  }
}

const injected = new Set();

async function apply(id) {
  const font = FONTS.find((f) => f.id === id) || FONTS[0];
  const root = document.documentElement;
  if (font.id === DEFAULT_ID) {
    root.style.removeProperty("--font-sans"); // back to the value in tokens.css
    return;
  }
  if (font.files && !(await filesPresent(font))) {
    root.style.removeProperty("--font-sans");
    return;
  }
  if (font.css && !injected.has(font.id)) {
    const style = document.createElement("style");
    style.dataset.fontTest = font.id;
    style.textContent = font.css;
    document.head.appendChild(style);
    injected.add(font.id);
  }
  if (font.load) await font.load();
  root.style.setProperty("--font-sans", font.family + ", " + FALLBACK);
}

/** Called once from main.jsx, so the saved font is back after a reload. */
export function applySavedFont() {
  const id = loadId();
  if (id !== DEFAULT_ID) apply(id).catch(() => {});
}

function FontSelect({ labelledBy }) {
  const [value, setValue] = useState(loadId);
  const [missing, setMissing] = useState({});

  useEffect(() => {
    let stop = false;
    Promise.all(FONTS.filter((f) => f.files).map(async (f) => [f.id, !(await filesPresent(f))])).then((pairs) => {
      if (!stop) setMissing(Object.fromEntries(pairs));
    });
    return () => {
      stop = true;
    };
  }, []);

  return (
    <Select
      labelledBy={labelledBy}
      value={value}
      onChange={(id) => {
        setValue(id);
        saveId(id);
        apply(id).catch(() => {});
      }}
      options={FONTS.map((f) => ({
        value: f.id,
        label: f.label,
        note: missing[f.id] ? "files missing" : f.id === DEFAULT_ID ? "default" : null,
        disabled: !!missing[f.id],
      }))}
    />
  );
}

/** The row for Settings > Appearance. */
export function fontRow() {
  return {
    section: "appearance",
    group: "Testing",
    id: "font",
    name: "Font (for testing)",
    desc: "Try the dashboard in another font. Saved in this browser. This setting will be removed.",
    control: (id) => <FontSelect labelledBy={id} />,
  };
}
