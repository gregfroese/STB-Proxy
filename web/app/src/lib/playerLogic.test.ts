import { describe, expect, it } from "vitest";
import type { Channel, NowNext, Programme } from "./types";
import {
  classifySourceError,
  epgRefreshAction,
  minuteBoundaryPassed,
  programmeBoundaryPassed,
  programmeProgress,
  resolveNowNext,
  zapIndex,
  zapList,
  zapTarget,
} from "./playerLogic";

const t0 = new Date("2024-01-01T12:00:00Z");
const at = (seconds: number) => new Date(t0.getTime() + seconds * 1000);

function programme(title: string, start: Date, stop: Date | null): Programme {
  return { title, start, stop, description: null };
}

describe("error classification", () => {
  it("503 is all-tuners-busy", () => {
    expect(
      classifySourceError({ isHttpResponse: true, responseCode: 503, location: null }),
    ).toEqual({ kind: "all_tuners_busy" });
  });

  it("302 is a redirect carrying its target", () => {
    expect(
      classifySourceError({
        isHttpResponse: true,
        responseCode: 302,
        location: "http://portal/stream.m3u8",
      }),
    ).toEqual({ kind: "redirect", target: "http://portal/stream.m3u8" });
  });

  it("every 3xx redirect status maps to a redirect", () => {
    for (const code of [301, 302, 303, 307, 308]) {
      expect(
        classifySourceError({ isHttpResponse: true, responseCode: code, location: null }),
      ).toEqual({ kind: "redirect", target: null });
    }
  });

  it("other http errors and plain network failures are unreachable", () => {
    for (const code of [404, 500, 200]) {
      expect(
        classifySourceError({ isHttpResponse: true, responseCode: code, location: null }),
      ).toEqual({ kind: "unreachable" });
    }
    expect(
      classifySourceError({ isHttpResponse: false, responseCode: null, location: null }),
    ).toEqual({ kind: "unreachable" });
  });
});

describe("EPG refresh decision", () => {
  it("minute boundary is crossed only when the wall-clock minute changes", () => {
    expect(minuteBoundaryPassed(at(60), t0)).toBe(true);
    expect(minuteBoundaryPassed(at(1), t0)).toBe(false);
    expect(minuteBoundaryPassed(at(30), t0)).toBe(false);
    expect(minuteBoundaryPassed(t0, t0)).toBe(false);
  });

  it("programme boundary passes at or after stop, not before, tolerating null", () => {
    const stop = at(1800);
    expect(programmeBoundaryPassed(stop, stop)).toBe(true);
    expect(programmeBoundaryPassed(at(1801), stop)).toBe(true);
    expect(programmeBoundaryPassed(at(1799), stop)).toBe(false);
    expect(programmeBoundaryPassed(t0, null)).toBe(false);
  });

  it("a programme boundary forces a refetch even mid-minute", () => {
    expect(epgRefreshAction(at(30), t0, at(30))).toBe("REFETCH");
  });

  it("a new minute recomputes, otherwise nothing", () => {
    expect(epgRefreshAction(at(61), t0, at(600))).toBe("RECOMPUTE");
    expect(epgRefreshAction(at(30), t0, at(600))).toBe("NONE");
  });
});

describe("now/next resolution", () => {
  it("a still-airing now is kept", () => {
    const stored: NowNext = {
      now: programme("A", t0, at(600)),
      next: programme("B", at(600), at(1200)),
    };
    const resolved = resolveNowNext(stored, at(300))!;
    expect(resolved.now?.title).toBe("A");
    expect(resolved.next?.title).toBe("B");
  });

  it("a null-stop now never expires", () => {
    const stored: NowNext = { now: programme("Open", t0, null), next: null };
    expect(resolveNowNext(stored, at(99999))!.now?.title).toBe("Open");
  });

  it("an ended now promotes a started next", () => {
    const stored: NowNext = {
      now: programme("A", t0, at(600)),
      next: programme("B", at(600), at(1200)),
    };
    const resolved = resolveNowNext(stored, at(700))!;
    expect(resolved.now?.title).toBe("B");
    expect(resolved.next).toBeNull();
  });

  it("an ended now with an unstarted next leaves a gap", () => {
    const stored: NowNext = {
      now: programme("A", t0, at(600)),
      next: programme("B", at(900), at(1200)),
    };
    const resolved = resolveNowNext(stored, at(700))!;
    expect(resolved.now).toBeNull();
    expect(resolved.next?.title).toBe("B");
  });

  it("no stored entry resolves to null", () => {
    expect(resolveNowNext(null, t0)).toBeNull();
  });
});

describe("progress", () => {
  it("progress is the elapsed fraction, clamped", () => {
    const p = programme("A", t0, at(600));
    expect(programmeProgress(p, at(300))).toBeCloseTo(0.5, 4);
    expect(programmeProgress(p, at(-60))).toBe(0);
    expect(programmeProgress(p, at(900))).toBe(1);
    expect(programmeProgress(programme("A", t0, null), at(300))).toBe(0);
    expect(programmeProgress(null, t0)).toBe(0);
  });
});

function channel(id: string, name: string, blocks: string[]): Channel {
  return {
    portal: "1",
    channelId: id,
    name,
    blocks,
    url: `/play/1/${id}`,
    portalName: "",
    number: null,
    logo: null,
    genre: null,
    epgId: null,
    favourite: false,
    blockFavourites: [],
  };
}

const news1 = channel("1", "BBC News", ["News"]);
const news2 = channel("2", "Sky News", ["News"]);
const news3 = channel("3", "CNN", ["News", "US"]);
const kids = channel("4", "Cartoon Network", ["Kids"]);
const channels = [news1, news2, news3, kids];

describe("channel up/down within the launch Block", () => {
  it("zap list is the launch block's channels", () => {
    expect(zapList(channels, "News")).toEqual([news1, news2, news3]);
    expect(zapList(channels, "Kids")).toEqual([kids]);
  });

  it("a multi-block channel walks the launch block", () => {
    expect(zapTarget(channels, "News", news3, 1)).toEqual(news1);
    expect(zapTarget(channels, "News", news3, -1)).toEqual(news2);
  });

  it("channel up and down wrap at both ends", () => {
    expect(zapTarget(channels, "News", news1, 1)).toEqual(news2);
    expect(zapTarget(channels, "News", news1, -1)).toEqual(news3);
  });

  it("an empty block has no zap target", () => {
    expect(zapTarget(channels, "Sports", news1, 1)).toBeNull();
    expect(zapIndex(0, 0, 1)).toBe(-1);
  });

  it("a channel outside the list steps from the first entry", () => {
    expect(zapTarget(channels, "News", kids, 1)).toEqual(news2);
  });

  it("zap index wraps in both directions", () => {
    expect(zapIndex(3, 2, 1)).toBe(0);
    expect(zapIndex(3, 0, -1)).toBe(2);
    expect(zapIndex(3, 0, 1)).toBe(1);
  });

  it("zap follows the genre group when in genre mode", () => {
    const sporty = { ...channel("9", "ESPN", []), genre: "Sports" };
    const sporty2 = { ...channel("10", "Fox Sports", []), genre: "Sports" };
    const genreChannels = [...channels, sporty, sporty2];
    expect(zapList(genreChannels, "Sports", "genres")).toEqual([sporty, sporty2]);
    expect(zapTarget(genreChannels, "Sports", sporty, 1, "genres")).toEqual(sporty2);
  });
});
