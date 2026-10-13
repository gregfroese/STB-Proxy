// Hand-written types mirroring the BFF/lineup contract (spec 1.2, 1.4). No zod.

export interface Channel {
  portal: string;
  portalName: string;
  channelId: string;
  name: string;
  number: string | null;
  logo: string | null;
  genre: string | null;
  epgId: string | null;
  blocks: string[];
  favourite: boolean;
  blockFavourites: string[];
  url: string;
}

export interface Lineup {
  account: string | null;
  blocks: string[];
  channels: Channel[];
  failedPortals: string[];
}

export interface SessionInfo {
  account: string | null;
  operator: boolean;
  csrf: string;
}

export interface ApiErrorBody {
  error: string;
  code: string;
}

// EPG — server-side now/next keyed by epgId (spec 2.6).

export interface Programme {
  title: string;
  start: Date;
  stop: Date | null;
  description: string | null;
}

export interface NowNext {
  now: Programme | null;
  next: Programme | null;
}

export type Epg = Record<string, NowNext>;

/** The wire shape of GET /api/epg (dates are ISO strings). */
export interface RawProgramme {
  title: string;
  start: string;
  stop: string | null;
  description: string | null;
}

export interface RawNowNext {
  now: RawProgramme | null;
  next: RawProgramme | null;
}

export type RawEpg = Record<string, RawNowNext>;
