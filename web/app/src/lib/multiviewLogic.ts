// Ported from the Android MultiviewLogic.kt (spec 2.5). D-pad moveFocusSlot and
// the proactive tuner budget are dropped: the web Multiview is reactive-503 only.

import type { Channel } from "./types";
import type { PlaybackError } from "./playerLogic";

/** Web grid slots (spec 2.5: up to 3×3). */
export const MULTIVIEW_SLOTS = 9;

export type MultiviewLayout = "big" | "2x1" | "1x2" | "2x2" | "3x3";

export const LAYOUTS: { key: MultiviewLayout; label: string }[] = [
  { key: "big", label: "Big + strip" },
  { key: "2x1", label: "2×1" },
  { key: "1x2", label: "1×2" },
  { key: "2x2", label: "2×2" },
  { key: "3x3", label: "3×3" },
];

export interface MultiviewTile {
  slot: number;
  channel: Channel | null;
}

/** A fresh grid of `count` empty tiles. */
export function emptyTiles(count = MULTIVIEW_SLOTS): MultiviewTile[] {
  return Array.from({ length: count }, (_, slot) => ({ slot, channel: null }));
}

/** How many tiles a layout shows. */
export function visibleCount(layout: MultiviewLayout): number {
  return { big: 4, "2x1": 2, "1x2": 2, "2x2": 4, "3x3": 9 }[layout];
}

/** The Tiles a layout shows, in slot order. */
export function visibleTiles(tiles: MultiviewTile[], layout: MultiviewLayout): MultiviewTile[] {
  return tiles.slice(0, visibleCount(layout));
}

/** Exchange the channels held by slots a and b. */
export function swapTiles(tiles: MultiviewTile[], a: number, b: number): MultiviewTile[] {
  if (a === b) return tiles;
  const tileA = tiles.find((tile) => tile.slot === a);
  const tileB = tiles.find((tile) => tile.slot === b);
  if (!tileA || !tileB) return tiles;
  return tiles.map((tile) => {
    if (tile.slot === a) return { ...tile, channel: tileB.channel };
    if (tile.slot === b) return { ...tile, channel: tileA.channel };
    return tile;
  });
}

/** Clear the channel held by `slot`; the cell stays in place. */
export function removeTile(tiles: MultiviewTile[], slot: number): MultiviewTile[] {
  return tiles.map((tile) => (tile.slot === slot ? { ...tile, channel: null } : tile));
}

/** Put `channel` into `slot`. */
export function assignChannel(
  tiles: MultiviewTile[],
  slot: number,
  channel: Channel,
): MultiviewTile[] {
  return tiles.map((tile) => (tile.slot === slot ? { ...tile, channel } : tile));
}

/**
 * The single audio-source slot. Exactly one Tile is unmuted: `requested` when it
 * still holds a channel, otherwise the lowest non-empty slot.
 */
export function effectiveAudioSlot(
  tiles: MultiviewTile[],
  requested: number | null,
): number | null {
  const nonEmpty = tiles
    .filter((tile) => tile.channel != null)
    .map((tile) => tile.slot)
    .sort((a, b) => a - b);
  if (nonEmpty.length === 0) return null;
  return requested != null && nonEmpty.includes(requested) ? requested : nonEmpty[0];
}

export type TileStatus =
  | { kind: "empty" }
  | { kind: "live" }
  | { kind: "tuner_busy" }
  | { kind: "failed"; error: PlaybackError };

/** Derives a Tile's status from its own last error (reactive 503 folds into busy). */
export function tileStatus(tile: MultiviewTile, error: PlaybackError | null): TileStatus {
  if (tile.channel == null) return { kind: "empty" };
  if (error?.kind === "all_tuners_busy") return { kind: "tuner_busy" };
  if (error != null) return { kind: "failed", error };
  return { kind: "live" };
}
