// Ported from the Android PlayerLogic.kt (spec 2.6). PlaybackError, EPG refresh
// decisions, now/next resolution, progress and zap.

import type { Channel, NowNext, Programme } from "./types";
import { channelsInBlock } from "./pickerLogic";

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

/** The channel up/down list for a player launched from `launchBlock`. */
export function zapList(channels: Channel[], launchBlock: string): Channel[] {
  return channelsInBlock(channels, launchBlock);
}

/** Steps `current` by `delta` within a list of `size`, wrapping; -1 when empty. */
export function zapIndex(size: number, current: number, delta: number): number {
  if (size <= 0) return -1;
  return (((current + delta) % size) + size) % size;
}

/** The channel `delta` steps away from `current` in `launchBlock`, wrapping. */
export function zapTarget(
  channels: Channel[],
  launchBlock: string,
  current: Channel,
  delta: number,
): Channel | null {
  const list = zapList(channels, launchBlock);
  if (list.length === 0) return null;
  const index = list.findIndex(
    (channel) => channel.portal === current.portal && channel.channelId === current.channelId,
  );
  const next = zapIndex(list.length, index < 0 ? 0 : index, delta);
  return next < 0 ? null : list[next];
}
