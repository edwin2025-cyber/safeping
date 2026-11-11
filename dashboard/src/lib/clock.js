import { useSyncExternalStore } from "react";

// One shared timer for every relative time ("34 s ago", "2 min ago") and the top bar clock.
// It runs only while something on screen uses it.
const TICK_MS = 5000;

let now = Date.now();
let timer = null;
const listeners = new Set();

function tick() {
  now = Date.now();
  listeners.forEach((fn) => fn());
}

function subscribe(fn) {
  listeners.add(fn);
  if (timer === null) {
    now = Date.now();
    timer = setInterval(tick, TICK_MS);
  }
  return () => {
    listeners.delete(fn);
    if (!listeners.size && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

function snapshot() {
  return now;
}

/** Server time in seconds (local time plus skew), updated every 5 s by the shared timer. */
export function useNow(skew = 0) {
  return useSyncExternalStore(subscribe, snapshot) / 1000 + skew;
}
