"use client";

import { useLayoutEffect, useState } from "react";

/**
 * matchMedia in the browser. First render always `false` (matches SSR and avoids
 * hydration skew). Real value is applied after `useLayoutEffect`.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useLayoutEffect(() => {
    const m = window.matchMedia(query);
    setMatches(m.matches);
    const onChange = () => {
      setMatches(m.matches);
    };
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
