// Small fetch helpers. All paths are relative, so the same build works
// behind Flask and behind the Vite dev proxy.

// True only under `npm run dev:mock` (vite --mode mock). Vite replaces MODE with
// a fixed string, so in a normal build the mock branches below are dead code and
// src/mock/ is left out of the bundle.
export const MOCK = import.meta.env.MODE === "mock";

export async function getJson(url) {
  if (import.meta.env.MODE === "mock") return (await import("../mock/api.js")).mockGet(url);
  const response = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
}

export async function postJson(url, body) {
  if (import.meta.env.MODE === "mock") return (await import("../mock/api.js")).mockPost(url, body);
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
}
