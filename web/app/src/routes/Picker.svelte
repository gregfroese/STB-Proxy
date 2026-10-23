<script lang="ts">
  import { onMount } from "svelte";
  import ChannelTile from "../components/ChannelTile.svelte";
  import Rail from "../components/Rail.svelte";
  import { lineup, lineupError, lineupLoading, loadLineup, onDemandRevoked } from "../lib/lineup";
  import { channelsNotice } from "../lib/onDemand";
  import { onDemandShown } from "../lib/onDemandLogic";
  import {
    CHANNEL_FILTERS,
    applyChannelFilter,
    channelKey,
    channelsInGroup,
    effectiveGroupMode,
    groupMatchCounts,
    groupRail,
    launchGroupFor,
    searchChannels,
    type ChannelFilter,
  } from "../lib/pickerLogic";
  import { groupMode } from "../lib/prefs";
  import { navigate } from "../lib/router";
  import { accountLabel, session } from "../lib/session";
  import type { Channel } from "../lib/types";

  let query = $state("");
  let filter = $state<ChannelFilter>("ALL");
  let activeBlock = $state<string | null>(null);

  onMount(() => {
    void loadLineup();
  });

  const channels = $derived($lineup?.channels ?? []);
  const mode = $derived(effectiveGroupMode($groupMode, $lineup?.blocks ?? []));
  const rail = $derived(groupRail(mode, $lineup?.blocks ?? [], channels));
  const searching = $derived(query.trim() !== "");

  $effect(() => {
    if (rail.length === 0) {
      activeBlock = null;
      return;
    }
    if (activeBlock == null || !rail.some((entry) => entry.name === activeBlock)) {
      activeBlock = rail[0].name;
    }
  });

  const visible = $derived.by(() => {
    const base = searching
      ? searchChannels(channels, query)
      : activeBlock != null
        ? channelsInGroup(mode, channels, activeBlock)
        : [];
    return applyChannelFilter(base, filter);
  });

  const counts = $derived.by(() => {
    if (searching)
      return groupMatchCounts(
        mode,
        channels,
        rail.map((entry) => entry.name),
        query,
      );
    return new Map(rail.map((entry) => [entry.name, entry.count]));
  });

  function pick(channel: Channel) {
    const block = launchGroupFor(mode, channel, activeBlock);
    navigate(
      `/watch?portal=${encodeURIComponent(channel.portal)}&id=${encodeURIComponent(
        channel.channelId,
      )}&block=${encodeURIComponent(block)}`,
    );
  }

  const railEntries = $derived(
    rail.map((entry) => ({
      key: entry.name,
      label: entry.name,
      count: counts.get(entry.name) ?? 0,
    })),
  );

  const label = $derived(accountLabel($session));
  const showOnDemand = $derived(onDemandShown($lineup, $onDemandRevoked));
</script>

<div class="picker">
  <div class="appbar">
    <div class="brand">
      Channels
      <small>{label}</small>
    </div>
    <div class="spacer"></div>
    <button class="btn" onclick={() => navigate("/guide")}>Guide</button>
    {#if showOnDemand}
      <button class="btn" onclick={() => navigate("/ondemand")}>On Demand</button>
    {/if}
    <button class="btn" onclick={() => navigate("/multiview")}>Multiview</button>
    <button class="btn" onclick={() => navigate("/settings")}>Settings</button>
  </div>

  <div class="search">
    <span>⌕</span>
    <input
      placeholder={mode === "genres" ? "Search all Genres…" : "Search all Blocks…"}
      bind:value={query}
    />
  </div>

  <div class="chips">
    {#each CHANNEL_FILTERS as chip (chip.key)}
      <button
        class="chip {chip.key !== 'ALL' ? 'fav' : ''} {filter === chip.key ? 'on' : ''}"
        onclick={() => (filter = chip.key)}
      >
        {chip.label}
      </button>
    {/each}
  </div>

  {#if $channelsNotice}
    <div style="padding: 0 14px 10px">
      <div class="notice noticerow">
        <span>{$channelsNotice}</span>
        <button class="btn" onclick={() => channelsNotice.set(null)}>OK</button>
      </div>
    </div>
  {/if}

  {#if $lineupError}
    <div style="padding: 0 14px 10px">
      <div class="error-banner">{$lineupError}</div>
    </div>
  {/if}

  <div class="bwrap">
    <Rail
      entries={railEntries}
      active={searching ? null : activeBlock}
      onselect={(key) => {
        activeBlock = key;
        query = "";
      }}
    />
    <div class="grid">
      {#if $lineupLoading && !$lineup}
        <div class="empty">Loading channels…</div>
      {:else if channels.length === 0 && !$lineupError}
        <div class="empty">This account has no channels.</div>
      {:else if visible.length === 0}
        <div class="empty">
          {searching ? `No channels match “${query.trim()}”` : "No channels here."}
        </div>
      {:else}
        {#each visible as channel (channelKey(channel))}
          <ChannelTile {channel} {activeBlock} {mode} {searching} onpick={pick} />
        {/each}
      {/if}
    </div>
  </div>
</div>
