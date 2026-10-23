// The On Demand API reads (ticket 10), proxied 1:1 by the BFF. Every call goes through
// `onDemandRead`, so a 404 `on_demand_off` from any of them hides the app-bar button and
// returns the viewer to Channels with 09's notice.

import { writable } from "svelte/store";
import { read } from "./api";
import { onDemandRevoked } from "./lineup";
import { ON_DEMAND_OFF_NOTICE, isOnDemandOff } from "./onDemandLogic";
import { navigate } from "./router";
import type { OnDemandCategories, OnDemandItem, OnDemandPage } from "./types";

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
