// Pure logic for the On Demand player (ticket 12; settled in On Demand issue 11): seek
// steps, the key map, the end card, progress report scheduling and the session-ended
// states. The route (routes/OnDemandWatch.svelte) wires these to the <video> and the API.

import { ApiError } from "./api";
import { episodeCode, episodeName, facts, playErrorText, seasonLabel } from "./onDemandDetailLogic";
import { clock } from "./onDemandLogic";
import type { OnDemandDetail, OnDemandEpisode, OnDemandSeason } from "./types";

/** A held D-pad ← → steps 10 s, then 30 s after 1 s, then 60 s after 3 s. */
export function seekStep(heldMs: number): number {
  if (heldMs >= 3000) return 60;
  if (heldMs >= 1000) return 30;
  return 10;
}

export type PlayerKeyAction =
  | { type: "toggle" }
  | { type: "seek"; by: number }
  | { type: "fullscreen" }
  | { type: "mute" }
  | { type: "next" }
  /** Web: leave full screen, else leave the player. */
  | { type: "escape" }
  /** TV: hide the controls when they're up, else leave the player. */
  | { type: "back" }
  | { type: "showControls" };

export interface KeyContext {
  /** The web's TV mode (D-pad), not a keyboard. */
  tv: boolean;
  controlsVisible: boolean;
  /** Keyboard focus is on the seek bar. */
  onBar: boolean;
  /**
   * "end": the end card, where ← seeks back out of it (on TV, only from its first
   * button); "modal": "Still watching?" or a session overlay, whose buttons keep the keys.
   */
  card: "end" | "modal" | null;
  /** How long ← → has been held, for the TV's acceleration. */
  heldMs: number;
}

const BACK_KEYS = new Set(["Escape", "Backspace", "GoBack", "BrowserBack"]);

/** What a key press does in the player, or null to leave it to the browser (focus, buttons). */
export function playerKey(
  input: { key: string; shiftKey: boolean },
  ctx: KeyContext,
): PlayerKeyAction | null {
  const key = input.key;
  const horizontal = key === "ArrowLeft" || key === "ArrowRight";
  const sign = key === "ArrowLeft" ? -1 : 1;

  if (ctx.tv && BACK_KEYS.has(key)) return { type: "back" };
  if (!ctx.tv && key === "Escape") return { type: "escape" };

  if (ctx.card === "modal") return null;
  if (ctx.card === "end") {
    return key === "ArrowLeft" ? { type: "seek", by: -(ctx.tv ? seekStep(ctx.heldMs) : 10) } : null;
  }

  if (key === "MediaPlayPause" || key === " ") return { type: "toggle" };

  if (ctx.tv) {
    if (horizontal) {
      return !ctx.controlsVisible || ctx.onBar
        ? { type: "seek", by: sign * seekStep(ctx.heldMs) }
        : null;
    }
    if (ctx.controlsVisible) return null;
    if (key === "Enter") return { type: "toggle" };
    if (key === "ArrowUp" || key === "ArrowDown") return { type: "showControls" };
    return null;
  }

  if (horizontal) return { type: "seek", by: sign * (input.shiftKey ? 60 : 10) };
  switch (key.toLowerCase()) {
    case "k":
      return { type: "toggle" };
    case "f":
      return { type: "fullscreen" };
    case "m":
      return { type: "mute" };
    case "n":
      return { type: "next" };
    default:
      return null;
  }
}

/** The end card's countdown, before the next Episode plays or the player goes back. */
export const END_CARD_MS = 15000;
/** "Still watching?" replaces the next-Episode card after this many autoplays in a row. */
export const STILL_WATCHING_AFTER = 3;

/**
 * What takes over when an Episode or Movie ends: the next Episode with a countdown,
 * "Still watching?" (no countdown), or ✓ Watched for a Movie or the last Episode.
 */
export type EndCard =
  { kind: "next"; until: number } | { kind: "still" } | { kind: "done"; until: number };

export function endCardFor(o: { hasNext: boolean; autoplays: number; now: number }): EndCard {
  if (!o.hasNext) return { kind: "done", until: o.now + END_CARD_MS };
  if (o.autoplays >= STILL_WATCHING_AFTER) return { kind: "still" };
  return { kind: "next", until: o.now + END_CARD_MS };
}

/** What the card does by itself at `now`: autoplay the next Episode, go back, or nothing yet. */
export function endCardDue(card: EndCard, now: number): "autoplay" | "back" | null {
  if (card.kind === "still" || now < card.until) return null;
  return card.kind === "next" ? "autoplay" : "back";
}

/** The countdown's whole seconds left (0 for "Still watching?"). */
export function secondsLeft(card: EndCard, now: number): number {
  if (card.kind === "still") return 0;
  return Math.max(0, Math.ceil((card.until - now) / 1000));
}

/** Autoplays in a row: an autoplay adds one; any input or a hand-picked Next Episode resets. */
export function autoplaysAfter(count: number, what: "autoplay" | "manual" | "input"): number {
  return what === "autoplay" ? count + 1 : 0;
}

/** The controls fade this long after the last input while playing. */
export const CONTROLS_HIDE_MS = 4000;

/** Whether the controls show: always while paused, loading or dragging the bar. */
export function controlsShown(o: {
  playing: boolean;
  busy: boolean;
  dragging: boolean;
  sinceInputMs: number;
}): boolean {
  return !o.playing || o.busy || o.dragging || o.sinceInputMs < CONTROLS_HIDE_MS;
}

export type AspectMode = "auto" | "16:9" | "4:3" | "zoom";
export const ASPECTS: AspectMode[] = ["auto", "16:9", "4:3", "zoom"];
export const ASPECT_LABELS: Record<AspectMode, string> = {
  auto: "Auto",
  "16:9": "16:9",
  "4:3": "4:3",
  zoom: "Zoom",
};

/** The Aspect button cycles Auto · 16:9 · 4:3 · Zoom. */
export function nextAspect(mode: AspectMode): AspectMode {
  return ASPECTS[(ASPECTS.indexOf(mode) + 1) % ASPECTS.length];
}

/** The Episode after `currentId` in its Season, or null after the last (or if unknown). */
export function nextEpisode(
  episodes: OnDemandEpisode[],
  currentId: string,
): OnDemandEpisode | null {
  const index = episodes.findIndex((episode) => episode.id === currentId);
  return index >= 0 ? (episodes[index + 1] ?? null) : null;
}

/** The Season after `seasonId`, whose first Episode follows the last one of this Season. */
export function seasonAfter(seasons: OnDemandSeason[], seasonId: string): OnDemandSeason | null {
  const index = seasons.findIndex((season) => season.id === seasonId);
  return index >= 0 ? (seasons[index + 1] ?? null) : null;
}

/** The top bar: a Movie's title with "year · n min", or the Series with "S2 · E4 · Name". */
export function playerHeading(
  detail: OnDemandDetail,
  episode: OnDemandEpisode | null,
  season: OnDemandSeason | null,
): { title: string; sub: string } {
  if (!episode) return { title: detail.name, sub: facts(detail).join(" · ") };
  const parts: string[] = [];
  if (season?.number != null) parts.push(`S${season.number}`);
  if (episode.number != null) parts.push(`E${episode.number}`);
  parts.push(episodeName(episode.name, episode.number));
  return { title: detail.name, sub: parts.join(" · ") };
}

/** The next-Episode card: "S2 E5 · Name" and "44 min · Season 2" (the length when known). */
export function nextCardText(
  episode: OnDemandEpisode,
  season: OnDemandSeason | null,
): { name: string; facts: string } {
  const code = episodeCode(season?.number ?? null, episode.number);
  const name = [code, episodeName(episode.name, episode.number)].filter((p) => p).join(" · ");
  const parts: string[] = [];
  const duration = episode.progress?.durationSec;
  if (duration) parts.push(`${Math.round(duration / 60)} min`);
  if (season) parts.push(seasonLabel(season));
  return { name, facts: parts.join(" · ") };
}

/** The ✓ Watched card's title: the Movie, or "<Series> · Season n finished". */
export function doneTitle(detail: OnDemandDetail, season: OnDemandSeason | null): string {
  if (detail.kind !== "series") return detail.name;
  return season ? `${detail.name} · ${seasonLabel(season)} finished` : detail.name;
}

/** What covers the picture when the session can't carry on (09's wording). */
export type PlayerOverlay = "evicted" | "stopped" | "busy" | "error";

export type StreamFailure =
  /** 410 `idle`: open a new session with `replaces` at the same position, silently. */
  | { kind: "restart" }
  | { kind: "overlay"; overlay: PlayerOverlay }
  /** 404 `on_demand_off`: On Demand was switched off for this login. */
  | { kind: "off" };

/**
 * The stream stopped loading: `status` and `body` are what the session's playlist answers
 * when fetched again (null when it can't be reached). 410 `session_ended` says why (ADR
 * 0005); a session the server no longer knows is presented like a stopped one.
 */
export function streamFailure(status: number | null, body: unknown): StreamFailure {
  const fields = (body ?? {}) as { code?: unknown; reason?: unknown };
  if (status === 404 && fields.code === "on_demand_off") return { kind: "off" };
  if (status === 410) {
    if (fields.reason === "idle") return { kind: "restart" };
    return { kind: "overlay", overlay: fields.reason === "evicted" ? "evicted" : "stopped" };
  }
  return { kind: "overlay", overlay: "error" };
}

export const IDLE_RESTART_BUSY_TOAST = "Couldn't restart — someone else on this login is watching.";

/**
 * POST /play failed inside the player (an idle restart, Resume, Try again or the next
 * Episode): 503 `busy` gets the busy overlay, plus the toast when it was the silent restart.
 */
export function playFailure(
  error: unknown,
  idleRestart: boolean,
): { toast: string | null; overlay: PlayerOverlay } {
  const busy = error instanceof ApiError && error.status === 503;
  return {
    toast: busy && idleRestart ? IDLE_RESTART_BUSY_TOAST : null,
    overlay: busy ? "busy" : "error",
  };
}

const OVERLAY_BODY: Record<"evicted" | "stopped", string> = {
  evicted:
    "Playback stopped — someone started watching on another device with this login, and the provider only allows one stream at a time.",
  stopped: "The stream was stopped from the server's Streams page.",
};

/** The overlay's title, text and main button; `message` is the error overlay's text. */
export function overlayCopy(
  overlay: PlayerOverlay,
  positionSec: number,
  message: string | null,
): { title: string; body: string; primary: string } {
  if (overlay === "busy") {
    return {
      title: "Couldn't continue",
      body: playErrorText(new ApiError(503, "busy", "")),
      primary: "Try again",
    };
  }
  if (overlay === "error") {
    return {
      title: "Playback stopped",
      body: message ?? "Couldn't keep playing this title.",
      primary: "Try again",
    };
  }
  return {
    title: "Playback stopped",
    body: OVERLAY_BODY[overlay],
    primary: `▶ Resume from ${clock(positionSec)}`,
  };
}

/** Progress is reported after this many seconds of playback (ADR 0006). */
export const REPORT_EVERY_SEC = 30;

/** A playback report's numbers (PUT /api/ondemand/progress, with the item key). */
export interface ProgressSample {
  positionSec: number;
  durationSec: number | null;
}

export interface ProgressReporter {
  /** Seconds of actual playback since the last call; reports once 30 s have played. */
  played(seconds: number): void;
  /** Report now (pause, Back, end, hand-over, hidden page), restarting the 30 s. */
  now(keepalive?: boolean): void;
}

/**
 * Schedules the player's progress reports. `sample` is null until playback has reached
 * its start position, so a report never records 0:00 over a Resume point.
 */
export function createProgressReporter(o: {
  sample: () => ProgressSample | null;
  send: (sample: ProgressSample, keepalive: boolean) => void;
}): ProgressReporter {
  let playedSec = 0;
  const report = (keepalive: boolean) => {
    const sample = o.sample();
    if (!sample) return;
    playedSec = 0;
    o.send(sample, keepalive);
  };
  return {
    played(seconds) {
      playedSec += seconds;
      if (playedSec >= REPORT_EVERY_SEC) report(false);
    },
    now(keepalive = false) {
      report(keepalive);
    },
  };
}
