import { useSyncExternalStore } from "react";

import { parseRoute, type Route } from "./routes";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

const getHash = () => window.location.hash;

/** The current hash route; re-renders on every hash change. */
export function useHashRoute(): Route {
  const hash = useSyncExternalStore(subscribe, getHash, () => "");
  return parseRoute(hash);
}

export function navigate(hash: string): void {
  window.location.hash = hash;
}

/** Changes the route without adding a history entry (used for redirects). */
export function replaceRoute(hash: string): void {
  window.location.replace(hash);
}
