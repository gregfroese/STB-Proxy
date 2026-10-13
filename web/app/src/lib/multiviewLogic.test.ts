import { describe, expect, it } from "vitest";
import type { Channel } from "./types";
import {
  assignChannel,
  effectiveAudioSlot,
  emptyTiles,
  removeTile,
  swapTiles,
  tileStatus,
  visibleCount,
  visibleTiles,
  type MultiviewTile,
} from "./multiviewLogic";

function channel(id: string, name = `CH ${id}`): Channel {
  return {
    portal: "1",
    channelId: id,
    name,
    url: `/play/1/${id}`,
    portalName: "",
    number: null,
    logo: null,
    genre: null,
    epgId: null,
    blocks: [],
    favourite: false,
    blockFavourites: [],
  };
}

const a = channel("1", "BBC One");
const b = channel("2", "BBC Two");
const c = channel("3", "ITV");

function grid(...channels: (Channel | null)[]): MultiviewTile[] {
  return channels.map((ch, slot) => ({ slot, channel: ch }));
}

describe("swap", () => {
  it("exchange exchanges two tiles' channels", () => {
    const swapped = swapTiles(grid(a, b), 0, 1);
    expect(swapped[0].channel).toEqual(b);
    expect(swapped[1].channel).toEqual(a);
  });

  it("exchanges a filled and an empty tile", () => {
    const swapped = swapTiles(grid(a, null), 0, 1);
    expect(swapped[0].channel).toBeNull();
    expect(swapped[1].channel).toEqual(a);
  });

  it("swapping a tile with itself is a no-op", () => {
    const tiles = grid(a, b);
    expect(swapTiles(tiles, 0, 0)).toEqual(tiles);
  });

  it("swapping an unknown slot is a no-op", () => {
    const tiles = grid(a, b);
    expect(swapTiles(tiles, 0, 9)).toEqual(tiles);
  });
});

describe("remove / assign", () => {
  it("remove clears only the addressed slot", () => {
    const removed = removeTile(grid(a, b, c), 1);
    expect(removed[1].channel).toBeNull();
    expect(removed[0].channel).toEqual(a);
    expect(removed[2].channel).toEqual(c);
  });

  it("assign puts a channel into the addressed slot only", () => {
    const assigned = assignChannel(grid(null, b), 0, a);
    expect(assigned[0].channel).toEqual(a);
    expect(assigned[1].channel).toEqual(b);
  });
});

describe("audio source", () => {
  it("falls back to the first non-empty slot when none is requested", () => {
    expect(effectiveAudioSlot(grid(null, a, b), null)).toBe(1);
  });

  it("the requested audio slot is honoured when it has a channel", () => {
    expect(effectiveAudioSlot(grid(a, b, c), 2)).toBe(2);
  });

  it("moving audio updates the single source", () => {
    const tiles = grid(a, b, c);
    expect(effectiveAudioSlot(tiles, 0)).toBe(0);
    expect(effectiveAudioSlot(tiles, 1)).toBe(1);
  });

  it("an empty requested slot falls back to a filled one", () => {
    expect(effectiveAudioSlot(grid(a, null), 1)).toBe(0);
  });

  it("removing the audio tile falls back to the next non-empty slot", () => {
    expect(effectiveAudioSlot(removeTile(grid(a, b, c), 0), 0)).toBe(1);
  });

  it("an empty grid has no audio source", () => {
    expect(effectiveAudioSlot(grid(null, null), 0)).toBeNull();
  });
});

describe("status derivation", () => {
  it("status is empty without a channel", () => {
    expect(tileStatus({ slot: 0, channel: null }, null)).toEqual({ kind: "empty" });
  });

  it("a live 503 folds into tuner-busy", () => {
    expect(tileStatus({ slot: 0, channel: a }, { kind: "all_tuners_busy" })).toEqual({
      kind: "tuner_busy",
    });
  });

  it("a non-503 error is a per-tile failure", () => {
    expect(tileStatus({ slot: 0, channel: a }, { kind: "unreachable" })).toEqual({
      kind: "failed",
      error: { kind: "unreachable" },
    });
  });

  it("a playable tile with no error is live", () => {
    expect(tileStatus({ slot: 0, channel: a }, null)).toEqual({ kind: "live" });
  });
});

describe("layouts", () => {
  it("each layout shows the right number of tiles", () => {
    const tiles = emptyTiles();
    expect(visibleCount("big")).toBe(4);
    expect(visibleCount("2x1")).toBe(2);
    expect(visibleCount("1x2")).toBe(2);
    expect(visibleCount("2x2")).toBe(4);
    expect(visibleCount("3x3")).toBe(9);
    expect(visibleTiles(tiles, "2x1")).toHaveLength(2);
    expect(visibleTiles(tiles, "1x2")).toHaveLength(2);
    expect(visibleTiles(tiles, "2x2")).toHaveLength(4);
    expect(visibleTiles(tiles, "3x3")).toHaveLength(9);
  });
});
