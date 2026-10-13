// hls.js over the BFF's ffmpeg-remuxed HLS (spec 2.7 fallback). ffmpeg produces
// fMP4 with correct composition times, which the browser's hardware decoder
// accepts — unlike mpegts.js for B-frame-heavy streams.

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

export function attachHls(options: AttachOptions): HlsHandle | null {
  if (!Hls.isSupported()) return null;

  const hls = new Hls({
    // No blob worker (strict CSPs / mobile quirks); fMP4 segments need no remux.
    enableWorker: false,
    lowLatencyMode: false,
    backBufferLength: 30,
    maxBufferLength: 30,
    liveSyncDurationCount: 3,
  });

  hls.on(Hls.Events.ERROR, (_event, data) => {
    if (!data.fatal) return;
    const code = data.response?.code;
    if (code === 503) options.onError({ kind: "all_tuners_busy" });
    else if (code === 404) options.onError({ kind: "unreachable" });
    else options.onError({ kind: "unreachable" });
  });
  hls.on(Hls.Events.MANIFEST_PARSED, () => options.onPlaying?.());

  options.media.muted = options.muted;
  hls.loadSource(options.url);
  hls.attachMedia(options.media);

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
