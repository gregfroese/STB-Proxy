// Ported from the Android PlayerLogic.kt (spec 2.6). PlaybackError, EPG refresh
// decisions, now/next resolution, progress and zap.

import type { Channel, NowNext, Programme } from "./types";
import { channelKey, channelsInGroup, type GroupMode } from "./pickerLogic";
import type { ZapScope } from "./zapScope";
import { isTvBrowser } from "./device";

export type PlaybackError =
  | { kind: "all_tuners_busy" }
  | { kind: "unreachable" }
  | { kind: "redirect"; target: string | null };

export interface SourceErrorInfo {
  isHttpResponse: boolean;
  responseCode: number | null;
  location: string | null;
}

/** Maps a surfaced source error to one of the three states. */
export function classifySourceError(info: SourceErrorInfo): PlaybackError {
  if (info.isHttpResponse && info.responseCode != null) {
    if (info.responseCode === 503) return { kind: "all_tuners_busy" };
    if ([301, 302, 303, 307, 308].includes(info.responseCode)) {
      return { kind: "redirect", target: info.location };
    }
  }
  return { kind: "unreachable" };
}

export type EpgRefreshAction = "NONE" | "RECOMPUTE" | "REFETCH";

/** True once `now` has entered a different wall-clock minute than `lastComputedAt`. */
export function minuteBoundaryPassed(now: Date, lastComputedAt: Date): boolean {
  return Math.floor(now.getTime() / 60000) !== Math.floor(lastComputedAt.getTime() / 60000);
}

/** True once the currently-airing programme's stop has been reached. */
export function programmeBoundaryPassed(now: Date, currentStop: Date | null): boolean {
  return currentStop != null && now.getTime() >= currentStop.getTime();
}

/** The refresh decision: refetch on a programme boundary, else recompute each minute. */
export function epgRefreshAction(
  now: Date,
  lastComputedAt: Date,
  currentStop: Date | null,
): EpgRefreshAction {
  if (programmeBoundaryPassed(now, currentStop)) return "REFETCH";
  if (minuteBoundaryPassed(now, lastComputedAt)) return "RECOMPUTE";
  return "NONE";
}

/** Re-derives the now/next to display at `now` from a stored snapshot. */
export function resolveNowNext(stored: NowNext | null, now: Date): NowNext | null {
  if (stored == null) return null;
  const current = stored.now;
  const stillAiring =
    current != null &&
    current.start.getTime() <= now.getTime() &&
    (current.stop == null || now.getTime() < current.stop.getTime());
  if (stillAiring) return stored;

  const promoted =
    stored.next != null && stored.next.start.getTime() <= now.getTime() ? stored.next : null;
  if (promoted != null) return { now: promoted, next: null };
  return { now: null, next: stored.next };
}

/** Fraction of the programme elapsed at `now`, clamped to 0..1; 0 when unbounded. */
export function programmeProgress(programme: Programme | null, now: Date): number {
  const stop = programme?.stop;
  if (programme == null || stop == null) return 0;
  const total = stop.getTime() - programme.start.getTime();
  if (total <= 0) return 0;
  const elapsed = now.getTime() - programme.start.getTime();
  return Math.min(1, Math.max(0, elapsed / total));
}

/** The channel up/down list for a player launched from `launchGroup`. */
export function zapList(
  channels: Channel[],
  launchGroup: string,
  mode: GroupMode = "blocks",
): Channel[] {
  return channelsInGroup(mode, channels, launchGroup);
}

/**
 * The ordered up/down list for a player launched under [scope] (ticket 07): a `group`
 * re-derives from the lineup as today; a `list` maps its keys to the lineup, preserving
 * the given order, and keeps [launched] even if the set no longer holds it.
 */
export function scopeZapList(
  channels: Channel[],
  scope: ZapScope,
  mode: GroupMode,
  launched: Channel | null,
): Channel[] {
  if (scope.kind === "group") return channelsInGroup(mode, channels, scope.block);

  const byKey = new Map(channels.map((channel) => [channelKey(channel), channel]));
  const seen = new Set<string>();
  const list: Channel[] = [];
  for (const key of scope.keys) {
    const channel = byKey.get(key);
    if (channel && !seen.has(key)) {
      seen.add(key);
      list.push(channel);
    }
  }
  if (launched) {
    const key = channelKey(launched);
    if (!seen.has(key)) list.unshift(launched);
  }
  return list;
}

/** Steps [current] by [delta] through every [channels] entry, wrapping (Multiview, ticket 10). */
export function zapWithin(channels: Channel[], current: Channel, delta: number): Channel | null {
  if (channels.length === 0) return null;
  const index = channels.findIndex(
    (channel) => channel.portal === current.portal && channel.channelId === current.channelId,
  );
  const next = zapIndex(channels.length, index < 0 ? 0 : index, delta);
  return next < 0 ? null : channels[next];
}

/** Steps `current` by `delta` within a list of `size`, wrapping; -1 when empty. */
export function zapIndex(size: number, current: number, delta: number): number {
  if (size <= 0) return -1;
  return (((current + delta) % size) + size) % size;
}

/** The channel `delta` steps away from `current` in `launchGroup`, wrapping. */
export function zapTarget(
  channels: Channel[],
  launchGroup: string,
  current: Channel,
  delta: number,
  mode: GroupMode = "blocks",
): Channel | null {
  const list = zapList(channels, launchGroup, mode);
  if (list.length === 0) return null;
  const index = list.findIndex(
    (channel) => channel.portal === current.portal && channel.channelId === current.channelId,
  );
  const next = zapIndex(list.length, index < 0 ? 0 : index, delta);
  return next < 0 ? null : list[next];
}

export type FullscreenStrategy = "video" | "page" | "window";

/**
 * How full screen is done.
 * - "video": phones fullscreen the video element itself, because fullscreening a
 *   container with an MSE video stalls on some Android Chrome versions.
 * - "window": TV apps' built-in browsers (a WebView, e.g. Downloader on Fire TV)
 *   only grow the player to fill the browser. A WebView hands a fullscreened page
 *   to a separate view, but Fire TV keeps placing the hardware video layer by the
 *   original browser view, so the picture stays at its old size.
 * - "page": other TV browsers (Silk) and desktop grow the player to fill the page
 *   and fullscreen the page; a fullscreened <video> keeps its old size on TV.
 */
export function fullscreenStrategy(userAgent: string, coarsePointer: boolean): FullscreenStrategy {
  const tv = isTvBrowser(userAgent);
  if (coarsePointer && !tv) return "video";
  return tv && /\bwv\b/.test(userAgent) ? "window" : "page";
}
