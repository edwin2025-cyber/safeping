import { useCallback, useState } from "react";

const KEY = "safeping.settings";

// null means "use the default from /api/config".
export const DEFAULT_SETTINGS = {
  theme: "auto", // auto, light, dark
  sound: false,
  showStatus: false,
  autoZoom: true,
  mapLabels: true,
  timeFormat: "12", // 12 or 24
  sightRadius: null, // 25, 50 or 100
  cameraBefore: null, // minutes
  cameraAfter: null, // minutes
};

export const FALLBACK_DEFAULTS = { sight_radius_m: 50, camera_before_min: 2, camera_after_min: 5 };

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
    return { ...DEFAULT_SETTINGS, ...(saved && typeof saved === "object" ? saved : {}) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function save(settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    // Private window or storage blocked. Settings still work until reload.
  }
}

export function useSettings() {
  const [settings, setSettings] = useState(load);

  const update = useCallback((patch) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      save(next);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    save(DEFAULT_SETTINGS);
    setSettings({ ...DEFAULT_SETTINGS });
  }, []);

  return { settings, update, reset };
}

/** Fills the null settings with the server defaults. */
export function effectiveSettings(settings, config) {
  const d = { ...FALLBACK_DEFAULTS, ...((config && config.defaults) || {}) };
  return {
    ...settings,
    sightRadius: settings.sightRadius ?? d.sight_radius_m,
    cameraBefore: settings.cameraBefore ?? d.camera_before_min,
    cameraAfter: settings.cameraAfter ?? d.camera_after_min,
    defaults: d,
  };
}

export function loadBool(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value === "1";
  } catch {
    return fallback;
  }
}

export function saveBool(key, value) {
  try {
    localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // ignore
  }
}
