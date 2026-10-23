import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import type {
  OnDemandDetail,
  OnDemandEpisode,
  OnDemandProgress,
  OnDemandSeason,
  OnDemandUpNext,
} from "./types";
import {
  credits,
  episodeRow,
  facts,
  genreTags,
  markedProgress,
  movieActions,
  openingSeason,
  playErrorText,
  seasonErrorText,
  TITLE_GONE,
  playTitle,
  seasonLabel,
  seriesPlay,
  watchFromQuery,
  watchPath,
} from "./onDemandDetailLogic";

function progress(extra: Partial<OnDemandProgress> = {}): OnDemandProgress {
  return { positionSec: null, durationSec: 5400, watched: false, updatedAt: 1, ...extra };
}

describe("movieActions", () => {
  it("offers Play from the start, and Mark watched, for a Movie never played", () => {
    expect(movieActions(null)).toEqual({
      primary: { label: "▶ Play", startSec: 0 },
      startOver: false,
      mark: { label: "Mark watched", watched: false },
    });
  });

  it("offers Resume from the Resume point and Start over", () => {
    const actions = movieActions(progress({ positionSec: 754 }));
    expect(actions.primary).toEqual({ label: "▶ Resume from 12:34", startSec: 754 });
    expect(actions.startOver).toBe(true);
    expect(actions.mark).toEqual({ label: "Mark watched", watched: false });
  });

  it("offers Play again from the start once Watched, even with a newer Resume point", () => {
    for (const watched of [
      progress({ watched: true }),
      progress({ watched: true, positionSec: 900 }),
    ]) {
      expect(movieActions(watched)).toEqual({
        primary: { label: "▶ Play again", startSec: 0 },
        startOver: false,
        mark: { label: "✓ Watched", watched: true },
      });
    }
  });
});

describe("seasonErrorText", () => {
  it("blames the portal for a portal_error, and says so plainly otherwise", () => {
    expect(seasonErrorText(new ApiError(502, "portal_error", "x"))).toBe(
      "The portal didn't send this Season's Episodes. Try again in a moment.",
    );
    expect(seasonErrorText(new TypeError("Failed to fetch"))).toBe(
      "Couldn't load this Season's Episodes.",
    );
  });
});

describe("playErrorText", () => {
  it("words busy, not_found and portal_error as decided in 09", () => {
    expect(playErrorText(new ApiError(503, "busy", "All tuners are busy"))).toBe(
      "Someone else on this login is already watching — On Demand uses the same stream as live TV. Stop the other stream and try again.",
    );
    expect(playErrorText(new ApiError(404, "not_found", "That isn't in On Demand"))).toBe(
      "This title isn't available any more.",
    );
    expect(playErrorText(new ApiError(502, "portal_error", "The portal didn't answer"))).toBe(
      "The portal didn't answer. Try again in a moment.",
    );
  });

  it("says a missing title is gone in the title page's own words", () => {
    expect(TITLE_GONE).toBe("This title isn't available any more.");
  });

  it("falls back to the server's own words, or a generic line when there are none", () => {
    expect(
      playErrorText(new ApiError(502, "unsupported_stream", "That title can't be played here")),
    ).toBe("That title can't be played here");
    expect(playErrorText(new TypeError("Failed to fetch"))).toBe(
      "Couldn't start playback. Try again.",
    );
  });
});

function upNext(extra: Partial<OnDemandUpNext> = {}): OnDemandUpNext {
  return {
    seasonId: "s2",
    seasonNumber: 2,
    episodeId: "e4",
    episodeNumber: 4,
    name: "The Ledger",
    positionSec: null,
    durationSec: 2700,
    ...extra,
  };
}

function season(
  id: string,
  number: number | null,
  extra: Partial<OnDemandSeason> = {},
): OnDemandSeason {
  return { id, number, name: null, episodeCount: 8, ...extra };
}

function episode(
  id: string,
  number: number | null,
  extra: Partial<OnDemandEpisode> = {},
): OnDemandEpisode {
  return { id, seasonId: "s1", number, name: null, progress: null, ...extra };
}

const SEASONS = [season("s1", 1), season("s2", 2)];

describe("seriesPlay", () => {
  it("resumes Up next from its Resume point", () => {
    const play = seriesPlay(
      { portal: "p", id: "77", seasons: SEASONS, upNext: upNext({ positionSec: 840 }) },
      null,
    );
    expect(play).toEqual({
      label: "▶ Resume S2 E4",
      sub: "The Ledger · from 14:00",
      start: {
        key: { portal: "p", seriesId: "77", seasonId: "s2", episodeId: "e4" },
        startSec: 840,
      },
    });
  });

  it("plays Up next from the start when it has no Resume point, naming it Episode n without a name", () => {
    const play = seriesPlay(
      { portal: "p", id: "77", seasons: SEASONS, upNext: upNext({ name: null }) },
      null,
    );
    expect(play?.label).toBe("▶ Play S2 E4");
    expect(play?.sub).toBe("Episode 4");
    expect(play?.start?.startSec).toBe(0);
  });

  it("plays the first Episode of the first Season without an Up next, once it's loaded", () => {
    const series = { portal: "p", id: "77", seasons: SEASONS, upNext: null };
    expect(seriesPlay(series, null)).toEqual({ label: "▶ Play S1 E1", sub: null, start: null });
    expect(seriesPlay(series, [episode("101", 1, { name: "Pilot" }), episode("102", 2)])).toEqual({
      label: "▶ Play S1 E1",
      sub: "Pilot",
      start: {
        key: { portal: "p", seriesId: "77", seasonId: "s1", episodeId: "101" },
        startSec: 0,
      },
    });
  });

  it("has no button for a Series with no Seasons, or a first Season with no Episodes", () => {
    expect(seriesPlay({ portal: "p", id: "77", seasons: [], upNext: null }, null)).toBeNull();
    expect(seriesPlay({ portal: "p", id: "77", seasons: SEASONS, upNext: null }, [])).toBeNull();
  });
});

describe("openingSeason", () => {
  it("opens on the Up next Season, else the first, else none", () => {
    expect(openingSeason(SEASONS, upNext())).toBe("s2");
    expect(openingSeason(SEASONS, null)).toBe("s1");
    expect(openingSeason(SEASONS, upNext({ seasonId: "gone" }))).toBe("s1");
    expect(openingSeason([], null)).toBeNull();
  });
});

describe("seasonLabel", () => {
  it("uses the portal's name, else Season n", () => {
    expect(seasonLabel(season("s1", 1, { name: "Specials" }))).toBe("Specials");
    expect(seasonLabel(season("s3", 3))).toBe("Season 3");
    expect(seasonLabel(season("x", null))).toBe("Season");
  });
});

describe("episodeRow", () => {
  const SERIES = { portal: "p", id: "77" };
  const watchedAt = { positionSec: null, durationSec: 2700, watched: true, updatedAt: 1 };

  it("shows a fresh Episode with its name, or Episode n, and plays it from the start", () => {
    expect(episodeRow(SERIES, episode("e1", 1, { name: "Pilot" }), null)).toEqual({
      number: "1",
      name: "Pilot",
      status: "",
      watched: false,
      progress: null,
      upNext: false,
      start: { key: { portal: "p", seriesId: "77", seasonId: "s1", episodeId: "e1" }, startSec: 0 },
    });
    expect(episodeRow(SERIES, episode("e5", 5), null).name).toBe("Episode 5");
  });

  it("shows mm:ss in and a bar for a Resume point, and tapping resumes there", () => {
    const row = episodeRow(
      SERIES,
      episode("e2", 2, { progress: { ...watchedAt, watched: false, positionSec: 675 } }),
      null,
    );
    expect(row.status).toBe("11:15 in");
    expect(row.progress).toBeCloseTo(0.25);
    expect(row.start.startSec).toBe(675);
  });

  it("shows ✓ Watched with no bar, and plays a Watched Episode from the start", () => {
    const row = episodeRow(
      SERIES,
      episode("e3", 3, { progress: { ...watchedAt, positionSec: 900 } }),
      null,
    );
    expect(row).toMatchObject({ status: "✓ Watched", watched: true, progress: null });
    expect(row.start.startSec).toBe(0);
  });

  it("marks the Up next Episode", () => {
    const next = upNext({ seasonId: "s1", episodeId: "e4" });
    expect(episodeRow(SERIES, episode("e4", 4), next).upNext).toBe(true);
    expect(episodeRow(SERIES, episode("e4", 4, { seasonId: "s2" }), next).upNext).toBe(false);
  });
});

function detail(extra: Partial<OnDemandDetail> = {}): OnDemandDetail {
  return {
    portal: "p",
    portalName: "Alpha",
    id: "9",
    kind: "movie",
    name: "Harbor",
    year: null,
    rating: null,
    added: null,
    poster: null,
    description: null,
    genres: null,
    director: null,
    actors: null,
    country: null,
    durationMin: null,
    ageRating: null,
    categories: [],
    ...extra,
  };
}

describe("facts", () => {
  it("lists year and minutes for a Movie, Seasons for a Series, leaving out what's missing", () => {
    expect(facts(detail({ year: 2019, durationMin: 104 }))).toEqual(["2019", "104 min"]);
    expect(facts(detail({ kind: "series", seasons: [season("s1", 1)] }))).toEqual(["1 Season"]);
    expect(facts(detail({ kind: "series", year: 2020, seasons: SEASONS }))).toEqual([
      "2020",
      "2 Seasons",
    ]);
    expect(facts(detail())).toEqual([]);
  });
});

describe("genreTags", () => {
  it("splits the portal's genre list into tags", () => {
    expect(genreTags("Drama, Crime ,Thriller")).toEqual(["Drama", "Crime", "Thriller"]);
    expect(genreTags(null)).toEqual([]);
  });
});

describe("credits", () => {
  it("lists Director, the first five of the Cast with +n more, and Country", () => {
    expect(
      credits(
        detail({
          director: "A. Director",
          actors: "One, Two, Three, Four, Five, Six, Seven",
          country: "Canada",
        }),
      ),
    ).toEqual([
      { label: "Director", value: "A. Director", more: null },
      { label: "Cast", value: "One, Two, Three, Four, Five", more: "+2 more" },
      { label: "Country", value: "Canada", more: null },
    ]);
  });

  it("leaves out what the portal didn't send", () => {
    expect(credits(detail({ actors: "Solo" }))).toEqual([
      { label: "Cast", value: "Solo", more: null },
    ]);
    expect(credits(detail())).toEqual([]);
  });
});

describe("watchPath / watchFromQuery", () => {
  const read = (path: string) => watchFromQuery(new URL(path, "http://x").searchParams);

  it("addresses a Movie and where it starts", () => {
    const path = watchPath({ key: { portal: "p/1", id: "9" }, startSec: 754 });
    expect(path).toBe("/ondemand/watch?portal=p%2F1&id=9&start=754");
    expect(read(path)).toEqual({ key: { portal: "p/1", id: "9" }, startSec: 754 });
  });

  it("addresses an Episode by Series, Season and Episode, leaving out a start of 0", () => {
    const start = {
      key: { portal: "p", seriesId: "77", seasonId: "s2", episodeId: "e4" },
      startSec: 0,
    };
    const path = watchPath(start);
    expect(path).toBe("/ondemand/watch?portal=p&series=77&season=s2&episode=e4");
    expect(read(path)).toEqual(start);
  });

  it("reads nothing from an address that doesn't name an item, and no start as 0", () => {
    expect(read("/ondemand/watch?portal=p")).toBeNull();
    expect(read("/ondemand/watch?portal=p&series=77&season=s2")).toBeNull();
    expect(read("/ondemand/watch?id=9")).toBeNull();
    expect(read("/ondemand/watch?portal=p&id=9&start=junk")).toEqual({
      key: { portal: "p", id: "9" },
      startSec: 0,
    });
  });
});

describe("markedProgress", () => {
  it("is Watched with no Resume point after Mark watched, keeping the known length", () => {
    expect(markedProgress(progress({ positionSec: 754 }), true, 99)).toEqual({
      positionSec: null,
      durationSec: 5400,
      watched: true,
      updatedAt: 99,
    });
    expect(markedProgress(null, true, 99)).toEqual({
      positionSec: null,
      durationSec: null,
      watched: true,
      updatedAt: 99,
    });
  });

  it("is nothing at all after unmarking (07 clears the Resume point too)", () => {
    expect(markedProgress(progress({ watched: true }), false, 99)).toBeNull();
    expect(movieActions(markedProgress(progress({ watched: true }), false, 99)).primary.label).toBe(
      "▶ Play",
    );
  });
});

describe("playTitle", () => {
  it("is the Movie's name, or the Series with the Episode's code and name", () => {
    expect(playTitle("Harbor", null)).toBe("Harbor");
    expect(playTitle("Harbor", { seasonNumber: 2, number: 4, name: "The Ledger" })).toBe(
      "Harbor · S2 E4 · The Ledger",
    );
    expect(playTitle("Harbor", { seasonNumber: null, number: 3, name: null })).toBe(
      "Harbor · E3 · Episode 3",
    );
  });
});
