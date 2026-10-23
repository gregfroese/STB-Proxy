// Pure logic for a title's page (ticket 11; UX settled in On Demand issue 09): the Play
// buttons from 07's `progress`/`upNext`, Seasons and Episodes, and Play's error wording.

import { ApiError } from "./api";
import { clock } from "./onDemandLogic";
import type {
  OnDemandDetail,
  OnDemandEpisode,
  OnDemandKey,
  OnDemandProgress,
  OnDemandSeason,
  OnDemandUpNext,
} from "./types";

/** Play's errors that 09 words for the viewer, by the server's `code`. */
const PLAY_ERRORS: Record<string, string> = {
  busy: "Someone else on this login is already watching — On Demand uses the same stream as live TV. Stop the other stream and try again.",
  not_found: "This title isn't available any more.",
  portal_error: "The provider didn't answer. Try again in a moment.",
};

/** The line shown under the Play button when POST /play fails. */
export function playErrorText(error: unknown): string {
  if (error instanceof ApiError) return PLAY_ERRORS[error.code] ?? error.message;
  return "Couldn't start playback. Try again.";
}

/** A Play button: its label and where playback starts. */
export interface PlayButton {
  label: string;
  startSec: number;
}

export interface MovieActions {
  primary: PlayButton;
  /** Show "Start over" beside a Resume. */
  startOver: boolean;
  /** The Mark watched / ✓ Watched toggle: its label and the current state. */
  mark: { label: string; watched: boolean };
}

/**
 * A Movie's buttons: Resume from its Resume point (plus Start over), Play again once
 * Watched, otherwise Play. Watched wins over a Resume point (ADR 0006).
 */
export function movieActions(progress: OnDemandProgress | null | undefined): MovieActions {
  const watched = progress?.watched ?? false;
  const resumeAt = watched ? null : (progress?.positionSec ?? null);
  const mark = { label: watched ? "✓ Watched" : "Mark watched", watched };
  if (resumeAt != null && resumeAt > 0) {
    return {
      primary: { label: `▶ Resume from ${clock(resumeAt)}`, startSec: resumeAt },
      startOver: true,
      mark,
    };
  }
  return {
    primary: { label: watched ? "▶ Play again" : "▶ Play", startSec: 0 },
    startOver: false,
    mark,
  };
}

/** The facts line before the boxed age rating and ★: year, "n min" or "n Seasons". */
export function facts(detail: OnDemandDetail): string[] {
  const parts: string[] = [];
  if (detail.year != null) parts.push(String(detail.year));
  if (detail.kind === "series") {
    const count = detail.seasons?.length ?? 0;
    if (count > 0) parts.push(`${count} Season${count === 1 ? "" : "s"}`);
  } else if (detail.durationMin != null) {
    parts.push(`${detail.durationMin} min`);
  }
  return parts;
}

function list(text: string | null | undefined): string[] {
  return (text ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

/** The portal's comma-separated genres as tags. */
export function genreTags(genres: string | null | undefined): string[] {
  return list(genres);
}

/** Cast shows this many names, then "+n more". */
export const CAST_SHOWN = 5;

export interface Credit {
  label: string;
  value: string;
  more: string | null;
}

/** The credits list: Director, Cast (the first five, "+n more") and Country, when sent. */
export function credits(detail: OnDemandDetail): Credit[] {
  const rows: Credit[] = [];
  if (detail.director) rows.push({ label: "Director", value: detail.director, more: null });
  const cast = list(detail.actors);
  if (cast.length > 0) {
    const rest = cast.length - CAST_SHOWN;
    rows.push({
      label: "Cast",
      value: cast.slice(0, CAST_SHOWN).join(", "),
      more: rest > 0 ? `+${rest} more` : null,
    });
  }
  if (detail.country) rows.push({ label: "Country", value: detail.country, more: null });
  return rows;
}

/**
 * A Movie's progress once PUT progress {watched} has succeeded, as 07 stores it: Watched
 * drops the Resume point; unmarking forgets the Movie entirely. `now` is epoch seconds.
 */
export function markedProgress(
  progress: OnDemandProgress | null | undefined,
  watched: boolean,
  now: number,
): OnDemandProgress | null {
  if (!watched) return null;
  return {
    positionSec: null,
    durationSec: progress?.durationSec ?? null,
    watched: true,
    updatedAt: now,
  };
}

/** What Play hands the player: the item and where to start (the player never asks). */
export interface PlayStart {
  key: OnDemandKey;
  startSec: number;
}

/** The player's address (ticket 12): the item key and the start, so a reload can reopen it. */
export function watchPath(start: PlayStart): string {
  const key = start.key;
  const params = new URLSearchParams({ portal: key.portal });
  if ("id" in key) {
    params.set("id", key.id);
  } else {
    params.set("series", key.seriesId);
    params.set("season", key.seasonId);
    params.set("episode", key.episodeId);
  }
  const startSec = Math.max(0, Math.floor(start.startSec));
  if (startSec > 0) params.set("start", String(startSec));
  return `/ondemand/watch?${params.toString()}`;
}

/** The PlayStart in a player address, or null when it doesn't name a Movie or Episode. */
export function watchFromQuery(query: URLSearchParams): PlayStart | null {
  const portal = query.get("portal");
  if (!portal) return null;
  const start = Number(query.get("start") ?? 0);
  const startSec = Number.isFinite(start) && start > 0 ? Math.floor(start) : 0;
  const id = query.get("id");
  if (id) return { key: { portal, id }, startSec };
  const seriesId = query.get("series");
  const seasonId = query.get("season");
  const episodeId = query.get("episode");
  if (seriesId && seasonId && episodeId) {
    return { key: { portal, seriesId, seasonId, episodeId }, startSec };
  }
  return null;
}

/** "S2 E4", leaving out a number the portal didn't give. */
export function episodeCode(seasonNumber: number | null, episodeNumber: number | null): string {
  const parts: string[] = [];
  if (seasonNumber != null) parts.push(`S${seasonNumber}`);
  if (episodeNumber != null) parts.push(`E${episodeNumber}`);
  return parts.join(" ");
}

/** An Episode's name, or "Episode n" (Xtream and legacy portals send none). */
export function episodeName(name: string | null, number: number | null): string {
  return name || (number != null ? `Episode ${number}` : "Episode");
}

/** The player's title: the Movie, or "Series · S2 E4 · Name". */
export function playTitle(
  name: string,
  episode: { seasonNumber: number | null; number: number | null; name: string | null } | null,
): string {
  if (!episode) return name;
  const code = episodeCode(episode.seasonNumber, episode.number);
  return [name, code, episodeName(episode.name, episode.number)].filter((part) => part).join(" · ");
}

/** The Season chip selected on open: Up next's Season, else the first. null with none. */
export function openingSeason(
  seasons: OnDemandSeason[],
  next: OnDemandUpNext | null | undefined,
): string | null {
  if (next && seasons.some((season) => season.id === next.seasonId)) return next.seasonId;
  return seasons[0]?.id ?? null;
}

/** A Season chip's label: the portal's name, else "Season n". */
export function seasonLabel(season: OnDemandSeason): string {
  return season.name || (season.number != null ? `Season ${season.number}` : "Season");
}

export interface EpisodeRow {
  number: string;
  name: string;
  /** "✓ Watched", "mm:ss in" or "". */
  status: string;
  watched: boolean;
  /** The thin bar, 0-1, or null for none. */
  progress: number | null;
  upNext: boolean;
  /** Tapping the row: its Resume point unless Watched, else the start. */
  start: PlayStart;
}

/** One row of a Season's Episode list. */
export function episodeRow(
  series: Pick<OnDemandDetail, "portal" | "id">,
  episode: OnDemandEpisode,
  next: OnDemandUpNext | null | undefined,
): EpisodeRow {
  const progress = episode.progress;
  const watched = progress?.watched ?? false;
  const resumeAt =
    !watched && progress?.positionSec != null && progress.positionSec > 0
      ? progress.positionSec
      : null;
  return {
    number: episode.number != null ? String(episode.number) : "",
    name: episodeName(episode.name, episode.number),
    status: watched ? "✓ Watched" : resumeAt != null ? `${clock(resumeAt)} in` : "",
    watched,
    progress:
      resumeAt != null && progress?.durationSec
        ? Math.min(1, resumeAt / progress.durationSec)
        : null,
    upNext: next != null && next.seasonId === episode.seasonId && next.episodeId === episode.id,
    start: {
      key: {
        portal: series.portal,
        seriesId: series.id,
        seasonId: episode.seasonId,
        episodeId: episode.id,
      },
      startSec: resumeAt ?? 0,
    },
  };
}

export interface SeriesPlay {
  label: string;
  /** The Episode's name, and "from mm:ss" when resuming. */
  sub: string | null;
  /** null until the first Season's Episodes have loaded. */
  start: PlayStart | null;
}

/**
 * A Series' main button: Resume/Play its Up next, else Play the first Episode of the
 * first Season (`firstEpisodes`, null while loading). null when there is nothing to play.
 */
export function seriesPlay(
  series: Pick<OnDemandDetail, "portal" | "id" | "seasons" | "upNext">,
  firstEpisodes: OnDemandEpisode[] | null,
): SeriesPlay | null {
  const next = series.upNext;
  if (next) {
    const resumeAt = next.positionSec != null && next.positionSec > 0 ? next.positionSec : null;
    const name = episodeName(next.name, next.episodeNumber);
    return {
      label:
        `▶ ${resumeAt != null ? "Resume" : "Play"} ${episodeCode(next.seasonNumber, next.episodeNumber)}`.trimEnd(),
      sub: resumeAt != null ? `${name} · from ${clock(resumeAt)}` : name,
      start: {
        key: {
          portal: series.portal,
          seriesId: series.id,
          seasonId: next.seasonId,
          episodeId: next.episodeId,
        },
        startSec: resumeAt ?? 0,
      },
    };
  }
  const first = series.seasons?.[0];
  if (!first || firstEpisodes?.length === 0) return null;
  const episode = firstEpisodes?.[0] ?? null;
  const code = episodeCode(first.number ?? 1, episode ? episode.number : 1);
  return {
    label: `▶ Play ${code}`.trimEnd(),
    sub: episode?.name ?? null,
    start: episode
      ? {
          key: {
            portal: series.portal,
            seriesId: series.id,
            seasonId: first.id,
            episodeId: episode.id,
          },
          startSec: 0,
        }
      : null,
  };
}
