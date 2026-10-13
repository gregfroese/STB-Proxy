// mpegts.js over the BFF's proxied TS (spec 2.7): client-side TS→fMP4→MSE.
// The HTTP status the BFF returns (e.g. 503) is surfaced through the loader
// error, which we classify into the player's PlaybackError taxonomy.

import mpegts from "mpegts.js";
import { classifySourceError, type PlaybackError } from "./playerLogic";

export interface PlayerHandle {
  destroy(): void;
  stats(): { speedKBps: number };
}

export function liveTsSupported(): boolean {
  try {
    return mpegts.isSupported() && mpegts.getFeatureList().mseLivePlayback === true;
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

const PLAYER_CONFIG = {
  // A generous stash smooths jitter, and we do NOT chase latency (chasing drops
  // frames and stutters a live feed). Bound the MSE buffer so long live playback
  // doesn't stall on the SourceBuffer quota.
  enableStashBuffer: true,
  stashInitialSize: 1024,
  liveBufferLatencyChasing: false,
  autoCleanupSourceBuffer: true,
  autoCleanupMaxBackwardDuration: 30,
  autoCleanupMinBackwardDuration: 10,
  lazyLoad: false,
} as const;

type MpegtsPlayer = ReturnType<typeof mpegts.createPlayer>;

function classify(info: { code?: number } | undefined): PlaybackError {
  const status =
    info && typeof info.code === "number" && info.code >= 100 && info.code <= 599
      ? info.code
      : null;
  return classifySourceError({
    isHttpResponse: status != null,
    responseCode: status,
    location: null,
  });
}

export function attachPlayer(options: AttachOptions): PlayerHandle | null {
  if (!mpegts.isSupported()) return null;

  let player: MpegtsPlayer | null = null;
  let gotMedia = false;
  let usingWorker = true;
  let destroyed = false;

  const start = (worker: boolean): void => {
    player = mpegts.createPlayer(
      { type: "mpegts", isLive: true, url: options.url },
      { ...PLAYER_CONFIG, enableWorker: worker },
    );
    player.attachMediaElement(options.media);
    player.on(mpegts.Events.ERROR, (_type: string, _detail: string, info: { code?: number }) => {
      if (!gotMedia && usingWorker && !destroyed) {
        // The blob worker is unavailable here (e.g. CSP): retry on the main thread.
        usingWorker = false;
        try {
          player?.destroy();
        } catch {
          /* ignore */
        }
        start(false);
        return;
      }
      options.onError(classify(info));
    });
    player.on(mpegts.Events.MEDIA_INFO, () => {
      gotMedia = true;
      options.onPlaying?.();
    });
    options.media.muted = options.muted;
    player.load();
    const play = player.play() as unknown as Promise<void> | undefined;
    if (play && typeof play.catch === "function") play.catch(() => undefined);
  };

  try {
    start(true);
  } catch {
    try {
      start(false);
    } catch {
      options.onError({ kind: "unreachable" });
      return null;
    }
  }

  return {
    destroy() {
      destroyed = true;
      try {
        player?.pause();
        player?.unload();
        player?.detachMediaElement();
        player?.destroy();
      } catch {
        /* already torn down */
      }
    },
    stats() {
      try {
        const info = (player as unknown as { statisticsInfo?: { speed?: number } } | null)
          ?.statisticsInfo;
        return { speedKBps: info?.speed ?? 0 };
      } catch {
        return { speedKBps: 0 };
      }
    },
  };
}
