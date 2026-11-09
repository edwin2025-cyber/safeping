import { useEffect, useRef } from "react";

/** Calls fn now and then every ms while enabled. fn can change between renders. */
export function usePolling(fn, ms, enabled = true, deps = []) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) return undefined;
    let stopped = false;
    const tick = () => {
      if (!stopped) fnRef.current();
    };
    tick();
    const timer = setInterval(tick, ms);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, enabled, ...deps]);
}
