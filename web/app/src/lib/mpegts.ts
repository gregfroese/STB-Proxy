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

export function attachPlayer(options: AttachOptions): PlayerHandle | null {
  if (!mpegts.isSupported()) return null;

  try {
    const player = mpegts.createPlayer(
      { type: "mpegts", isLive: true, url: options.url },
      {
        // Main-thread demux (no blob Worker), a generous stash, and no latency
        // chasing (which drops frames and stutters a live feed). Bound the MSE
        // buffer so long live playback doesn't stall on the SourceBuffer quota.
        enableWorker: false,
        enableStashBuffer: true,
        stashInitialSize: 1024,
        liveBufferLatencyChasing: false,
        autoCleanupSourceBuffer: true,
        autoCleanupMaxBackwardDuration: 30,
        autoCleanupMinBackwardDuration: 10,
        lazyLoad: false,
      },
    );
    player.attachMediaElement(options.media);
    player.on(
      mpegts.Events.ERROR,
      (_type: string, _detail: string, info: { code?: number } | undefined) => {
        const status =
          info && typeof info.code === "number" && info.code >= 100 && info.code <= 599
            ? info.code
            : null;
        options.onError(
          classifySourceError({
            isHttpResponse: status != null,
            responseCode: status,
            location: null,
          }),
        );
      },
    );
    player.on(mpegts.Events.MEDIA_INFO, () => options.onPlaying?.());

    options.media.muted = options.muted;
    player.load();
    const play = player.play() as unknown as Promise<void> | undefined;
    if (play && typeof play.catch === "function") play.catch(() => undefined);

    return {
      destroy() {
        try {
          player.pause();
          player.unload();
          player.detachMediaElement();
          player.destroy();
        } catch {
          /* already torn down */
        }
      },
      stats() {
        try {
          const info = (
            player as unknown as { statisticsInfo?: { speed?: number } }
          ).statisticsInfo;
          return { speedKBps: info?.speed ?? 0 };
        } catch {
          return { speedKBps: 0 };
        }
      },
    };
  } catch {
    options.onError({ kind: "unreachable" });
    return null;
  }
}
