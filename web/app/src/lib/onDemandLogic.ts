// Pure logic for the On Demand browse screen (ticket 10; UX settled in On Demand
// issue 09): status pills, search rules, paging, shelves and poster badges.

import { ApiError } from "./api";
import type {
  OnDemandCategory,
  OnDemandItem,
  OnDemandPage,
  OnDemandPortal,
  OnDemandPortalStatus,
} from "./types";

const DAY = 86400;

/** The Channels screen's notice after an On Demand call says the switch is off (09). */
export const ON_DEMAND_OFF_NOTICE = "On Demand isn't available on this login any more.";

/** True for the server's 404 `on_demand_off`: this login may no longer use On Demand. */
export function isOnDemandOff(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404 && error.code === "on_demand_off";
}

/**
 * Whether the app bar offers On Demand: the lineup says so, and no On Demand call has since
 * answered `on_demand_off` (the BFF caches the lineup, so it can lag behind).
 */
export function onDemandShown(lineup: { onDemand?: boolean } | null, revoked: boolean): boolean {
  return (lineup?.onDemand ?? false) && !revoked;
}

export interface StatusPill {
  portal: string;
  status: OnDemandPortalStatus;
  text: string;
}

function statusText(portal: OnDemandPortal, now: number): string {
  switch (portal.status) {
    case "indexing":
      return `Still indexing${portal.progress != null ? ` (${portal.progress}%)` : ""} — newest first`;
    case "stale": {
      const days = Math.max(1, Math.floor((now - (portal.lastRefresh ?? now)) / DAY));
      return `Not refreshed for ${days} day${days === 1 ? "" : "s"}`;
    }
    case "partial":
      return "Partly indexed";
    case "failed":
      return "Couldn't load — showing nothing from it";
    case "ready":
      return "";
  }
}

/** One pill per portal that isn't `ready`, worded as in 09. `now` is epoch seconds. */
export function statusPills(portals: OnDemandPortal[], now: number): StatusPill[] {
  return portals
    .filter((portal) => portal.status !== "ready")
    .map((portal) => ({
      portal: portal.portal,
      status: portal.status,
      text: `${portal.name}: ${statusText(portal, now)}`,
    }));
}

/** Search starts at this many characters (the server refuses fewer). */
export const MIN_SEARCH = 2;

/** The search to run for what's typed: the trimmed text, or null below MIN_SEARCH. */
export function searchTerm(typed: string): string | null {
  const term = typed.trim();
  return term.length >= MIN_SEARCH ? term : null;
}

export type OnDemandSort = "added" | "name" | "year" | "rating";

/** The sort chips, in 09's order. */
export const SORTS: { key: OnDemandSort; label: string }[] = [
  { key: "added", label: "Recently added" },
  { key: "name", label: "A–Z" },
  { key: "year", label: "Year" },
  { key: "rating", label: "Rating" },
];

/** A page of the grid holds this many items. */
export const PAGE_SIZE = 60;

/** What the grid lists: a category ("" = All), what's typed, and a sort the viewer chose. */
export interface ItemsQuery {
  category: string;
  q: string;
  /** null = the server's default: Recently added, or best match for a search. */
  sort: OnDemandSort | null;
}

/** The browse screen's state: an ItemsQuery, plus whether All shows a grid, not shelves. */
export interface Browse extends ItemsQuery {
  allGrid: boolean;
}

/** The browse screen's address, so Back (from a title, ticket 11) returns to it. */
export function browsePath(browse: Browse): string {
  const params = new URLSearchParams();
  if (browse.category) params.set("category", browse.category);
  if (browse.q) params.set("q", browse.q);
  if (browse.sort) params.set("sort", browse.sort);
  if (browse.allGrid) params.set("all", "1");
  const query = params.toString();
  return query ? `/ondemand?${query}` : "/ondemand";
}

/** A title's page (ticket 11). */
export function titlePath(item: Pick<OnDemandItem, "portal" | "id">): string {
  return `/ondemand/title?${new URLSearchParams({ portal: item.portal, id: item.id }).toString()}`;
}

/** The browse state in a /ondemand address. */
export function browseFromQuery(query: URLSearchParams): Browse {
  const sort = query.get("sort");
  return {
    category: query.get("category") ?? "",
    q: query.get("q") ?? "",
    sort: SORTS.some((chip) => chip.key === sort) ? (sort as OnDemandSort) : null,
    allGrid: query.get("all") === "1",
  };
}

/** All shows shelves; a category, a search or "See all" on Recently added shows the grid. */
export function browseView(browse: Browse): "shelves" | "grid" {
  return browse.category === "" && searchTerm(browse.q) === null && !browse.allGrid
    ? "shelves"
    : "grid";
}

/** The chip shown as selected: the chosen sort, else Recently added unless searching. */
export function activeSort(sort: OnDemandSort | null, searching: boolean): OnDemandSort | null {
  return sort ?? (searching ? null : "added");
}

/** The hint beside the chips while searching. `category` is null for All. */
export function searchHint(category: string | null, sort: OnDemandSort | null): string {
  const where = category ? `in ${category}` : "all categories";
  return sort ? where : `Best match first · ${where}`;
}

/** What the grid says when it has nothing. `category` is null for All. */
export function emptyText(typed: string, category: string | null): string {
  const term = searchTerm(typed);
  if (term === null) return "No titles here.";
  return `No titles match “${term}”${category ? ` in ${category}` : ""}`;
}

/** The /api/ondemand/items request for one page of `query`. */
export function itemsPath(query: ItemsQuery, offset: number, limit = PAGE_SIZE): string {
  const params = new URLSearchParams();
  if (query.category) params.set("category", query.category);
  const term = searchTerm(query.q);
  if (term) params.set("q", term);
  if (query.sort) params.set("sort", query.sort);
  params.set("offset", String(offset));
  params.set("limit", String(limit));
  return `/api/ondemand/items?${params.toString()}`;
}

/** A shelf on All holds this many items. */
export const SHELF_SIZE = 20;

export type Shelf =
  | { key: "continue"; title: string; kind: "continue" }
  | { key: "recent"; title: string; kind: "recent"; path: string }
  | {
      key: string;
      title: string;
      kind: "category";
      category: string;
      count: number;
      path: string;
    };

/**
 * The shelves on All: Continue watching (only when it has something), Recently added, then
 * one per category in rail order. Each list shelf carries the request for its 20 items.
 */
export function allShelves(continueItems: OnDemandItem[], categories: OnDemandCategory[]): Shelf[] {
  const shelves: Shelf[] = [];
  if (continueItems.length > 0) {
    shelves.push({ key: "continue", title: "Continue watching", kind: "continue" });
  }
  shelves.push({
    key: "recent",
    title: "Recently added",
    kind: "recent",
    path: itemsPath({ category: "", q: "", sort: null }, 0, SHELF_SIZE),
  });
  for (const category of categories) {
    shelves.push({
      key: `category:${category.id}`,
      title: category.name,
      kind: "category",
      category: category.id,
      count: category.count,
      path: itemsPath({ category: category.id, q: "", sort: null }, 0, SHELF_SIZE),
    });
  }
  return shelves;
}

/** The grid's infinite scroll: what's loaded so far, and the total once known. */
export interface Paging {
  items: OnDemandItem[];
  /** null until the first page arrives. */
  total: number | null;
}

export function initialPaging(): Paging {
  return { items: [], total: null };
}

/** The offset of the next page to fetch, or null when everything is loaded. */
export function nextOffset(paging: Paging): number | null {
  if (paging.total !== null && paging.items.length >= paging.total) return null;
  return paging.items.length;
}

/**
 * `paging` with `page` added. A page that doesn't start where the loaded items end (a
 * duplicate or late reply) is ignored. An empty page ends the list even short of `total`,
 * so a catalogue that shrank between pages can't loop forever.
 */
export function appendPage(paging: Paging, page: OnDemandPage): Paging {
  if (page.offset !== paging.items.length) return paging;
  const items = [...paging.items, ...page.items];
  const total = page.items.length === 0 ? items.length : page.total;
  return { items, total };
}

/** The line under the grid: loading, "Loading more… (n of total)", or the count at the end. */
export function sentinel(paging: Paging, emptyText: string): { text: string; end: boolean } {
  if (paging.total === null) return { text: "Loading…", end: false };
  const loaded = paging.items.length;
  if (loaded < paging.total) {
    return { text: `Loading more… (${loaded} of ${paging.total})`, end: false };
  }
  if (loaded === 0) return { text: emptyText, end: true };
  return { text: `${loaded} title${loaded === 1 ? "" : "s"}`, end: true };
}

/** A playback position as m:ss, or h:mm:ss from an hour. */
export function clock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}

/** How far through, 0-1, or null when there's no position or no known length. */
function fraction(position: number | null, duration: number | null): number | null {
  if (position == null || position <= 0 || !duration) return null;
  return Math.min(1, position / duration);
}

export interface PosterBadges {
  series: boolean;
  watched: boolean;
  /** The progress bar, 0-1, or null for none. */
  progress: number | null;
}

/** The poster's badges: "Series", ✓ Watched, and a bar for a Resume point. */
export function posterBadges(item: OnDemandItem): PosterBadges {
  if (item.kind === "series") {
    const next = item.upNext;
    return {
      series: true,
      watched: false,
      progress: next ? fraction(next.positionSec, next.durationSec) : null,
    };
  }
  const watched = item.progress?.watched ?? false;
  return {
    series: false,
    watched,
    progress:
      item.progress && !watched
        ? fraction(item.progress.positionSec, item.progress.durationSec)
        : null,
  };
}

function left(position: number | null, duration: number | null): string | null {
  if (position == null || !duration) return null;
  return `${Math.max(1, Math.round((duration - position) / 60))} min left`;
}

/** The line under a Continue watching card: "80 min left", or "S2 · E4 · Name · Up next". */
export function continueLine(item: OnDemandItem): string {
  if (item.kind === "series") {
    const next = item.upNext;
    if (!next) return "";
    const parts: string[] = [];
    if (next.seasonNumber != null) parts.push(`S${next.seasonNumber}`);
    if (next.episodeNumber != null) parts.push(`E${next.episodeNumber}`);
    if (next.name) parts.push(next.name);
    parts.push(left(next.positionSec, next.durationSec) ?? "Up next");
    return parts.join(" · ");
  }
  const progress = item.progress;
  if (!progress || progress.positionSec == null) return "";
  return left(progress.positionSec, progress.durationSec) ?? `${clock(progress.positionSec)} in`;
}

/** How long typing must pause before the search runs. */
export const SEARCH_DEBOUNCE_MS = 300;

export interface Debounced<A extends unknown[]> {
  (...args: A): void;
  cancel(): void;
}

/** `fn` run once `ms` after the last call, with that call's arguments. */
export function debounce<A extends unknown[]>(fn: (...args: A) => void, ms: number): Debounced<A> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const debounced = (...args: A) => {
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, ms);
  };
  debounced.cancel = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
  return debounced;
}
