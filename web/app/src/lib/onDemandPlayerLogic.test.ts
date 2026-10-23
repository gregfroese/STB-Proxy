import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import {
  autoplaysAfter,
  controlsShown,
  createProgressReporter,
  doneTitle,
  endCardDue,
  endCardFor,
  nextAspect,
  nextCardText,
  nextEpisode,
  overlayCopy,
  playFailure,
  playerHeading,
  playerKey,
  seasonAfter,
  streamFailure,
  secondsLeft,
  seekStep,
  type KeyContext,
  type ProgressSample,
} from "./onDemandPlayerLogic";

describe("seekStep (TV D-pad hold acceleration)", () => {
  it("steps 10 s for the first second of a hold", () => {
    expect(seekStep(0)).toBe(10);
    expect(seekStep(999)).toBe(10);
  });

  it("steps 30 s after 1 s and 60 s after 3 s", () => {
    expect(seekStep(1000)).toBe(30);
    expect(seekStep(2999)).toBe(30);
    expect(seekStep(3000)).toBe(60);
    expect(seekStep(20000)).toBe(60);
  });
});

const desktop: KeyContext = {
  tv: false,
  controlsVisible: true,
  onBar: false,
  card: null,
  heldMs: 0,
};
const tvHidden: KeyContext = { ...desktop, tv: true, controlsVisible: false };
const press = (key: string, shiftKey = false) => ({ key, shiftKey });

describe("playerKey on the web (keyboard)", () => {
  it("toggles play with Space and K", () => {
    expect(playerKey(press(" "), desktop)).toEqual({ type: "toggle" });
    expect(playerKey(press("k"), desktop)).toEqual({ type: "toggle" });
    expect(playerKey(press("K"), desktop)).toEqual({ type: "toggle" });
  });

  it("seeks 10 s with the arrows and 60 s with Shift, whether or not the controls show", () => {
    expect(playerKey(press("ArrowLeft"), desktop)).toEqual({ type: "seek", by: -10 });
    expect(playerKey(press("ArrowRight"), { ...desktop, controlsVisible: false })).toEqual({
      type: "seek",
      by: 10,
    });
    expect(playerKey(press("ArrowLeft", true), desktop)).toEqual({ type: "seek", by: -60 });
    expect(playerKey(press("ArrowRight", true), desktop)).toEqual({ type: "seek", by: 60 });
  });

  it("maps F, M, N and Esc", () => {
    expect(playerKey(press("f"), desktop)).toEqual({ type: "fullscreen" });
    expect(playerKey(press("m"), desktop)).toEqual({ type: "mute" });
    expect(playerKey(press("N"), desktop)).toEqual({ type: "next" });
    expect(playerKey(press("Escape"), desktop)).toEqual({ type: "escape" });
  });

  it("leaves other keys alone", () => {
    expect(playerKey(press("x"), desktop)).toBeNull();
    expect(playerKey(press("ArrowUp"), desktop)).toBeNull();
  });

  it("lets a session overlay or Still watching? keep its buttons' keys", () => {
    const modal = { ...desktop, card: "modal" as const };
    expect(playerKey(press(" "), modal)).toBeNull();
    expect(playerKey(press("ArrowLeft"), modal)).toBeNull();
    expect(playerKey(press("Escape"), modal)).toEqual({ type: "escape" });
  });

  it("seeks back out of the end card with ←, but not forward", () => {
    const end = { ...desktop, card: "end" as const };
    expect(playerKey(press("ArrowLeft"), end)).toEqual({ type: "seek", by: -10 });
    expect(playerKey(press("ArrowRight"), end)).toBeNull();
    expect(playerKey(press(" "), end)).toBeNull();
  });
});

describe("playerKey in TV mode (D-pad)", () => {
  it("seeks with ← → while the controls are hidden, accelerating with the hold", () => {
    expect(playerKey(press("ArrowRight"), tvHidden)).toEqual({ type: "seek", by: 10 });
    expect(playerKey(press("ArrowLeft"), { ...tvHidden, heldMs: 1500 })).toEqual({
      type: "seek",
      by: -30,
    });
    expect(playerKey(press("ArrowRight"), { ...tvHidden, heldMs: 4000 })).toEqual({
      type: "seek",
      by: 60,
    });
  });

  it("seeks on the focused seek bar, and leaves ← → to focus on the buttons", () => {
    const shown = { ...tvHidden, controlsVisible: true };
    expect(playerKey(press("ArrowLeft"), { ...shown, onBar: true })).toEqual({
      type: "seek",
      by: -10,
    });
    expect(playerKey(press("ArrowLeft"), shown)).toBeNull();
  });

  it("pauses with OK while the controls are hidden, else OK presses the focused button", () => {
    expect(playerKey(press("Enter"), tvHidden)).toEqual({ type: "toggle" });
    expect(playerKey(press("Enter"), { ...tvHidden, controlsVisible: true })).toBeNull();
  });

  it("brings the controls up with ↑ ↓ (no channel zap)", () => {
    expect(playerKey(press("ArrowUp"), tvHidden)).toEqual({ type: "showControls" });
    expect(playerKey(press("ArrowDown"), tvHidden)).toEqual({ type: "showControls" });
    expect(playerKey(press("ArrowDown"), { ...tvHidden, controlsVisible: true })).toBeNull();
  });

  it("treats Back keys as Back and the media key as play/pause", () => {
    expect(playerKey(press("Escape"), tvHidden)).toEqual({ type: "back" });
    expect(playerKey(press("Backspace"), tvHidden)).toEqual({ type: "back" });
    expect(playerKey(press("GoBack"), tvHidden)).toEqual({ type: "back" });
    expect(playerKey(press("MediaPlayPause"), { ...tvHidden, controlsVisible: true })).toEqual({
      type: "toggle",
    });
  });

  it("seeks back out of the end card with ← from its first button", () => {
    const end = { ...tvHidden, card: "end" as const };
    expect(playerKey(press("ArrowLeft"), end)).toEqual({ type: "seek", by: -10 });
    expect(playerKey(press("Enter"), end)).toBeNull();
    expect(playerKey(press("ArrowUp"), end)).toBeNull();
  });
});

describe("the end card", () => {
  it("offers the next Episode with a 15 s countdown, then autoplays it", () => {
    const card = endCardFor({ hasNext: true, autoplays: 0, now: 1000 });
    expect(card.kind).toBe("next");
    expect(secondsLeft(card, 1000)).toBe(15);
    expect(secondsLeft(card, 1500)).toBe(15);
    expect(secondsLeft(card, 15000)).toBe(1);
    expect(endCardDue(card, 15999)).toBeNull();
    expect(endCardDue(card, 16000)).toBe("autoplay");
  });

  it("shows ✓ Watched after a Movie or the last Episode and goes back after 15 s", () => {
    const card = endCardFor({ hasNext: false, autoplays: 0, now: 0 });
    expect(card.kind).toBe("done");
    expect(endCardDue(card, 14999)).toBeNull();
    expect(endCardDue(card, 15000)).toBe("back");
  });

  it("asks Still watching? after 3 autoplays in a row, and waits for an answer", () => {
    let autoplays = 0;
    for (let episode = 0; episode < 3; episode += 1) {
      const card = endCardFor({ hasNext: true, autoplays, now: 0 });
      expect(card.kind).toBe("next");
      expect(endCardDue(card, 15000)).toBe("autoplay");
      autoplays = autoplaysAfter(autoplays, "autoplay");
    }
    const still = endCardFor({ hasNext: true, autoplays, now: 0 });
    expect(still.kind).toBe("still");
    expect(endCardDue(still, 10_000_000)).toBeNull();
  });

  it("restarts the autoplay count on any input or a hand-picked Next Episode", () => {
    expect(autoplaysAfter(2, "input")).toBe(0);
    expect(autoplaysAfter(3, "manual")).toBe(0);
    expect(autoplaysAfter(1, "autoplay")).toBe(2);
    expect(endCardFor({ hasNext: true, autoplays: autoplaysAfter(2, "input"), now: 0 }).kind).toBe(
      "next",
    );
  });

  it("never asks Still watching? when there is no next Episode", () => {
    expect(endCardFor({ hasNext: false, autoplays: 5, now: 0 }).kind).toBe("done");
  });
});

describe("a session that ends under the player (410)", () => {
  const ended = (reason: string) => ({ error: "Session ended", code: "session_ended", reason });

  it("restarts an idle session silently", () => {
    expect(streamFailure(410, ended("idle"))).toEqual({ kind: "restart" });
  });

  it("shows the Resume overlay when evicted, failed or stopped", () => {
    expect(streamFailure(410, ended("evicted"))).toEqual({ kind: "overlay", overlay: "evicted" });
    expect(streamFailure(410, ended("failed"))).toEqual({ kind: "overlay", overlay: "failed" });
    expect(streamFailure(410, ended("stopped"))).toEqual({ kind: "overlay", overlay: "stopped" });
  });

  it("treats an unknown end or a lost session as stopped, and other failures as an error", () => {
    expect(streamFailure(410, { code: "session_ended" })).toEqual({
      kind: "overlay",
      overlay: "stopped",
    });
    expect(streamFailure(404, { code: "not_found" })).toEqual({
      kind: "overlay",
      overlay: "error",
    });
    expect(streamFailure(null, null)).toEqual({ kind: "overlay", overlay: "error" });
  });

  it("hands on_demand_off back to the switched-off flow", () => {
    expect(streamFailure(404, { error: "x", code: "on_demand_off" })).toEqual({ kind: "off" });
  });

  it("shows the busy toast and overlay when the idle restart gets 503", () => {
    const busy = new ApiError(503, "busy", "All tuners are busy");
    expect(playFailure(busy, true)).toEqual({
      toast: "Couldn't restart — someone else on this login is watching.",
      overlay: "busy",
    });
    expect(playFailure(busy, false)).toEqual({ toast: null, overlay: "busy" });
    expect(playFailure(new ApiError(502, "portal_error", "x"), true)).toEqual({
      toast: null,
      overlay: "error",
    });
  });

  it("words the overlays as 09 does, with Resume from the position", () => {
    expect(overlayCopy("evicted", 754, null)).toEqual({
      title: "Playback stopped",
      body: "Playback stopped — someone started watching on another device with this login, and the portal only allows one stream at a time.",
      primary: "▶ Resume from 12:34",
    });
    expect(overlayCopy("stopped", 60, null).body).toBe(
      "The stream was stopped from the server's Streams page.",
    );
    expect(overlayCopy("busy", 60, null)).toEqual({
      title: "Couldn't continue",
      body: "Someone else on this login is already watching — On Demand uses the same stream as live TV. Stop the other stream and try again.",
      primary: "Try again",
    });
    expect(overlayCopy("failed", 754, null)).toEqual({
      title: "Playback interrupted",
      body: "Playback was interrupted — the stream stopped coming through.",
      primary: "▶ Resume from 12:34",
    });
    expect(overlayCopy("error", 0, "The portal didn't answer.")).toEqual({
      title: "Playback stopped",
      body: "The portal didn't answer.",
      primary: "Try again",
    });
  });
});

describe("controls", () => {
  const idle = { playing: true, busy: false, dragging: false, sinceInputMs: 0 };

  it("fade 4 s after the last input while playing", () => {
    expect(controlsShown({ ...idle, sinceInputMs: 3999 })).toBe(true);
    expect(controlsShown({ ...idle, sinceInputMs: 4000 })).toBe(false);
  });

  it("stay up while paused, loading or dragging", () => {
    const late = { ...idle, sinceInputMs: 60000 };
    expect(controlsShown({ ...late, playing: false })).toBe(true);
    expect(controlsShown({ ...late, busy: true })).toBe(true);
    expect(controlsShown({ ...late, dragging: true })).toBe(true);
  });

  it("cycle Aspect through Auto, 16:9, 4:3 and Zoom", () => {
    expect(nextAspect("auto")).toBe("16:9");
    expect(nextAspect("16:9")).toBe("4:3");
    expect(nextAspect("4:3")).toBe("zoom");
    expect(nextAspect("zoom")).toBe("auto");
  });
});

describe("the next Episode and the titles", () => {
  const episode = (id: string, number: number, name: string | null = null, durationSec = 0) => ({
    id,
    seasonId: "s2",
    number,
    name,
    progress: durationSec ? { positionSec: null, durationSec, watched: false, updatedAt: 0 } : null,
  });
  const seasons = [
    { id: "s1", number: 1, name: null, episodeCount: 8 },
    { id: "s2", number: 2, name: null, episodeCount: 3 },
  ];

  it("is the next one in the Season, or none after its last", () => {
    const list = [episode("a", 1), episode("b", 2), episode("c", 3)];
    expect(nextEpisode(list, "a")?.id).toBe("b");
    expect(nextEpisode(list, "c")).toBeNull();
    expect(nextEpisode(list, "zz")).toBeNull();
  });

  it("goes on to the next Season's first Episode", () => {
    expect(seasonAfter(seasons, "s1")?.id).toBe("s2");
    expect(seasonAfter(seasons, "s2")).toBeNull();
  });

  const movie = {
    portal: "p",
    portalName: "P",
    id: "m1",
    kind: "movie" as const,
    name: "The Long Voyage",
    year: 2019,
    rating: null,
    added: null,
    poster: null,
    description: "A family drifts.",
    genres: null,
    director: null,
    actors: null,
    country: null,
    durationMin: 112,
    ageRating: null,
    categories: [],
  };
  const series = { ...movie, id: "sr", kind: "series" as const, name: "Harbour Lights", seasons };

  it("heads a Movie with its year and length, an Episode with S · E · name", () => {
    expect(playerHeading(movie, null, null)).toEqual({
      title: "The Long Voyage",
      sub: "2019 · 112 min",
    });
    expect(playerHeading(series, episode("b", 4, "The Pier"), seasons[1])).toEqual({
      title: "Harbour Lights",
      sub: "S2 · E4 · The Pier",
    });
    expect(playerHeading(series, episode("b", 5), seasons[1]).sub).toBe("S2 · E5 · Episode 5");
  });

  it("words the end card", () => {
    expect(nextCardText(episode("c", 5, "Low Tide", 2640), seasons[1])).toEqual({
      name: "S2 E5 · Low Tide",
      facts: "44 min · Season 2",
    });
    expect(nextCardText(episode("c", 5), seasons[1]).facts).toBe("Season 2");
    expect(nextCardText(episode("c", 5, null, 12), seasons[1]).facts).toBe("Season 2");
    expect(doneTitle(movie, null)).toBe("The Long Voyage");
    expect(doneTitle(series, seasons[1])).toBe("Harbour Lights · Season 2 finished");
  });
});

describe("progress reports", () => {
  function reporter(sample: ProgressSample | null = { positionSec: 100, durationSec: 3000 }) {
    const sent: { sample: ProgressSample; keepalive: boolean }[] = [];
    const current = { sample };
    const progress = createProgressReporter({
      sample: () => current.sample,
      send: (s, keepalive) => sent.push({ sample: s, keepalive }),
    });
    return { progress, sent, current };
  }

  it("reports every 30 s of playback", () => {
    const { progress, sent } = reporter();
    for (let second = 0; second < 29; second += 1) progress.played(1);
    expect(sent).toHaveLength(0);
    progress.played(1);
    expect(sent).toEqual([{ sample: { positionSec: 100, durationSec: 3000 }, keepalive: false }]);
    progress.played(29.5);
    expect(sent).toHaveLength(1);
    progress.played(0.5);
    expect(sent).toHaveLength(2);
  });

  it("reports at once on pause, Back, end and hand-over, and restarts the 30 s", () => {
    const { progress, sent } = reporter();
    progress.played(20);
    progress.now();
    expect(sent).toHaveLength(1);
    progress.played(20);
    expect(sent).toHaveLength(1);
    progress.played(10);
    expect(sent).toHaveLength(2);
  });

  it("sends with keepalive when the page is being hidden or left", () => {
    const { progress, sent } = reporter();
    progress.now(true);
    expect(sent[0].keepalive).toBe(true);
  });

  it("sends nothing before playback has reached its start position", () => {
    const { progress, sent, current } = reporter(null);
    progress.played(45);
    progress.now();
    expect(sent).toHaveLength(0);
    current.sample = { positionSec: 1200, durationSec: null };
    progress.played(1);
    expect(sent).toEqual([{ sample: { positionSec: 1200, durationSec: null }, keepalive: false }]);
  });
});
