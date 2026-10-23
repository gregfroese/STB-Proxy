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
  /** True when this login's Account may use On Demand (ADR 0004). */
  onDemand?: boolean;
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

// On Demand — the viewer catalogue (/api/ondemand/*, ADRs 0003-0006).

export type OnDemandKind = "movie" | "series";

/** A Movie's viewing state for this Account (ADR 0006). */
export interface OnDemandProgress {
  positionSec: number | null;
  durationSec: number | null;
  watched: boolean;
  updatedAt: number;
}

/** A Series' next Episode for this Account (ADR 0006). */
export interface OnDemandUpNext {
  seasonId: string;
  seasonNumber: number | null;
  episodeId: string;
  episodeNumber: number | null;
  name: string | null;
  positionSec: number | null;
  durationSec: number | null;
}

/** One Movie or Series in a list (/items, /continue). */
export interface OnDemandItem {
  portal: string;
  portalName: string;
  id: string;
  kind: OnDemandKind;
  name: string;
  year: number | null;
  rating: number | null;
  added: string | null;
  poster: string | null;
  /** Movies only; null when never played. */
  progress?: OnDemandProgress | null;
  /** Series only; null when there is none. */
  upNext?: OnDemandUpNext | null;
}

export interface OnDemandCategory {
  id: string;
  name: string;
  count: number;
}

export type OnDemandPortalStatus = "indexing" | "ready" | "stale" | "partial" | "failed";

export interface OnDemandPortal {
  portal: string;
  name: string;
  status: OnDemandPortalStatus;
  /** Percent indexed while indexing, else null. */
  progress: number | null;
  /** Epoch seconds of the last good refresh, or null. */
  lastRefresh: number | null;
}

export interface OnDemandCategories {
  categories: OnDemandCategory[];
  portals: OnDemandPortal[];
}

export interface OnDemandPage {
  items: OnDemandItem[];
  total: number;
  offset: number;
  limit: number;
}
