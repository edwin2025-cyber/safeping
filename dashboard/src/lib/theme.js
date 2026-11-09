import { useEffect, useState } from "react";

function systemTheme() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Returns "light" or "dark" and keeps data-theme on <html> in sync. */
export function useEffectiveTheme(setting) {
  const [system, setSystem] = useState(systemTheme);

  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystem(query.matches ? "dark" : "light");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const theme = setting === "light" || setting === "dark" ? setting : system;

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return theme;
}

export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches),
  );
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}
