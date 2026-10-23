// A minimal history-based router (spec 2.1). Routes: login, picker, player,
// multiview, guide, settings, ondemand (browse) and ondemandTitle (a title's page).

import { writable } from "svelte/store";

export type RouteName =
  | "login"
  | "picker"
  | "player"
  | "multiview"
  | "guide"
  | "settings"
  | "ondemand"
  | "ondemandTitle"
  | "notfound";

export interface Route {
  name: RouteName;
  path: string;
  query: URLSearchParams;
}

export function parseRoute(input: string): Route {
  const url = new URL(input, window.location.origin);
  const path = url.pathname;
  let name: RouteName = "notfound";
  if (path === "/login") name = "login";
  else if (path === "/" || path === "") name = "picker";
  else if (path === "/watch") name = "player";
  else if (path === "/multiview") name = "multiview";
  else if (path === "/guide") name = "guide";
  else if (path === "/settings") name = "settings";
  else if (path === "/ondemand") name = "ondemand";
  else if (path === "/ondemand/title") name = "ondemandTitle";
  return { name, path, query: url.searchParams };
}

export const route = writable<Route>(parseRoute(window.location.pathname + window.location.search));

type PopGuard = () => boolean;
const popGuards = new Set<PopGuard>();

/**
 * Lets a screen claim a Back press before the router follows it: a guard that
 * returns true has handled it, and the route is left alone. Returns the remover.
 */
export function guardPopState(guard: PopGuard): () => void {
  popGuards.add(guard);
  return () => popGuards.delete(guard);
}

if (typeof window !== "undefined") {
  window.addEventListener("popstate", () => {
    for (const guard of popGuards) if (guard()) return;
    route.set(parseRoute(window.location.pathname + window.location.search));
  });
}

export function navigate(path: string, replace = false): void {
  if (replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  route.set(parseRoute(path));
}
