// hls.js over the BFF's ffmpeg-remuxed HLS (spec 2.7 fallback). ffmpeg produces
// fMP4 with correct composition times, which the browser's hardware decoder
// accepts — unlike mpegts.js for B-frame-heavy streams. `attachVod` plays an On Demand
// session's HLS (ticket 12).

import Hls from "hls.js";
import type { PlaybackError } from "./playerLogic";

export interface HlsHandle {
  destroy(): void;
}

export function hlsSupported(): boolean {
  try {
    return Hls.isSupported();
  } catch {
    return false;
  }
}

interface AttachOptions {
  url: string;
  media: HTMLVideoElement;
  muted: boolean;
  onError: (error: PlaybackError) => void;
  onPlaying?: () => void;
}

function loadPolicy(retries: number) {
  const retry = { maxNumRetry: retries, retryDelayMs: 500, maxRetryDelayMs: 2000 };
  return {
    default: {
      maxTimeToFirstByteMs: 10000,
      maxLoadTimeMs: 20000,
      timeoutRetry: retry,
      errorRetry: retry,
    },
  };
}

interface VodOptions {
  url: string;
  media: HTMLVideoElement;
  /** Where to start once loaded (a Resume point), in seconds. */
  startSec: number;
  /** The stream can't carry on; `status` is the failing request's HTTP status, if any. */
  onFatal: (status: number | null) => void;
  /** The browser refused to autoplay with sound, so playback started muted. */
  onMutedAutoplay?: () => void;
}

function playWithFallback(media: HTMLVideoElement, onMuted?: () => void) {
  const play = media.play() as unknown as Promise<void> | undefined;
  if (!play || typeof play.catch !== "function") return;
  play.catch((error: unknown) => {
    if (!(error instanceof DOMException) || error.name !== "NotAllowedError" || media.muted) return;
    media.muted = true;
    onMuted?.();
    const retry = media.play() as unknown as Promise<void> | undefined;
    if (retry && typeof retry.catch === "function") retry.catch(() => undefined);
  });
}

/**
 * An On Demand session's HLS (ticket 12): VOD, seekable, starting at `startSec`. hls.js
 * where MSE exists, else the browser's own HLS (Safari). The session's segments are never
 * shared, so a 4xx (410 when the session ended) is fatal straight away.
 */
export function attachVod(options: VodOptions): HlsHandle {
  const media = options.media;
  let failed = false;
  const fail = (status: number | null) => {
    if (failed) return;
    failed = true;
    options.onFatal(status);
  };

  if (!Hls.isSupported() && media.canPlayType("application/vnd.apple.mpegurl")) {
    const onMeta = () => {
      if (options.startSec > 0) media.currentTime = options.startSec;
      playWithFallback(media, options.onMutedAutoplay);
    };
    const onError = () => fail(null);
    media.addEventListener("loadedmetadata", onMeta, { once: true });
    media.addEventListener("error", onError);
    media.src = options.url;
    return {
      destroy() {
        media.removeEventListener("loadedmetadata", onMeta);
        media.removeEventListener("error", onError);
        media.removeAttribute("src");
        media.load();
      },
    };
  }

  const hls = new Hls({
    // No blob worker (strict CSP), as for live.
    enableWorker: false,
    startPosition: options.startSec > 0 ? options.startSec : -1,
    maxBufferLength: 30,
    backBufferLength: 30,
    manifestLoadPolicy: loadPolicy(1),
    playlistLoadPolicy: loadPolicy(2),
    fragLoadPolicy: loadPolicy(3),
  });
  hls.on(Hls.Events.ERROR, (_event, data) => {
    const status = data.response?.code ?? null;
    // A 410 is the session ending: don't let hls.js stall on it as a non-fatal error.
    if (data.fatal || status === 410) fail(status || null);
  });
  hls.on(Hls.Events.MANIFEST_PARSED, () => playWithFallback(media, options.onMutedAutoplay));
  hls.loadSource(options.url);
  hls.attachMedia(media);

  return {
    destroy() {
      try {
        hls.destroy();
      } catch {
        /* already torn down */
      }
    },
  };
}

export function attachHls(options: AttachOptions): HlsHandle | null {
  if (!Hls.isSupported()) return null;

  const hls = new Hls({
    // No blob worker (strict CSPs / mobile quirks); fMP4 segments need no remux.
    enableWorker: false,
    lowLatencyMode: false,
    backBufferLength: 30,
    maxBufferLength: 30,
    liveSyncDurationCount: 3,
    // Give up quickly if the stream ends (e.g. the operator stopped it) rather
    // than retrying a dead playlist for a long time.
    manifestLoadPolicy: loadPolicy(1),
    playlistLoadPolicy: loadPolicy(2),
    fragLoadPolicy: loadPolicy(2),
  });

  const playMedia = () => {
    const play = options.media.play() as unknown as Promise<void> | undefined;
    if (play && typeof play.catch === "function") play.catch(() => undefined);
  };

  hls.on(Hls.Events.ERROR, (_event, data) => {
    if (!data.fatal) return;
    const code = data.response?.code;
    if (code === 503) options.onError({ kind: "all_tuners_busy" });
    else if (code === 404) options.onError({ kind: "unreachable" });
    else options.onError({ kind: "unreachable" });
  });
  hls.on(Hls.Events.MANIFEST_PARSED, () => {
    options.onPlaying?.();
    playMedia();
  });

  options.media.muted = options.muted;
  hls.loadSource(options.url);
  hls.attachMedia(options.media);
  playMedia();

  return {
    destroy() {
      try {
        hls.destroy();
      } catch {
        /* already torn down */
      }
    },
  };
}
