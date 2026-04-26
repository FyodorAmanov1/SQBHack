"use client";

import { useSyncExternalStore } from "react";

function subscribeMediaQuery(query: string, callback: () => void) {
  const m = window.matchMedia(query);
  m.addEventListener("change", callback);
  return () => m.removeEventListener("change", callback);
}

/**
 * Avoids hydration mismatch: server snapshot is false; after mount, matches client width.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onStoreChange) => subscribeMediaQuery(query, onStoreChange),
    () => window.matchMedia(query).matches,
    () => false,
  );
}
