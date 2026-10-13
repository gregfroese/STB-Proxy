import { describe, expect, it } from "vitest";
import type { Channel } from "./types";
import {
  OTHER_BLOCK,
  blockMatchCounts,
  blockRail,
  channelsInBlock,
  extraBlockCount,
  launchBlockFor,
  searchChannels,
} from "./pickerLogic";

function channel(
  id: string,
  name: string,
  number: string | null = null,
  blocks: string[] = [],
): Channel {
  return {
    portal: "1",
    channelId: id,
    name,
    number,
    blocks,
    url: `/play/1/${id}`,
    portalName: "",
    logo: null,
    genre: null,
    epgId: null,
    favourite: false,
    blockFavourites: [],
  };
}

const kids = channel("1", "Cartoon Network", "301", ["Kids"]);
const news = channel("2", "BBC News", "501", ["News"]);
const multi = channel("3", "TNT Sports", "203", ["Sports", "Entertainment"]);
const ungrouped = channel("4", "Community TV", "701", []);
const channels = [kids, news, multi, ungrouped];

describe("pickerLogic", () => {
  it("rail follows blocks order and appends Other last", () => {
    const rail = blockRail(["Entertainment", "Kids", "News", "Sports"], channels);
    expect(rail.map((entry) => entry.name)).toEqual([
      "Entertainment",
      "Kids",
      "News",
      "Sports",
      OTHER_BLOCK,
    ]);
    expect(rail.map((entry) => entry.count)).toEqual([1, 1, 1, 1, 1]);
  });

  it("Other is omitted when every channel is grouped", () => {
    const rail = blockRail(["Kids", "News", "Sports"], [kids, news, multi]);
    expect(rail.map((entry) => entry.name)).toEqual(["Kids", "News", "Sports"]);
  });

  it("channelsInBlock resolves named blocks and Other", () => {
    expect(channelsInBlock(channels, "Sports")).toEqual([multi]);
    expect(channelsInBlock(channels, OTHER_BLOCK)).toEqual([ungrouped]);
  });

  it("search matches name and number across all blocks, case-insensitively", () => {
    expect(searchChannels(channels, "bbc")).toEqual([news]);
    expect(searchChannels(channels, "701")).toEqual([ungrouped]);
    expect(searchChannels(channels, "  ")).toEqual(channels);
    expect(searchChannels(channels, "zzz")).toEqual([]);
  });

  it("block match counts are per-block and span every block", () => {
    const counts = blockMatchCounts(
      channels,
      ["Entertainment", "Kids", "News", "Sports", OTHER_BLOCK],
      "t",
    );
    expect(counts.get("Entertainment")).toBe(1);
    expect(counts.get("Kids")).toBe(1);
    expect(counts.get("News")).toBe(0);
    expect(counts.get("Sports")).toBe(1);
    expect(counts.get(OTHER_BLOCK)).toBe(1);
  });

  it("plus-N badge counts the channel's other blocks only", () => {
    expect(extraBlockCount(multi, "Sports", false)).toBe(1);
    expect(extraBlockCount(kids, "Kids", false)).toBe(0);
    expect(extraBlockCount(multi, "Sports", true)).toBe(0);
    expect(extraBlockCount(ungrouped, OTHER_BLOCK, false)).toBe(0);
  });

  it("launch block prefers the active block else the channel's first", () => {
    expect(launchBlockFor(multi, "Sports")).toBe("Sports");
    expect(launchBlockFor(multi, "Kids")).toBe("Sports");
    expect(launchBlockFor(multi, null)).toBe("Sports");
    expect(launchBlockFor(ungrouped, "Kids")).toBe(OTHER_BLOCK);
    expect(launchBlockFor(ungrouped, OTHER_BLOCK)).toBe(OTHER_BLOCK);
  });
});
