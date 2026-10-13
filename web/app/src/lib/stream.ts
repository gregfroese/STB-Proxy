// One entry point for playing a channel: mpegts.js over the proxied TS, with an
// automatic switch to the BFF's HLS fallback (hls.js) when the TS remux drops
// frames or fails — mpegts.js mishandles some streams (e.g. B-frame-heavy 1080p60).

import { attachPlayer, liveTsSupported, type PlayerHandle } from "./mpegts";
import { attachHls, hlsSupported, type HlsHandle } from "./hls";
import type { PlaybackError } from "./playerLogic";

export type StreamMode = "ts" | "hls";

export interface StreamHandle {
  destroy(): void;
  stats(): { speedKBps: number };
  mode(): StreamMode;
}

export function hlsUrlFor(portal: string, channelId: string): string {
  return `/hls/${encodeURIComponent(portal)}/${encodeURIComponent(channelId)}/index.m3u8`;
}

interface AttachOptions {
  tsUrl: string;
  hlsUrl: string;
  media: HTMLVideoElement;
  muted: boolean;
  onError: (error: PlaybackError) => void;
  onPlaying?: () => void;
}

export function attachStream(options: AttachOptions): StreamHandle | null {
  let mode: StreamMode = "ts";
  let ts: PlayerHandle | null = null;
  let hls: HlsHandle | null = null;
  let destroyed = false;
  let startedAt = Date.now();
  let lastFrames = 0;
  let lastDropped = 0;

  const resetMedia = () => {
    try {
      options.media.pause();
      options.media.removeAttribute("src");
      options.media.load();
    } catch {
      /* ignore */
    }
  };

  const startHls = () => {
    if (destroyed || mode === "hls") return;
    mode = "hls";
    ts?.destroy();
    ts = null;
    resetMedia();
    if (!hlsSupported()) {
      options.onError({ kind: "unreachable" });
      return;
    }
    startedAt = Date.now();
    lastFrames = 0;
    lastDropped = 0;
    hls = attachHls({
      url: options.hlsUrl,
      media: options.media,
      muted: options.muted,
      onError: options.onError,
      onPlaying: options.onPlaying,
    });
    if (hls == null) options.onError({ kind: "unreachable" });
  };

  const onTsError = (error: PlaybackError) => {
    // A busy tuner is not a remux problem: surface it rather than fall back.
    if (error.kind === "all_tuners_busy") {
      options.onError(error);
      return;
    }
    startHls();
  };

  if (liveTsSupported()) {
    ts = attachPlayer({
      url: options.tsUrl,
      media: options.media,
      muted: options.muted,
      onError: onTsError,
      onPlaying: options.onPlaying,
    });
  }
  if (ts == null) startHls();

  const watchdog = window.setInterval(() => {
    if (destroyed || mode !== "ts") return;
    const quality = options.media.getVideoPlaybackQuality?.();
    if (!quality) return;
    const deltaFrames = quality.totalVideoFrames - lastFrames;
    const deltaDropped = quality.droppedVideoFrames - lastDropped;
    lastFrames = quality.totalVideoFrames;
    lastDropped = quality.droppedVideoFrames;
    if (
      Date.now() - startedAt > 8000 &&
      quality.totalVideoFrames > 300 &&
      deltaFrames > 0 &&
      deltaDropped / deltaFrames > 0.2
    ) {
      startHls();
    }
  }, 2000);

  return {
    destroy() {
      destroyed = true;
      window.clearInterval(watchdog);
      ts?.destroy();
      hls?.destroy();
    },
    stats() {
      return ts ? ts.stats() : { speedKBps: 0 };
    },
    mode() {
      return mode;
    },
  };
}
