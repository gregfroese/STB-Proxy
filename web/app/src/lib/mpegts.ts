// mpegts.js over the BFF's proxied TS (spec 2.7): client-side TS→fMP4→MSE.
// The HTTP status the BFF returns (e.g. 503) is surfaced through the loader
// error, which we classify into the player's PlaybackError taxonomy.

import mpegts from "mpegts.js";
import { classifySourceError, type PlaybackError } from "./playerLogic";

export interface PlayerHandle {
  destroy(): void;
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
        // Main-thread demux: avoids a blob worker (which a strict CSP can block).
        enableWorker: false,
        liveBufferLatencyChasing: true,
        lazyLoad: false,
        stashInitialSize: 128,
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
    };
  } catch {
    options.onError({ kind: "unreachable" });
    return null;
  }
}
