import { get, writable } from "svelte/store";
import { read } from "./api";
import type { Channel, Epg, NowNext, Programme, RawEpg, RawNowNext, RawProgramme } from "./types";

export const epg = writable<Epg>({});

let loaded = false;
let inflight: Promise<void> | null = null;

function mapProgramme(raw: RawProgramme | null): Programme | null {
  if (!raw) return null;
  return {
    title: raw.title,
    start: new Date(raw.start),
    stop: raw.stop ? new Date(raw.stop) : null,
    description: raw.description,
  };
}

function mapNowNext(raw: RawNowNext): NowNext {
  return { now: mapProgramme(raw.now), next: mapProgramme(raw.next) };
}

export async function loadEpg(force = false): Promise<void> {
  if (inflight) return inflight;
  if (loaded && !force) return;
  inflight = (async () => {
    try {
      const raw = await read<RawEpg>("/api/epg");
      const mapped: Epg = {};
      for (const [key, value] of Object.entries(raw)) mapped[key] = mapNowNext(value);
      epg.set(mapped);
      loaded = true;
    } catch {
      // The guide is best-effort; the player/picker still work without it.
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

/** now/next for a channel by its opaque epgId. */
export function nowNextFor(channel: Channel): NowNext | null {
  if (!channel.epgId) return null;
  return get(epg)[channel.epgId] ?? null;
}

export function resetEpg(): void {
  epg.set({});
  loaded = false;
}
