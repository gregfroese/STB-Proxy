import { describe, expect, it } from "vitest";
import { appendScope, getScope, parseScope, scopeKeys, watchUrl } from "./zapScope";
import type { Channel } from "./types";

function channel(id: string): Channel {
  return {
    portal: "p1",
    portalName: "Portal",
    channelId: id,
    name: `C${id}`,
    number: null,
    logo: null,
    genre: null,
    epgId: null,
    blocks: [],
    favourite: false,
    blockFavourites: [],
    url: `/play/p1/${id}`,
  };
}

function params(scope: Parameters<typeof appendScope>[1]): URLSearchParams {
  const query = new URLSearchParams();
  appendScope(query, scope);
  return query;
}

describe("scope transport", () => {
  it("a group scope rides as block= plus a label", () => {
    const query = params({ kind: "group", block: "News", label: "News" });
    expect(query.get("scope")).toBe("group");
    expect(query.get("block")).toBe("News");
    expect(query.get("label")).toBe("News");
  });

  it("a short list scope inlines its keys", () => {
    const query = params({ kind: "list", keys: ["p1:1", "p1:2"], label: "Results" });
    expect(query.get("scope")).toBe("list");
    expect(query.get("keys")).toBe("p1:1,p1:2");
    expect(query.get("token")).toBeNull();
  });

  it("a long list scope parks behind a token", () => {
    const keys = Array.from({ length: 51 }, (_, i) => `p1:${i}`);
    const query = params({ kind: "list", keys, label: "Results" });
    const token = query.get("token");
    expect(token).toBeTruthy();
    expect(query.get("keys")).toBeNull();
    expect(getScope(token)).toEqual({ kind: "list", keys, label: "Results" });
  });

  it("an absent scope parses as a group", () => {
    const scope = parseScope(new URLSearchParams("portal=p1&id=1&block=News"));
    expect(scope).toEqual({ kind: "group", block: "News", label: "News" });
  });

  it("an inline list scope round-trips", () => {
    const scope = parseScope(params({ kind: "list", keys: ["p1:1"], label: "Results" }));
    expect(scope).toEqual({ kind: "list", keys: ["p1:1"], label: "Results" });
  });

  it("a token list scope resolves from the store", () => {
    const keys = Array.from({ length: 51 }, (_, i) => `p1:${i}`);
    const scope = parseScope(params({ kind: "list", keys, label: "Results" }));
    expect(scope.kind === "list" && scope.keys).toEqual(keys);
  });

  it("an unresolvable token yields an empty list", () => {
    const scope = parseScope(new URLSearchParams("scope=list&token=nope&label=x"));
    expect(scope).toEqual({ kind: "list", keys: [], label: "x" });
  });
});

describe("scope keys and URLs", () => {
  it("scope keys are distinct and in order", () => {
    expect(scopeKeys([channel("1"), channel("2"), channel("1")])).toEqual(["p1:1", "p1:2"]);
  });

  it("watchUrl carries the channel and scope", () => {
    const url = watchUrl(channel("9"), { kind: "group", block: "News", label: "News" });
    expect(url).toContain("/watch?portal=p1&id=9");
    expect(url).toContain("block=News");
  });
});
