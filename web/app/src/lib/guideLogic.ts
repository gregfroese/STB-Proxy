// Pure helpers for the Guide screen (tickets 04, 09). Ported nowhere: the web viewer is
// the origin of these rules; Android mirrors them.

import { channelKey } from "./pickerLogic";
import type { Channel, GuideHit, GuideProgramme, NowNext } from "./types";

export const GUIDE_MODES = ["prefix", "words", "contains", "exact", "regex"] as const;
export type GuideMode = (typeof GUIDE_MODES)[number];

export const DEFAULT_GUIDE_MODE: GuideMode = "prefix";
export const GUIDE_LIMIT_DEFAULT = 200;
export const GUIDE_LIMIT_MAX = 500;
export const GUIDE_LIMIT_STEP = 200;
export const GUIDE_DEBOUNCE_MS = 300;

/** True while [programme] is on air at [now] (epoch millis). */
export function isAiring(programme: GuideProgramme | null | undefined, now: number): boolean {
  return programme != null && programme.start <= now && programme.stop > now;
}

/** "Showing first N of Y" while more results exist, else a plain count. */
export function resultCountLabel(shown: number, total: number): string {
  if (total > shown) return `Showing first ${shown} of ${total}`;
  return total === 1 ? "1 result" : `${total} results`;
}

/** The next page size for "Load more", capped at the maximum. */
export function nextGuideLimit(current: number): number {
  return Math.min(current + GUIDE_LIMIT_STEP, GUIDE_LIMIT_MAX);
}

/** The distinct Channels a set of hits airs on, in first-seen order (search zap scope). */
export function hitChannels(hits: GuideHit[], channels: Channel[]): Channel[] {
  const wanted = new Map(channels.map((channel) => [channelKey(channel), channel]));
  const out: Channel[] = [];
  const seen = new Set<string>();
  for (const hit of hits) {
    const key = `${hit.portal}:${hit.channelId}`;
    const channel = wanted.get(key);
    if (channel && !seen.has(key)) {
      seen.add(key);
      out.push(channel);
    }
  }
  return out;
}

/** The now/next a Channel shows, from the epg map keyed by epgId. */
export function nowNextForChannel(channel: Channel, epg: Record<string, NowNext>): NowNext | null {
  return channel.epgId ? (epg[channel.epgId] ?? null) : null;
}

/** The channels whose current Programme is airing at [now] (the "On now" filter). */
export function airingChannels(
  channels: Channel[],
  epg: Record<string, NowNext>,
  now: number,
): Channel[] {
  return channels.filter((channel) => {
    const current = nowNextForChannel(channel, epg)?.now ?? null;
    if (current == null) return false;
    const stop = current.stop?.getTime() ?? null;
    return current.start.getTime() <= now && (stop == null || stop > now);
  });
}

/** The channel-name/number sub-filter. */
export function filterChannels(channels: Channel[], text: string): Channel[] {
  const needle = text.trim().toLowerCase();
  if (needle === "") return channels;
  return channels.filter(
    (channel) =>
      channel.name.toLowerCase().includes(needle) || (channel.number ?? "").includes(needle),
  );
}
