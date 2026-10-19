import { describe, expect, it } from "vitest";
import {
  airingChannels,
  filterChannels,
  hitChannels,
  nextGuideLimit,
  nowNextForChannel,
  resultCountLabel,
} from "./guideLogic";
import type { Channel, GuideHit, NowNext } from "./types";

function channel(id: string, overrides: Partial<Channel> = {}): Channel {
  return {
    portal: "p1",
    portalName: "Portal",
    channelId: id,
    name: `Channel ${id}`,
    number: id,
    logo: null,
    genre: "News",
    epgId: `epg${id}`,
    blocks: [],
    favourite: false,
    blockFavourites: [],
    url: `/play/p1/${id}`,
    ...overrides,
  };
}

function hit(id: string, title = "Show"): GuideHit {
  return {
    portal: "p1",
    channelId: id,
    channelName: `Channel ${id}`,
    channelNumber: id,
    logo: null,
    epgId: `epg${id}`,
    start: 1000,
    stop: 2000,
    title,
    desc: "",
  };
}

describe("result count label", () => {
  it("says showing first N of Y when more exist", () => {
    expect(resultCountLabel(200, 340)).toBe("Showing first 200 of 340");
  });

  it("is a plain count when everything is shown", () => {
    expect(resultCountLabel(3, 3)).toBe("3 results");
    expect(resultCountLabel(1, 1)).toBe("1 result");
  });
});

describe("load more", () => {
  it("steps toward the maximum and clamps", () => {
    expect(nextGuideLimit(200)).toBe(400);
    expect(nextGuideLimit(400)).toBe(500);
    expect(nextGuideLimit(500)).toBe(500);
  });
});

describe("hit channels", () => {
  it("maps hits to distinct lineup channels in first-seen order", () => {
    const channels = [channel("1"), channel("2"), channel("3")];
    const hits = [hit("2"), hit("1"), hit("2")];
    expect(hitChannels(hits, channels).map((c) => c.channelId)).toEqual(["2", "1"]);
  });

  it("drops hits whose channel is not in the lineup", () => {
    expect(hitChannels([hit("9")], [channel("1")])).toEqual([]);
  });
});

describe("airing channels", () => {
  const now = 1500;
  const epg: Record<string, NowNext> = {
    epg1: {
      now: { title: "Now", start: new Date(1000), stop: new Date(2000), description: null },
      next: null,
    },
    epg2: {
      now: { title: "Later", start: new Date(3000), stop: new Date(4000), description: null },
      next: null,
    },
  };

  it("keeps only channels whose current programme is airing", () => {
    const channels = [channel("1"), channel("2")];
    expect(airingChannels(channels, epg, now).map((c) => c.channelId)).toEqual(["1"]);
  });

  it("a channel with no epg is not airing", () => {
    expect(airingChannels([channel("9")], epg, now)).toEqual([]);
  });
});

describe("sub-filter", () => {
  it("matches name or number, case-insensitively", () => {
    const channels = [channel("1", { name: "BBC News" }), channel("2", { name: "ITV" })];
    expect(filterChannels(channels, "bbc").map((c) => c.channelId)).toEqual(["1"]);
    expect(filterChannels(channels, "2").map((c) => c.channelId)).toEqual(["2"]);
    expect(filterChannels(channels, "")).toHaveLength(2);
  });
});

describe("now/next for a channel", () => {
  it("resolves by epgId and tolerates a missing one", () => {
    const epg: Record<string, NowNext> = { epg1: { now: null, next: null } };
    expect(nowNextForChannel(channel("1"), epg)).not.toBeNull();
    expect(nowNextForChannel(channel("1", { epgId: null }), epg)).toBeNull();
    expect(nowNextForChannel(channel("9"), epg)).toBeNull();
  });
});
