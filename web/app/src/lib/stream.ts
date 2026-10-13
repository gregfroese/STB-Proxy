// One entry point for playing a channel, with a fallback ladder for streams the
// browser can't play directly:
//   1. mpegts.js over the proxied TS (cheap, no server work);
//   2. HLS (ffmpeg -c copy) via hls.js when the TS remux drops frames;
//   3. HLS (ffmpeg re-encode) when the stream's bitstream is malformed and the
//      hardware decoder still rejects it.

import { attachPlayer, liveTsSupported, type PlayerHandle } from "./mpegts";
import { attachHls, hlsSupported, type HlsHandle } from "./hls";
import type { PlaybackError } from "./playerLogic";

export type StreamMode = "ts" | "hls-copy" | "hls-transcode";

const ORDER: Record<StreamMode, number> = { ts: 0, "hls-copy": 1, "hls-transcode": 2 };

export interface StreamHandle {
  destroy(): void;
  stats(): { speedKBps: number };
  mode(): StreamMode;
}

export function hlsUrlFor(
  portal: string,
  channelId: string,
  variant: "copy" | "transcode" = "copy",
  session = "default",
): string {
  return `/hls/${encodeURIComponent(portal)}/${encodeURIComponent(channelId)}/${variant}/${encodeURIComponent(
    session,
  )}/index.m3u8`;
}

function newSession(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
}

interface AttachOptions {
  tsUrl: string;
  portal: string;
  channelId: string;
  media: HTMLVideoElement;
  muted: boolean;
  onError: (error: PlaybackError) => void;
  onPlaying?: () => void;
}

export function attachStream(options: AttachOptions): StreamHandle | null {
  const session = newSession();
  let stage: StreamMode = "ts";
  let ts: PlayerHandle | null = null;
  let hls: HlsHandle | null = null;
  let destroyed = false;
  let played = false;
  let startedAt = Date.now();
  let lastFrames = 0;
  let lastDropped = 0;

  const onPlaying = () => {
    played = true;
    options.onPlaying?.();
  };

  const resetBaseline = () => {
    const quality = options.media.getVideoPlaybackQuality?.();
    startedAt = Date.now();
    lastFrames = quality?.totalVideoFrames ?? 0;
    lastDropped = quality?.droppedVideoFrames ?? 0;
  };

  const resetMedia = () => {
    try {
      options.media.pause();
      options.media.removeAttribute("src");
      options.media.load();
    } catch {
      /* ignore */
    }
  };

  const startHls = (variant: "copy" | "transcode") => {
    stage = variant === "copy" ? "hls-copy" : "hls-transcode";
    played = false;
    ts?.destroy();
    ts = null;
    hls?.destroy();
    hls = null;
    resetMedia();
    if (!hlsSupported()) {
      options.onError({ kind: "unreachable" });
      return;
    }
    resetBaseline();
    hls = attachHls({
      url: hlsUrlFor(options.portal, options.channelId, variant, session),
      media: options.media,
      muted: options.muted,
      onError: onHlsError,
      onPlaying,
    });
    if (hls == null) options.onError({ kind: "unreachable" });
  };

  const escalate = (target: "hls-copy" | "hls-transcode") => {
    if (destroyed || ORDER[target] <= ORDER[stage]) return;
    startHls(target === "hls-copy" ? "copy" : "transcode");
  };

  const onTsError = (error: PlaybackError) => {
    // A busy tuner is not a remux problem: surface it rather than fall back. And once
    // playback has started, an error means the stream ended (e.g. the operator stopped
    // it) — surface it, don't silently reconnect via the next rung.
    if (error.kind === "all_tuners_busy" || played) {
      options.onError(error);
      return;
    }
    escalate("hls-copy");
  };

  const onHlsError = (error: PlaybackError) => {
    if (error.kind === "all_tuners_busy" || played) {
      options.onError(error);
      return;
    }
    if (stage === "hls-copy") escalate("hls-transcode");
    else options.onError(error);
  };

  if (liveTsSupported()) {
    ts = attachPlayer({
      url: options.tsUrl,
      media: options.media,
      muted: options.muted,
      onError: onTsError,
      onPlaying,
    });
  }
  if (ts == null) startHls("copy");

  const watchdog = window.setInterval(() => {
    if (destroyed) return;
    const quality = options.media.getVideoPlaybackQuality?.();
    if (!quality) return;
    const deltaFrames = quality.totalVideoFrames - lastFrames;
    const deltaDropped = quality.droppedVideoFrames - lastDropped;
    lastFrames = quality.totalVideoFrames;
    lastDropped = quality.droppedVideoFrames;
    const stuttering =
      Date.now() - startedAt > 6000 &&
      quality.totalVideoFrames > 300 &&
      deltaFrames > 0 &&
      deltaDropped / deltaFrames > 0.2;
    if (stuttering && stage === "ts") escalate("hls-copy");
    else if (stuttering && stage === "hls-copy") escalate("hls-transcode");
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
      return stage;
    },
  };
}
