import { writable } from "svelte/store";
import { emptyTiles, type MultiviewLayout, type MultiviewTile } from "./multiviewLogic";
import type { PlaybackError } from "./playerLogic";

export const tiles = writable<MultiviewTile[]>(emptyTiles());
export const layout = writable<MultiviewLayout>("big");
export const audioSlot = writable<number | null>(null);
export const tileErrors = writable<Record<number, PlaybackError | null>>({});

export function resetMultiview(): void {
  tiles.set(emptyTiles());
  layout.set("big");
  audioSlot.set(null);
  tileErrors.set({});
}
