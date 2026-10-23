import { get, writable } from "svelte/store";
import { ApiError, read } from "./api";
import type { Lineup } from "./types";

export const lineup = writable<Lineup | null>(null);
export const lineupLoading = writable(false);
export const lineupError = writable<string | null>(null);
/** Set once an On Demand call answers `on_demand_off`; the cached lineup can lag behind. */
export const onDemandRevoked = writable(false);

let inflight: Promise<void> | null = null;

export async function loadLineup(force = false): Promise<void> {
  if (inflight) return inflight;
  if (!force && get(lineup)) return;
  lineupLoading.set(true);
  lineupError.set(null);
  inflight = (async () => {
    try {
      lineup.set(await read<Lineup>("/api/lineup"));
    } catch (error) {
      lineupError.set(error instanceof ApiError ? error.message : "Could not load channels.");
    } finally {
      lineupLoading.set(false);
      inflight = null;
    }
  })();
  return inflight;
}

export function clearLineup(): void {
  lineup.set(null);
  lineupError.set(null);
  onDemandRevoked.set(false);
}
