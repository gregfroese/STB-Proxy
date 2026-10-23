// Per-device viewer preferences, persisted in localStorage. Only the last
// browser/device matters — the server never sees these (spec follow-up).

import { writable } from "svelte/store";
import { ASPECTS, type AspectMode } from "./onDemandPlayerLogic";
import type { GroupMode } from "./pickerLogic";

const GROUP_MODE_KEY = "stbproxy.groupMode";

function readGroupMode(): GroupMode {
  try {
    return localStorage.getItem(GROUP_MODE_KEY) === "genres" ? "genres" : "blocks";
  } catch {
    return "blocks";
  }
}

/** Whether the picker groups channels by Blocks (default) or Genres. */
export const groupMode = writable<GroupMode>(readGroupMode());

const ASPECT_KEY = "stbproxy.onDemandAspect.";

/** The On Demand player's Aspect for an item (a Movie, or a whole Series); "auto" if unset. */
export function readAspect(item: string): AspectMode {
  try {
    const stored = localStorage.getItem(ASPECT_KEY + item);
    return ASPECTS.find((mode) => mode === stored) ?? "auto";
  } catch {
    return "auto";
  }
}

export function saveAspect(item: string, mode: AspectMode): void {
  try {
    if (mode === "auto") localStorage.removeItem(ASPECT_KEY + item);
    else localStorage.setItem(ASPECT_KEY + item, mode);
  } catch {
    /* private mode / storage disabled: it lasts this visit only */
  }
}

groupMode.subscribe((mode) => {
  try {
    localStorage.setItem(GROUP_MODE_KEY, mode);
  } catch {
    /* private mode / storage disabled: keep the in-memory value */
  }
});
