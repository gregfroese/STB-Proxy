// Ported from the Android PickerLogic.kt (spec 2.3). D-pad bits are dropped.

import type { Channel } from "./types";

/** Rail entry for public channels in no visible Block (`blocks: []`) or genre. */
export const OTHER_BLOCK = "Other";

/** Which taxonomy the viewer groups channels by (per-device preference). */
export type GroupMode = "blocks" | "genres";

/**
 * The mode actually used: a viewer preference of "blocks" still falls back to
 * "genres" when the account has no visible Blocks, so nothing is dumped into a
 * lone "Other" bucket.
 */
export function effectiveGroupMode(pref: GroupMode, blocks: string[]): GroupMode {
  return blocks.length > 0 ? pref : "genres";
}

/** A channel's Genre as a rail name, or "Other" when the portal gave none. */
export function genreName(channel: Channel): string {
  const genre = (channel.genre ?? "").trim();
  return genre === "" ? OTHER_BLOCK : genre;
}

/** The Genre rail: distinct genres (case-insensitively sorted), "Other" last. */
export function genreRail(channels: Channel[]): BlockEntry[] {
  const canonical = new Map<string, string>();
  for (const channel of channels) {
    const genre = (channel.genre ?? "").trim();
    if (genre === "") continue;
    const key = genre.toLowerCase();
    if (!canonical.has(key)) canonical.set(key, genre);
  }
  const entries = [...canonical.values()]
    .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
    .map((name) => ({
      name,
      count: channels.filter(
        (channel) => (channel.genre ?? "").trim().toLowerCase() === name.toLowerCase(),
      ).length,
    }));
  const other = channels.filter((channel) => (channel.genre ?? "").trim() === "").length;
  return other > 0 ? [...entries, { name: OTHER_BLOCK, count: other }] : entries;
}

/** The rail for [mode]: Blocks in operator order, or Genres alphabetically. */
export function groupRail(mode: GroupMode, blocks: string[], channels: Channel[]): BlockEntry[] {
  return mode === "genres" ? genreRail(channels) : blockRail(blocks, channels);
}

/** Channels belonging to [group], interpreted by [mode]. */
export function channelsInGroup(mode: GroupMode, channels: Channel[], group: string): Channel[] {
  if (mode === "blocks") return channelsInBlock(channels, group);
  const target = group.toLowerCase();
  return channels.filter((channel) => {
    const genre = (channel.genre ?? "").trim();
    return group === OTHER_BLOCK ? genre === "" : genre.toLowerCase() === target;
  });
}

/** Per-group match counts for the search rail, keyed by rail entry name. */
export function groupMatchCounts(
  mode: GroupMode,
  channels: Channel[],
  groupNames: string[],
  query: string,
): Map<string, number> {
  const matched = searchChannels(channels, query);
  return new Map(groupNames.map((group) => [group, channelsInGroup(mode, matched, group).length]));
}

/**
 * The `+N` badge: how many other groups the channel belongs to. Always 0 in
 * genre mode — a channel has exactly one genre.
 */
export function extraGroupCount(
  mode: GroupMode,
  channel: Channel,
  activeGroup: string | null,
  searching: boolean,
): number {
  return mode === "genres" ? 0 : extraBlockCount(channel, activeGroup, searching);
}

/** The group a channel launches into the player from (its zap list). */
export function launchGroupFor(
  mode: GroupMode,
  channel: Channel,
  activeGroup: string | null,
): string {
  return mode === "genres" ? genreName(channel) : launchBlockFor(channel, activeGroup);
}

/** A Channel's identity — the GLOSSARY's `(portal, channelId)` pair, as one key. */
export function channelKey(channel: Channel): string {
  return `${channel.portal}:${channel.channelId}`;
}

/** The picker's favourites filter (read-only). */
export type ChannelFilter = "ALL" | "FAVOURITES" | "BLOCK_FAVOURITES";

export const CHANNEL_FILTERS: { key: ChannelFilter; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "FAVOURITES", label: "★ Favourites" },
  { key: "BLOCK_FAVOURITES", label: "★ Block faves" },
];

/** Keep only the channels the filter selects. */
export function applyChannelFilter(channels: Channel[], filter: ChannelFilter): Channel[] {
  switch (filter) {
    case "ALL":
      return channels;
    case "FAVOURITES":
      return channels.filter((channel) => channel.favourite);
    case "BLOCK_FAVOURITES":
      return channels.filter((channel) => channel.blockFavourites.length > 0);
  }
}

/** Favourites first (overall, then block favourites), then by number and name. */
export function sortChannels(channels: Channel[]): Channel[] {
  return [...channels].sort((a, b) => {
    if (a.favourite !== b.favourite) return a.favourite ? -1 : 1;
    const aBlock = a.blockFavourites.length === 0;
    const bBlock = b.blockFavourites.length === 0;
    if (aBlock !== bBlock) return aBlock ? 1 : -1;
    const aNumber = a.number ?? "";
    const bNumber = b.number ?? "";
    if (aNumber !== bNumber) return aNumber < bNumber ? -1 : 1;
    if (a.name !== b.name) return a.name < b.name ? -1 : 1;
    return 0;
  });
}

export interface BlockEntry {
  name: string;
  count: number;
}

/** The Block rail in `blocks` order, with "Other" appended last when needed. */
export function blockRail(blocks: string[], channels: Channel[]): BlockEntry[] {
  const entries = blocks.map((name) => ({
    name,
    count: channels.filter((channel) => channel.blocks.includes(name)).length,
  }));
  const ungrouped = channels.filter((channel) => channel.blocks.length === 0).length;
  return ungrouped > 0 ? [...entries, { name: OTHER_BLOCK, count: ungrouped }] : entries;
}

/** Channels belonging to `block`; "Other" means the ungrouped public channels. */
export function channelsInBlock(channels: Channel[], block: string): Channel[] {
  if (block === OTHER_BLOCK) return channels.filter((channel) => channel.blocks.length === 0);
  return channels.filter((channel) => channel.blocks.includes(block));
}

/** Case-insensitive search across every Block, matching name or number. */
export function searchChannels(channels: Channel[], query: string): Channel[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") return channels;
  return channels.filter(
    (channel) =>
      channel.name.toLowerCase().includes(needle) || (channel.number ?? "").includes(needle),
  );
}

/** Per-Block match counts for the search rail, keyed by rail entry name. */
export function blockMatchCounts(
  channels: Channel[],
  blockNames: string[],
  query: string,
): Map<string, number> {
  const matched = searchChannels(channels, query);
  return new Map(blockNames.map((block) => [block, channelsInBlock(matched, block).length]));
}

/** The `+N` badge: how many other Blocks beyond the active rail entry. */
export function extraBlockCount(
  channel: Channel,
  activeBlock: string | null,
  searching: boolean,
): number {
  if (searching || activeBlock == null || activeBlock === OTHER_BLOCK) return 0;
  return channel.blocks.filter((block) => block !== activeBlock).length;
}

/** The Block a channel launches into the player from (its zap list). */
export function launchBlockFor(channel: Channel, activeBlock: string | null): string {
  if (activeBlock === OTHER_BLOCK && channel.blocks.length === 0) return OTHER_BLOCK;
  if (activeBlock != null && activeBlock !== OTHER_BLOCK && channel.blocks.includes(activeBlock)) {
    return activeBlock;
  }
  return channel.blocks[0] ?? OTHER_BLOCK;
}
