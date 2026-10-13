// A minimal history-based router (spec 2.1). Routes: login, picker, player,
// multiview, settings.

import { writable } from "svelte/store";

export type RouteName = "login" | "picker" | "player" | "multiview" | "settings" | "notfound";

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
  else if (path === "/settings") name = "settings";
  return { name, path, query: url.searchParams };
}

export const route = writable<Route>(parseRoute(window.location.pathname + window.location.search));

if (typeof window !== "undefined") {
  window.addEventListener("popstate", () => {
    route.set(parseRoute(window.location.pathname + window.location.search));
  });
}

export function navigate(path: string, replace = false): void {
  if (replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  route.set(parseRoute(path));
}
