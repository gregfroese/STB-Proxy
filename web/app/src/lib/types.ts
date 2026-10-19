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

// Guide — the account-scoped schedule the server serves (ADR 0002). Times are epoch seconds.

export interface GuideProgramme {
  start: number;
  stop: number;
  title: string;
  desc: string;
}

/** One programme in a search hit, joined to the Channel it airs on. */
export interface GuideHit extends GuideProgramme {
  portal: string;
  channelId: string;
  channelName: string;
  channelNumber: string | null;
  logo: string | null;
  epgId: string | null;
}

export interface GuideSearchResult {
  results: GuideHit[];
  total: number;
  loadedAt: number | null;
  programmes: number;
  failed: string[];
  partial: string[];
  account: string | null;
}

/** One Channel's upcoming Programmes (GET /api/guide/channel). */
export interface GuideChannelProgrammes {
  portal: string;
  channelId: string;
  programmes: GuideProgramme[];
}
