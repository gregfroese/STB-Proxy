import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import type { OnDemandItem, OnDemandPage, OnDemandPortal, OnDemandUpNext } from "./types";
import {
  ON_DEMAND_OFF_NOTICE,
  SEARCH_DEBOUNCE_MS,
  isOnDemandOff,
  onDemandShown,
  activeSort,
  allShelves,
  browseFromQuery,
  browsePath,
  titlePath,
  titleBack,
  backLabel,
  appendPage,
  browseView,
  formatTime,
  continueLine,
  debounce,
  posterBadges,
  emptyText,
  searchHint,
  initialPaging,
  itemsPath,
  nextOffset,
  searchTerm,
  gridFooter,
  statusPills,
} from "./onDemandLogic";

const DAY = 86400;
const NOW = 1_800_000_000;

function portal(
  name: string,
  status: OnDemandPortal["status"],
  extra: Partial<OnDemandPortal> = {},
): OnDemandPortal {
  return { portal: name.toLowerCase(), name, status, progress: null, lastRefresh: null, ...extra };
}

describe("statusPills", () => {
  it("shows nothing when every portal is ready", () => {
    expect(statusPills([portal("Alpha", "ready"), portal("Beta", "ready")], NOW)).toEqual([]);
  });

  it("words each status that isn't ready as decided in 09", () => {
    const pills = statusPills(
      [
        portal("Alpha", "indexing", { progress: 42 }),
        portal("Beta", "ready"),
        portal("Gamma", "stale", { lastRefresh: NOW - 3 * DAY - 100 }),
        portal("Delta", "partial"),
        portal("Echo", "failed"),
      ],
      NOW,
    );
    expect(pills).toEqual([
      { portal: "alpha", status: "indexing", text: "Alpha: Still indexing (42%) — newest first" },
      { portal: "gamma", status: "stale", text: "Gamma: Not refreshed for 3 days" },
      { portal: "delta", status: "partial", text: "Delta: Partly indexed" },
      { portal: "echo", status: "failed", text: "Echo: Couldn't load — showing nothing from it" },
    ]);
  });

  it("says 1 day, and never less, for a portal gone stale recently", () => {
    const [pill] = statusPills([portal("Alpha", "stale", { lastRefresh: NOW - 3600 })], NOW);
    expect(pill.text).toBe("Alpha: Not refreshed for 1 day");
  });

  it("leaves the percentage out when indexing hasn't counted pages yet", () => {
    const [pill] = statusPills([portal("Alpha", "indexing")], NOW);
    expect(pill.text).toBe("Alpha: Still indexing — newest first");
  });
});

describe("searchTerm", () => {
  it("is null below 2 characters, ignoring surrounding spaces", () => {
    expect(searchTerm("")).toBeNull();
    expect(searchTerm("a")).toBeNull();
    expect(searchTerm("  a  ")).toBeNull();
  });

  it("is the trimmed text from 2 characters on", () => {
    expect(searchTerm(" ab ")).toBe("ab");
    expect(searchTerm("the matrix")).toBe("the matrix");
  });
});

describe("itemsPath", () => {
  it("asks for a category's page, Recently added by default", () => {
    expect(itemsPath({ category: "action", q: "", sort: null }, 0)).toBe(
      "/api/ondemand/items?category=action&offset=0&limit=60",
    );
  });

  it("searches the selected category, best match first, from 2 characters", () => {
    expect(itemsPath({ category: "action", q: " ma ", sort: null }, 60)).toBe(
      "/api/ondemand/items?category=action&q=ma&offset=60&limit=60",
    );
    expect(itemsPath({ category: "", q: "m", sort: null }, 0)).toBe(
      "/api/ondemand/items?offset=0&limit=60",
    );
  });

  it("keeps a sort the viewer chose, also while searching", () => {
    expect(itemsPath({ category: "", q: "ma", sort: "year" }, 0, 20)).toBe(
      "/api/ondemand/items?q=ma&sort=year&offset=0&limit=20",
    );
  });
});

function item(id: string, extra: Partial<OnDemandItem> = {}): OnDemandItem {
  return {
    portal: "p1",
    portalName: "Alpha",
    id,
    kind: "movie",
    name: `Title ${id}`,
    year: 2020,
    rating: 7.1,
    added: "2026-10-01 10:00:00",
    poster: null,
    progress: null,
    ...extra,
  };
}

function page(offset: number, count: number, total: number): OnDemandPage {
  const items = Array.from({ length: count }, (_, n) => item(String(offset + n)));
  return { items, total, offset, limit: 60 };
}

describe("paging", () => {
  it("starts at offset 0 with a plain loading line", () => {
    const paging = initialPaging();
    expect(nextOffset(paging)).toBe(0);
    expect(gridFooter(paging, "No titles here.")).toEqual({ text: "Loading…", end: false });
  });

  it("asks for the next 60 until the total is loaded, counting as it goes", () => {
    let paging = appendPage(initialPaging(), page(0, 60, 130));
    expect(nextOffset(paging)).toBe(60);
    expect(gridFooter(paging, "")).toEqual({ text: "Loading more… (60 of 130)", end: false });
    paging = appendPage(paging, page(60, 60, 130));
    paging = appendPage(paging, page(120, 10, 130));
    expect(paging.items).toHaveLength(130);
    expect(nextOffset(paging)).toBeNull();
    expect(gridFooter(paging, "")).toEqual({ text: "130 titles", end: true });
  });

  it("says 1 title, and shows the empty text when nothing matches", () => {
    expect(gridFooter(appendPage(initialPaging(), page(0, 1, 1)), "")).toEqual({
      text: "1 title",
      end: true,
    });
    expect(gridFooter(appendPage(initialPaging(), page(0, 0, 0)), "Nothing.")).toEqual({
      text: "Nothing.",
      end: true,
    });
  });

  it("ignores a page that doesn't follow on from what's loaded", () => {
    const paging = appendPage(initialPaging(), page(0, 60, 130));
    expect(appendPage(paging, page(0, 60, 130))).toBe(paging);
    expect(appendPage(paging, page(120, 10, 130))).toBe(paging);
  });

  it("stops when the catalogue shrank under it and a page comes back empty", () => {
    let paging = appendPage(initialPaging(), page(0, 60, 130));
    paging = appendPage(paging, page(60, 0, 130));
    expect(nextOffset(paging)).toBeNull();
    expect(gridFooter(paging, "")).toEqual({ text: "60 titles", end: true });
  });
});

describe("browseView", () => {
  it("shows shelves on All, and the grid for a category", () => {
    expect(browseView({ category: "", q: "", sort: null, allGrid: false })).toBe("shelves");
    expect(browseView({ category: "action", q: "", sort: null, allGrid: false })).toBe("grid");
  });

  it("shows search results in the grid, but not before 2 characters", () => {
    expect(browseView({ category: "", q: "ma", sort: null, allGrid: false })).toBe("grid");
    expect(browseView({ category: "", q: "m", sort: null, allGrid: false })).toBe("shelves");
  });

  it("shows All as a grid once asked to (See all on Recently added)", () => {
    expect(browseView({ category: "", q: "", sort: null, allGrid: true })).toBe("grid");
  });
});

describe("search wording", () => {
  it("hints best match first and where it searches", () => {
    expect(searchHint("Action", null)).toBe("Best match first · in Action");
    expect(searchHint(null, null)).toBe("Best match first · all categories");
    expect(searchHint("Action", "year")).toBe("in Action");
  });

  it("names the search and the category when nothing matches", () => {
    expect(emptyText(" zzz ", "Action")).toBe("No titles match “zzz” in Action");
    expect(emptyText("zzz", null)).toBe("No titles match “zzz”");
    expect(emptyText("", "Action")).toBe("No titles here.");
  });

  it("lights the chosen sort chip, Recently added when browsing, none for best match", () => {
    expect(activeSort(null, false)).toBe("added");
    expect(activeSort(null, true)).toBeNull();
    expect(activeSort("name", true)).toBe("name");
  });
});

describe("allShelves", () => {
  const categories = [
    { id: "action", name: "Action", count: 120 },
    { id: "kids", name: "Kids", count: 8 },
  ];

  it("puts Continue watching first, then Recently added, then a shelf per category", () => {
    expect(allShelves([item("1")], categories)).toEqual([
      { key: "continue", title: "Continue watching", kind: "continue" },
      {
        key: "recent",
        title: "Recently added",
        kind: "recent",
        path: "/api/ondemand/items?offset=0&limit=20",
      },
      {
        key: "category:action",
        title: "Action",
        kind: "category",
        category: "action",
        count: 120,
        path: "/api/ondemand/items?category=action&offset=0&limit=20",
      },
      {
        key: "category:kids",
        title: "Kids",
        kind: "category",
        category: "kids",
        count: 8,
        path: "/api/ondemand/items?category=kids&offset=0&limit=20",
      },
    ]);
  });

  it("hides Continue watching when it's empty", () => {
    expect(allShelves([], categories).map((shelf) => shelf.key)).toEqual([
      "recent",
      "category:action",
      "category:kids",
    ]);
  });
});

function progress(positionSec: number | null, durationSec: number | null, watched = false) {
  return { positionSec, durationSec, watched, updatedAt: NOW };
}

function upNext(extra: Partial<OnDemandUpNext> = {}): OnDemandUpNext {
  return {
    seasonId: "s2",
    seasonNumber: 2,
    episodeId: "e4",
    episodeNumber: 4,
    name: "The Return",
    positionSec: null,
    durationSec: null,
    ...extra,
  };
}

describe("posterBadges", () => {
  it("shows nothing for a Movie never played", () => {
    expect(posterBadges(item("1"))).toEqual({ series: false, watched: false, progress: null });
  });

  it("tags a Series, with its Up next's progress", () => {
    const series = item("1", { kind: "series", progress: undefined, upNext: null });
    expect(posterBadges(series)).toEqual({ series: true, watched: false, progress: null });
    const resumed = { ...series, upNext: upNext({ positionSec: 600, durationSec: 2400 }) };
    expect(posterBadges(resumed).progress).toBe(0.25);
  });

  it("ticks a Watched Movie and shows no bar for it", () => {
    expect(posterBadges(item("1", { progress: progress(5000, 5400, true) }))).toEqual({
      series: false,
      watched: true,
      progress: null,
    });
  });

  it("draws the bar for a Resume point when the duration is known", () => {
    expect(posterBadges(item("1", { progress: progress(1800, 5400) })).progress).toBeCloseTo(1 / 3);
    expect(posterBadges(item("1", { progress: progress(1800, null) })).progress).toBeNull();
  });
});

describe("continueLine", () => {
  it("gives a Movie's time left", () => {
    expect(continueLine(item("1", { progress: progress(600, 5400) }))).toBe("80 min left");
  });

  it("gives a Movie's position when its length is unknown", () => {
    expect(continueLine(item("1", { progress: progress(754, null) }))).toBe("12:34 in");
  });

  it("names a Series' Up next Episode", () => {
    const series = item("1", { kind: "series", upNext: upNext() });
    expect(continueLine(series)).toBe("S2 · E4 · The Return · Up next");
    const started = {
      ...series,
      upNext: upNext({ name: null, positionSec: 600, durationSec: 2400 }),
    };
    expect(continueLine(started)).toBe("S2 · E4 · 30 min left");
  });
});

describe("formatTime", () => {
  it("is m:ss under an hour and h:mm:ss from an hour", () => {
    expect(formatTime(0)).toBe("0:00");
    expect(formatTime(754.9)).toBe("12:34");
    expect(formatTime(3723)).toBe("1:02:03");
  });
});

describe("On Demand switched off", () => {
  it("is a 404 on_demand_off, not any other 404 or failure", () => {
    expect(isOnDemandOff(new ApiError(404, "on_demand_off", "off"))).toBe(true);
    expect(isOnDemandOff(new ApiError(404, "not_found", "gone"))).toBe(false);
    expect(isOnDemandOff(new ApiError(502, "proxy_error", "down"))).toBe(false);
    expect(isOnDemandOff(new Error("network"))).toBe(false);
  });

  it("shows the nav button only when the lineup allows it and no call has said it's off", () => {
    expect(onDemandShown({ onDemand: true }, false)).toBe(true);
    expect(onDemandShown({ onDemand: true }, true)).toBe(false);
    expect(onDemandShown({ onDemand: false }, false)).toBe(false);
    expect(onDemandShown({}, false)).toBe(false);
    expect(onDemandShown(null, false)).toBe(false);
  });

  it("has 09's notice for the Channels screen", () => {
    expect(ON_DEMAND_OFF_NOTICE).toBe("On Demand isn't available on this login any more.");
  });
});

describe("browse URL", () => {
  it("is bare /ondemand for the All shelves", () => {
    expect(browsePath({ category: "", q: "", sort: null, allGrid: false })).toBe("/ondemand");
    expect(browseFromQuery(new URLSearchParams(""))).toEqual({
      category: "",
      q: "",
      sort: null,
      allGrid: false,
    });
  });

  it("carries the category, search, chosen sort and All grid", () => {
    const browse = { category: "action", q: "ma", sort: "year" as const, allGrid: false };
    expect(browsePath(browse)).toBe("/ondemand?category=action&q=ma&sort=year");
    expect(browseFromQuery(new URLSearchParams("category=action&q=ma&sort=year"))).toEqual(browse);
    expect(browsePath({ category: "", q: "", sort: "name", allGrid: true })).toBe(
      "/ondemand?sort=name&all=1",
    );
  });

  it("drops a sort it doesn't know", () => {
    expect(browseFromQuery(new URLSearchParams("sort=bogus")).sort).toBeNull();
  });

  it("links a title's page by its portal and id", () => {
    expect(titlePath(item("12 b", { portal: "p/1" }))).toBe("/ondemand/title?portal=p%2F1&id=12+b");
  });

  it("carries where the title was opened from, for its Back button", () => {
    const path = titlePath(item("12"), "Action & Adventure");
    expect(path).toBe("/ondemand/title?portal=p1&id=12&from=Action+%26+Adventure");
    expect(titleBack(new URL(path, "http://x").searchParams)).toBe("‹ Back to Action & Adventure");
    expect(titleBack(new URLSearchParams("portal=p1&id=12"))).toBe("‹ Back");
  });
});

describe("backLabel", () => {
  it("names the category, results while searching, or On Demand on All", () => {
    const browse = { category: "action", q: "", sort: null, allGrid: false };
    expect(backLabel(browse, "Action")).toBe("Action");
    expect(backLabel({ ...browse, q: "ma" }, "Action")).toBe("results");
    expect(backLabel({ ...browse, category: "" }, null)).toBe("On Demand");
    expect(backLabel({ ...browse, category: "", allGrid: true }, null)).toBe("On Demand");
  });
});

describe("debounce", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("runs once with the last value after typing pauses", () => {
    const seen: string[] = [];
    const typed = debounce((value: string) => seen.push(value), SEARCH_DEBOUNCE_MS);
    typed("ma");
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
    typed("mat");
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
    expect(seen).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(seen).toEqual(["mat"]);
  });

  it("drops a pending call when cancelled", () => {
    const seen: string[] = [];
    const typed = debounce((value: string) => seen.push(value), SEARCH_DEBOUNCE_MS);
    typed("ma");
    typed.cancel();
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS * 2);
    expect(seen).toEqual([]);
  });
});
