import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import {
  briefsByItem,
  canCancel,
  downloadButton,
  downloadErrorText,
  episodeDownloadText,
  isActive,
  itemKey,
} from "./onDemandDownloadLogic";
import type { OnDemandDownload, OnDemandDownloadBrief } from "./types";

function brief(extra: Partial<OnDemandDownloadBrief> = {}): OnDemandDownloadBrief {
  return { id: "d1", status: "queued", progress: 0, error: null, mine: true, ...extra };
}

describe("downloadButton", () => {
  it("offers Download when nobody asked for it", () => {
    expect(downloadButton(null)).toMatchObject({ label: "Download", canStart: true });
  });

  it("says where a download is, and only a failed one can be asked for again", () => {
    expect(downloadButton(brief())).toMatchObject({ label: "Queued", canStart: false });
    expect(downloadButton(brief({ progress: 42 }))).toMatchObject({
      label: "Paused at 42%",
      canStart: false,
    });
    expect(downloadButton(brief({ status: "downloading", progress: 7 }))).toMatchObject({
      label: "Downloading 7%",
      canStart: false,
    });
    expect(downloadButton(brief({ status: "done", progress: 100 }))).toMatchObject({
      label: "Downloaded",
      canStart: false,
    });
    expect(
      downloadButton(brief({ status: "failed", error: "The portal won't play that" })),
    ).toEqual({
      label: "Download failed – try again",
      canStart: true,
      hint: "The portal won't play that",
    });
  });
});

describe("episodeDownloadText", () => {
  it("is short, and empty when there's no download", () => {
    expect(episodeDownloadText(undefined)).toBeNull();
    expect(episodeDownloadText(brief({ status: "failed" }))).toBe("Download failed");
    expect(episodeDownloadText(brief({ status: "done" }))).toBe("Downloaded");
  });
});

describe("canCancel and isActive", () => {
  it("lets the viewer cancel only their own unfinished download", () => {
    expect(canCancel(brief())).toBe(true);
    expect(canCancel(brief({ status: "failed" }))).toBe(true);
    expect(canCancel(brief({ mine: false }))).toBe(false);
    expect(canCancel(brief({ status: "done" }))).toBe(false);
    expect(canCancel(null)).toBe(false);
  });

  it("keeps looking while queued or downloading", () => {
    expect(isActive(brief())).toBe(true);
    expect(isActive(brief({ status: "downloading" }))).toBe(true);
    expect(isActive(brief({ status: "done" }))).toBe(false);
    expect(isActive(brief({ status: "failed" }))).toBe(false);
    expect(isActive(null)).toBe(false);
  });
});

describe("briefsByItem", () => {
  it("matches Movies and Episodes by their keys", () => {
    const movie = { portal: "p1", id: "5" };
    const episode = { portal: "p1", seriesId: "77", seasonId: "3", episodeId: "9" };
    const downloads: OnDemandDownload[] = [
      {
        ...brief({ id: "a" }),
        kind: "movie",
        item: movie,
        title: "Heat",
        poster: "",
        sizeBytes: null,
        mine: true,
        createdAt: 1,
        finishedAt: null,
      },
      {
        ...brief({ id: "b", status: "done", progress: 100 }),
        kind: "episode",
        item: episode,
        title: "Show",
        poster: "",
        sizeBytes: 9,
        mine: false,
        createdAt: 2,
        finishedAt: 3,
      },
    ];
    const map = briefsByItem(downloads);
    expect(map.get(itemKey(movie))).toEqual({
      id: "a",
      status: "queued",
      progress: 0,
      error: null,
      mine: true,
    });
    expect(map.get(itemKey(episode))?.status).toBe("done");
    expect(map.get(itemKey({ portal: "p1", id: "77" }))).toBeUndefined();
  });
});

describe("downloadErrorText", () => {
  it("shows the server's words", () => {
    expect(
      downloadErrorText(
        new ApiError(503, "downloads_unavailable", "Downloads aren't set up on this server"),
      ),
    ).toBe("Downloads aren't set up on this server");
    expect(downloadErrorText(new Error("x"))).toBe("Couldn't ask for the download. Try again.");
  });
});
