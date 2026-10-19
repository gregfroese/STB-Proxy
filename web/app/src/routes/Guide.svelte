<script lang="ts">
  import { onMount } from "svelte";
  import Logo from "../components/Logo.svelte";
  import { ApiError } from "../lib/api";
  import { epg, loadEpg } from "../lib/epg";
  import { formatTime } from "../lib/format";
  import { lineup, lineupLoading, loadLineup } from "../lib/lineup";
  import { loadChannelGuide, searchGuide, type GuideSearchParams } from "../lib/guide";
  import {
    DEFAULT_GUIDE_MODE,
    GUIDE_DEBOUNCE_MS,
    GUIDE_LIMIT_DEFAULT,
    GUIDE_LIMIT_MAX,
    GUIDE_MODES,
    airingChannels,
    filterChannels,
    hitChannels,
    isAiring,
    nextGuideLimit,
    resultCountLabel,
    type GuideMode,
  } from "../lib/guideLogic";
  import {
    channelKey,
    channelsInGroup,
    effectiveGroupMode,
    groupRail,
    launchGroupFor,
  } from "../lib/pickerLogic";  import { epgRefreshAction } from "../lib/playerLogic";
  import { groupMode } from "../lib/prefs";
  import { navigate } from "../lib/router";
  import { scopeKeys, watchUrl, type ZapScope } from "../lib/zapScope";
  import type { Channel, GuideHit, GuideProgramme, GuideSearchResult } from "../lib/types";

  let query = $state("");
  let mode = $state<GuideMode>(DEFAULT_GUIDE_MODE);
  let advanced = $state(false);
  let onNow = $state(false);
  let channelFilter = $state("");
  let limit = $state(GUIDE_LIMIT_DEFAULT);
  let openKey = $state<string | null>(null);
  let now = $state(Date.now());

  let result = $state<GuideSearchResult | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);

  let timelines = $state<Record<string, GuideProgramme[]>>({});
  let timelineLoading = $state<Record<string, boolean>>({});

  let controller: AbortController | null = null;
  let lastComputed = Date.now();

  onMount(() => {
    void loadLineup();
    void loadEpg();
    const timer = window.setInterval(() => {
      const t = Date.now();
      now = t;
      if (query.trim() === "") return;
      const stop = result?.results[0]?.stop ? new Date(result.results[0].stop * 1000) : null;
      const action = epgRefreshAction(new Date(t), new Date(lastComputed), stop);
      if (action === "REFETCH") {
        lastComputed = t;
        void runSearch();
      } else if (action === "RECOMPUTE") {
        lastComputed = t;
      }
    }, 30000);
    const onVisibility = () => {
      if (document.visibilityState !== "visible") return;
      now = Date.now();
      lastComputed = now;
      if (query.trim() !== "") void runSearch();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
      controller?.abort();
    };
  });

  const channels = $derived($lineup?.channels ?? []);
  const effMode = $derived(effectiveGroupMode($groupMode, $lineup?.blocks ?? []));
  const searching = $derived(query.trim() !== "");
  const hits = $derived(result?.results ?? []);
  const resultChannels = $derived(hitChannels(hits, channels));
  const total = $derived(result?.total ?? 0);

  const browseChannels = $derived.by(() => {
    let list = filterChannels(channels, channelFilter);
    if (onNow) list = airingChannels(list, $epg, now);
    return list;
  });
  const sections = $derived.by(() =>
    groupRail(effMode, $lineup?.blocks ?? [], browseChannels)
      .map((entry) => ({
        name: entry.name,
        channels: channelsInGroup(effMode, browseChannels, entry.name),
      }))
      .filter((section) => section.channels.length > 0),
  );
  const browseOrder = $derived(sections.flatMap((section) => section.channels));

  const notice = $derived.by(() => {
    const failed = result?.failed ?? [];
    const partial = result?.partial ?? $lineup?.failedPortals ?? [];
    const parts: string[] = [];
    if (failed.length) parts.push(`Guide unavailable for ${failed.join(", ")}`);
    if (partial.length) parts.push(`Partial guide for ${partial.join(", ")}`);
    return parts.length ? parts.join(" · ") : null;
  });

  $effect(() => {
    const q = query.trim();
    const m = mode;
    const n = onNow;
    const cf = channelFilter;
    const lim = limit;
    if (q === "") {
      controller?.abort();
      result = null;
      error = null;
      loading = false;
      return;
    }
    const timer = window.setTimeout(
      () => void runSearch({ q, mode: m, now: n, channel: cf, limit: lim }),
      GUIDE_DEBOUNCE_MS,
    );
    return () => window.clearTimeout(timer);
  });

  async function runSearch(overrides: Partial<GuideSearchParams> = {}): Promise<void> {
    controller?.abort();
    const current = new AbortController();
    controller = current;
    loading = true;
    error = null;
    try {
      result = await searchGuide(
        {
          q: query.trim(),
          mode,
          now: onNow,
          channel: channelFilter.trim(),
          limit,
          ...overrides,
        },
        current.signal,
      );
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      error = caught instanceof ApiError ? caught.message : "Could not search the guide.";
      result = null;
    } finally {
      if (controller === current) loading = false;
    }
  }

  function loadMore(): void {
    limit = nextGuideLimit(limit);
  }

  function reload(): void {
    timelines = {};
    openKey = null;
    if (searching) {
      void runSearch();
    } else {
      void loadEpg(true);
      now = Date.now();
    }
  }

  async function toggleTimeline(channel: Channel): Promise<void> {
    const key = channelKey(channel);
    if (openKey === key) {
      openKey = null;
      return;
    }
    openKey = key;
    if (timelines[key]) return;
    timelineLoading = { ...timelineLoading, [key]: true };
    try {
      const data = await loadChannelGuide(channel.portal, channel.channelId);
      timelines = { ...timelines, [key]: data.programmes };
    } catch {
      timelines = { ...timelines, [key]: [] };
    } finally {
      timelineLoading = { ...timelineLoading, [key]: false };
    }
  }

  function groupScopeFor(channel: Channel): ZapScope {
    const label = launchGroupFor(effMode, channel, null);
    return { kind: "group", block: label, label };
  }

  function playBrowse(channel: Channel): void {
    if (onNow && browseOrder.length > 0) {
      navigate(watchUrl(channel, { kind: "list", keys: scopeKeys(browseOrder), label: "On now" }));
      return;
    }
    navigate(watchUrl(channel, groupScopeFor(channel)));
  }

  function playHit(hit: GuideHit): void {
    const channel = channels.find(
      (item) => item.portal === hit.portal && item.channelId === hit.channelId,
    );
    if (!channel) return;
    const label = query.trim() ? `Search: “${query.trim()}”` : `Results (${resultChannels.length})`;
    navigate(watchUrl(channel, { kind: "list", keys: scopeKeys(resultChannels), label }));
  }

  function channelForHit(hit: GuideHit): Channel | null {
    return (
      channels.find((item) => item.portal === hit.portal && item.channelId === hit.channelId) ??
      null
    );
  }

  function hhmm(seconds: number): string {
    return formatTime(new Date(seconds * 1000));
  }

  function programmeAiring(programme: GuideProgramme): boolean {
    return isAiring(programme, now);
  }

  function progressOf(programme: GuideProgramme): number {
    const span = programme.stop - programme.start;
    if (span <= 0) return 0;
    return Math.min(1, Math.max(0, (now / 1000 - programme.start) / span));
  }
</script>

<div class="guide">
  <div class="appbar">
    <button class="btn" onclick={() => navigate("/")}>‹ Channels</button>
    <div class="brand">
      Guide
      <small>{$groupMode === "genres" ? "Genres" : "Blocks"} · next 24h</small>
    </div>
    <div class="spacer"></div>
    <button class="btn" onclick={reload}>Reload</button>
    <button class="btn" onclick={() => navigate("/settings")}>Settings</button>
  </div>

  <div class="ghead">
    <div class="search">
      <span>⌕</span>
      <input
        placeholder="Search programmes across your lineup…"
        bind:value={query}
        onkeydown={(event) => {
          if (event.key === "Enter") void runSearch();
        }}
      />
    </div>
    <div class="seg">
      <button class={onNow ? "" : "on"} onclick={() => (onNow = false)}>All</button>
      <button class={onNow ? "on" : ""} onclick={() => (onNow = true)}>On now</button>
    </div>
    <div class="seg">
      <button class={$groupMode === "blocks" ? "on" : ""} onclick={() => groupMode.set("blocks")}
        >Blocks</button
      >
      <button class={$groupMode === "genres" ? "on" : ""} onclick={() => groupMode.set("genres")}
        >Genres</button
      >
    </div>
    <input class="btn gchan" placeholder="channel…" bind:value={channelFilter} />
    <button class="btn {advanced ? "on" : ""}" onclick={() => (advanced = !advanced)}>
      Match
    </button>
  </div>

  {#if advanced}
    <div class="chips">
      {#each GUIDE_MODES as option (option)}
        <button class="chip {mode === option ? 'on' : ''}" onclick={() => (mode = option)}>
          {option}
        </button>
      {/each}
      <span class="gdimm">How each search term matches programme titles and descriptions.</span>
    </div>
  {/if}

  {#if notice}
    <div class="gnote">{notice}</div>
  {/if}
  {#if error}
    <div class="gnote bad">{error}</div>
  {/if}

  {#if $lineupLoading && !$lineup}
    <div class="empty">Loading channels…</div>
  {:else if searching}
    <div class="rows">
      {#if loading && hits.length === 0}
        <div class="empty">Searching…</div>
      {:else if !error && hits.length === 0}
        <div class="empty">No programmes match “{query.trim()}”.</div>
      {:else}
        <div class="gcount">{resultCountLabel(hits.length, total)}</div>
        {#each hits as hit (`${hit.portal}:${hit.channelId}:${hit.start}:${hit.title}`)}
          {@const channel = channelForHit(hit)}
          <div class="rrow">
            <button class="rmain" onclick={() => playHit(hit)} title="Play">
              <span class="when">
                <b>{hhmm(hit.start)}</b>
                {hhmm(hit.stop)}
              </span>
              <span class="mid">
                <span class="tt">{hit.title}</span>
                <span class="cc">
                  <Logo name={hit.channelName} logo={hit.logo} size={18} />
                  {hit.channelNumber ? `CH ${hit.channelNumber}` : ""} {hit.channelName}
                  {#if programmeAiring(hit)}
                    <span class="now">● ON NOW</span>
                  {/if}
                </span>
              </span>
            </button>
            {#if channel}
              <button
                class="rexp"
                title="Timeline"
                onclick={() => toggleTimeline(channel)}
              >
                {openKey === channelKey(channel) ? "⌃" : "⌄"}
              </button>
            {/if}
          </div>
          {#if channel && openKey === channelKey(channel)}
            <div class="tl">
              {#if timelineLoading[channelKey(channel)]}
                <div class="empty">Loading timeline…</div>
              {:else}
                {#each timelines[channelKey(channel)] ?? [] as programme (`${programme.start}`)}
                  <div class="tlrow {programmeAiring(programme) ? 'airing' : ''}">
                    <span class="t">{hhmm(programme.start)}</span>
                    <span class="n">{programme.title}</span>
                    {#if programmeAiring(programme)}
                      <span class="pbar"><i style="width:{Math.round(progressOf(programme) * 100)}%"
                        ></i></span>
                      <span class="now">● ON NOW</span>
                    {/if}
                  </div>
                {/each}
              {/if}
            </div>
          {/if}
        {/each}
        {#if total > hits.length && limit < GUIDE_LIMIT_MAX}
          <button class="btn" onclick={loadMore}>Load more</button>
        {:else if total > hits.length}
          <div class="gdimm">Refine your search to see fewer results.</div>
        {/if}
      {/if}
    </div>
  {:else}
    <div class="acc">
      {#if browseChannels.length === 0}
        <div class="empty">
          {onNow ? "Nothing is on now." : "No channels here."}
        </div>
      {:else}
        {#each sections as section (section.name)}
          <div class="gsec">{section.name}</div>
          {#each section.channels as channel (channelKey(channel))}
            {@const nowNext = channel.epgId ? ($epg[channel.epgId] ?? null) : null}
            {@const current = nowNext?.now ?? null}
            <div class="cch">
              <div class="chead">
                <button class="cheadmain" onclick={() => toggleTimeline(channel)}>
                  <Logo name={channel.name} logo={channel.logo} size={34} />
                  <span class="who">
                    <span class="nm">{channel.name}</span>
                    <span class="nowline">
                      {channel.number ? `CH ${channel.number} · ` : ""}{current
                        ? `${current.title} ${formatTime(current.start)}–${formatTime(current.stop)}`
                        : "No guide data"}
                    </span>
                  </span>
                  <span class="chev">›</span>
                </button>
                <button class="btn primary" onclick={() => playBrowse(channel)}>▶</button>
              </div>
              {#if openKey === channelKey(channel)}
                <div class="cbody">
                  {#if timelineLoading[channelKey(channel)]}
                    <div class="empty">Loading timeline…</div>
                  {:else}
                    <div class="tl">
                      {#each timelines[channelKey(channel)] ?? [] as programme (`${programme.start}`)}
                        <div class="tlrow {programmeAiring(programme) ? 'airing' : ''}">
                          <span class="t">{hhmm(programme.start)}</span>
                          <span class="n">{programme.title}</span>
                          {#if programmeAiring(programme)}
                            <span class="now">● ON NOW</span>
                          {/if}
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/if}
            </div>
          {/each}
        {/each}
      {/if}
    </div>
  {/if}
</div>
