// Per-device viewer preferences, persisted in localStorage. Only the last
// browser/device matters — the server never sees these (spec follow-up).

import { writable } from "svelte/store";
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

groupMode.subscribe((mode) => {
  try {
    localStorage.setItem(GROUP_MODE_KEY, mode);
  } catch {
    /* private mode / storage disabled: keep the in-memory value */
  }
});
