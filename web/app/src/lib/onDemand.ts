// The On Demand API calls (tickets 10-11), proxied 1:1 by the BFF. Every call goes through
// `onDemandRead` or `onDemandMutate`, so a 404 `on_demand_off` from any of them hides the
// app-bar button and returns the viewer to Channels with 09's notice.

import { writable } from "svelte/store";
import { mutate, read } from "./api";
import { onDemandRevoked } from "./lineup";
import type { PlayStart } from "./onDemandDetailLogic";
import { ON_DEMAND_OFF_NOTICE, isOnDemandOff } from "./onDemandLogic";
import { navigate } from "./router";
import type {
  OnDemandCategories,
  OnDemandDetail,
  OnDemandEpisode,
  OnDemandItem,
  OnDemandKey,
  OnDemandPage,
  OnDemandSession,
} from "./types";

/** A one-line notice for the Channels screen (set when On Demand is switched off). */
export const channelsNotice = writable<string | null>(null);

/** On Demand was switched off for this login: drop the button, go to Channels and say so. */
export function onDemandOff(): void {
  onDemandRevoked.set(true);
  channelsNotice.set(ON_DEMAND_OFF_NOTICE);
  navigate("/", true);
}

/** `read`, but an `on_demand_off` answer also runs `onDemandOff()` before it rethrows. */
export async function onDemandRead<T>(path: string, signal?: AbortSignal): Promise<T> {
  try {
    return await read<T>(path, signal);
  } catch (error) {
    if (isOnDemandOff(error)) onDemandOff();
    throw error;
  }
}

export function loadCategories(signal?: AbortSignal): Promise<OnDemandCategories> {
  return onDemandRead<OnDemandCategories>("/api/ondemand/categories", signal);
}

/** One page of /items; `path` comes from `itemsPath` or a Shelf. */
export function loadItems(path: string, signal?: AbortSignal): Promise<OnDemandPage> {
  return onDemandRead<OnDemandPage>(path, signal);
}

export async function loadContinue(signal?: AbortSignal): Promise<OnDemandItem[]> {
  return (await onDemandRead<{ items: OnDemandItem[] }>("/api/ondemand/continue", signal)).items;
}

const part = encodeURIComponent;

/** A Movie's or Series' detail (a Series' lists its Seasons). */
export function loadDetail(
  portal: string,
  id: string,
  signal?: AbortSignal,
): Promise<OnDemandDetail> {
  return onDemandRead<OnDemandDetail>(`/api/ondemand/item/${part(portal)}/${part(id)}`, signal);
}

/** One Season's Episodes, ascending, each with this Account's `progress`. */
export function loadSeason(
  portal: string,
  seriesId: string,
  seasonId: string,
  signal?: AbortSignal,
): Promise<OnDemandEpisode[]> {
  return onDemandRead<OnDemandEpisode[]>(
    `/api/ondemand/series/${part(portal)}/${part(seriesId)}/season/${part(seasonId)}`,
    signal,
  );
}

/** `mutate` (never retried), with `onDemandRead`'s `on_demand_off` handling. */
async function onDemandMutate<T>(
  path: string,
  body: unknown,
  method: "POST" | "PUT" | "DELETE",
  keepalive = false,
): Promise<T> {
  try {
    return await mutate<T>(path, body, method, keepalive);
  } catch (error) {
    if (isOnDemandOff(error)) onDemandOff();
    throw error;
  }
}

/** POST /play: start an On Demand session for a Movie or an Episode (ADR 0005). */
export function startSession(key: OnDemandKey, replaces?: string): Promise<OnDemandSession> {
  return onDemandMutate<OnDemandSession>(
    "/api/ondemand/play",
    replaces ? { ...key, replaces } : key,
    "POST",
  );
}

/** Release a session now (DELETE /session/<sid>); `keepalive` as the page goes away. */
export function endSession(sid: string, keepalive = false): Promise<void> {
  return onDemandMutate<void>(`/api/ondemand/session/${part(sid)}`, undefined, "DELETE", keepalive);
}

/**
 * A playback report (07): fire-and-forget, never retried. `keepalive` when the page is
 * being hidden or left, so the report still lands.
 */
export function reportProgress(
  key: OnDemandKey,
  sample: { positionSec: number; durationSec: number | null },
  keepalive = false,
): Promise<void> {
  return onDemandMutate<void>(
    "/api/ondemand/progress",
    { ...key, positionSec: sample.positionSec, durationSec: sample.durationSec },
    "PUT",
    keepalive,
  );
}

/**
 * Fetch a session's playlist again after the stream failed, for its status and body: a
 * 410 `session_ended` names the reason (hls.js only sees the status). null when it can't
 * be reached at all.
 */
export async function probeSession(url: string): Promise<{ status: number | null; body: unknown }> {
  try {
    const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
    let body: unknown = null;
    if (!response.ok) {
      try {
        body = await response.json();
      } catch {
        /* not JSON */
      }
    }
    return { status: response.status, body };
  } catch {
    return { status: null, body: null };
  }
}

/** The hand mark (07): Watched, or not (which also clears the Resume point). */
export function markWatched(key: OnDemandKey, watched: boolean): Promise<void> {
  return onDemandMutate<void>("/api/ondemand/progress", { ...key, watched }, "PUT");
}

/**
 * What the title page hands the player (ticket 12) along with `watchPath(start)`: the
 * session it already opened (so Play's errors show on the title page) and the title to
 * show. The player takes it only when `start` matches its address; after a reload it
 * finds none and opens its own session from the address.
 */
export interface PlayHandoff {
  start: PlayStart;
  session: OnDemandSession;
  title: string;
}

export const playHandoff = writable<PlayHandoff | null>(null);
