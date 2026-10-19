// The Guide API reads (tickets 02/03): the account-scoped search and one channel's
// timeline, both proxied by the BFF.

import { read } from "./api";
import type { GuideMode } from "./guideLogic";
import type { GuideChannelProgrammes, GuideSearchResult } from "./types";

export interface GuideSearchParams {
  q: string;
  mode: GuideMode;
  now: boolean;
  channel: string;
  limit: number;
}

export async function searchGuide(
  params: GuideSearchParams,
  signal?: AbortSignal,
): Promise<GuideSearchResult> {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  if (params.mode) query.set("mode", params.mode);
  if (params.now) query.set("now", "true");
  if (params.channel) query.set("channel", params.channel);
  query.set("limit", String(params.limit));
  return read<GuideSearchResult>(`/api/guide/search?${query.toString()}`, signal);
}

export async function loadChannelGuide(
  portal: string,
  channelId: string,
  refresh = false,
  signal?: AbortSignal,
): Promise<GuideChannelProgrammes> {
  const query = new URLSearchParams({ portal, channelId });
  if (refresh) query.set("refresh", "1");
  return read<GuideChannelProgrammes>(`/api/guide/channel?${query.toString()}`, signal);
}
