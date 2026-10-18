<script lang="ts">
  import { onMount } from "svelte";
  import Logo from "../components/Logo.svelte";
  import MultiviewTile from "../components/MultiviewTile.svelte";
  import { loadEpg } from "../lib/epg";
  import { lineup, loadLineup } from "../lib/lineup";
  import {
    LAYOUTS,
    assignChannel,
    effectiveAudioSlot,
    removeTile,
    swapTiles,
    visibleTiles,
  } from "../lib/multiviewLogic";
  import { audioSlot, layout, tileErrors, tiles } from "../lib/multiview";
  import {
    CHANNEL_FILTERS,
    applyChannelFilter,
    channelKey,
    channelsInGroup,
    effectiveGroupMode,
    groupRail,
    searchChannels,
    type ChannelFilter,
  } from "../lib/pickerLogic";
  import { groupMode } from "../lib/prefs";
  import type { PlaybackError } from "../lib/playerLogic";
  import { navigate } from "../lib/router";
  import type { Channel } from "../lib/types";

  let pickSlot = $state<number | null>(null);
  let pickQuery = $state("");
  let pickFilter = $state<ChannelFilter>("ALL");
  let pickBlock = $state<string | null>(null);
  let armed = $state<number | null>(null);
  let retryKeys = $state<Record<number, number>>({});
  let unmuted = $state(false);
  let phone = $state(false);
  let portrait = $state(false);
  let rootEl: HTMLDivElement | undefined = $state();

  $effect(() => {
    const el = rootEl;
    if (!el) return;
    const unmute = () => (unmuted = true);
    el.addEventListener("pointerdown", unmute);
    return () => el.removeEventListener("pointerdown", unmute);
  });

  onMount(() => {
    void loadLineup();
    void loadEpg();
    const phoneQuery = window.matchMedia("(max-width: 720px)");
    const portraitQuery = window.matchMedia("(orientation: portrait)");
    const sync = () => {
      phone = phoneQuery.matches;
      portrait = portraitQuery.matches;
    };
    sync();
    phoneQuery.addEventListener("change", sync);
    portraitQuery.addEventListener("change", sync);
    return () => {
      phoneQuery.removeEventListener("change", sync);
      portraitQuery.removeEventListener("change", sync);
    };
  });

  const channels = $derived($lineup?.channels ?? []);

  // Phone: two tiles, laid out by orientation (landscape 2×1, portrait 1×2).
  // Desktop uses the layout chooser.
  const shown = $derived.by(() => {
    if (phone) return $tiles.slice(0, 2);
    return visibleTiles($tiles, $layout);
  });

  const LAYOUT_CLASS: Record<string, string> = {
    big: "big",
    "2x1": "two-by-one",
    "1x2": "one-by-two",
    "2x2": "two",
    "3x3": "three",
  };

  const layoutClass = $derived.by(() => {
    if (phone) return portrait ? "one-by-two" : "two-by-one";
    return LAYOUT_CLASS[$layout];
  });

  const audio = $derived(effectiveAudioSlot($tiles, $audioSlot));

  const pickSearching = $derived(pickQuery.trim() !== "");
  const pickMode = $derived(effectiveGroupMode($groupMode, $lineup?.blocks ?? []));
  const pickRail = $derived(groupRail(pickMode, $lineup?.blocks ?? [], channels));
  const pickVisible = $derived.by(() => {
    const base = pickSearching
      ? searchChannels(channels, pickQuery)
      : channelsInGroup(pickMode, channels, pickBlock ?? "");
    return applyChannelFilter(base, pickFilter);
  });

  $effect(() => {
    if (pickSlot == null) return;
    if (pickBlock == null || !pickRail.some((entry) => entry.name === pickBlock)) {
      pickBlock = pickRail[0]?.name ?? null;
    }
  });

  function setError(slot: number, error: PlaybackError | null) {
    tileErrors.update((map) => ({ ...map, [slot]: error }));
  }

  function openPick(slot: number) {
    pickSlot = slot;
    pickQuery = "";
    pickFilter = "ALL";
    pickBlock = pickRail[0]?.name ?? null;
  }

  function choose(channel: Channel) {
    if (pickSlot == null) return;
    const slot = pickSlot;
    tiles.update((list) => assignChannel(list, slot, channel));
    tileErrors.update((map) => ({ ...map, [slot]: null }));
    pickSlot = null;
  }

  function remove(slot: number) {
    tiles.update((list) => removeTile(list, slot));
    tileErrors.update((map) => ({ ...map, [slot]: null }));
  }

  function swap(slot: number) {
    if (armed == null) {
      armed = slot;
      return;
    }
    if (armed !== slot) tiles.update((list) => swapTiles(list, armed as number, slot));
    armed = null;
  }

  function tileClick(slot: number) {
    if (armed != null && armed !== slot) {
      tiles.update((list) => swapTiles(list, armed as number, slot));
    }
    armed = null;
  }

  function retry(slot: number) {
    retryKeys = { ...retryKeys, [slot]: (retryKeys[slot] ?? 0) + 1 };
  }

  function chooseAudio(slot: number) {
    audioSlot.set(slot);
    unmuted = true;
  }
</script>

<div class="multiview" bind:this={rootEl}>
  <div class="mvbar">
    <button class="btn" onclick={() => navigate("/")}>‹ Channels</button>
    <div class="brand">Multiview</div>
    <div class="spacer"></div>
    {#if !phone}
      <div class="seg">
        {#each LAYOUTS as option (option.key)}
          <button class={$layout === option.key ? "on" : ""} onclick={() => layout.set(option.key)}>
            {option.label}
          </button>
        {/each}
      </div>
    {/if}
    <button class="btn" onclick={() => navigate("/settings")}>Settings</button>
  </div>

  <div class="mvgrid {layoutClass}">
    {#each shown as tile (tile.slot)}
      <MultiviewTile
        {tile}
        audio={unmuted && audio === tile.slot}
        error={$tileErrors[tile.slot] ?? null}
        armed={armed === tile.slot}
        retryKey={retryKeys[tile.slot] ?? 0}
        onError={setError}
        onPick={openPick}
        onSwap={swap}
        onAudio={chooseAudio}
        onRemove={remove}
        onTileClick={tileClick}
        onRetry={retry}
      />
    {/each}
  </div>
</div>

{#if pickSlot != null}
  <div
    class="ovl"
    role="presentation"
    onclick={(event) => {
      if (event.target === event.currentTarget) pickSlot = null;
    }}
  >
    <div class="box">
      <div class="bh">Pick channel for tile #{pickSlot + 1}</div>
      <div style="padding: 8px 10px 0">
        <div class="search" style="margin: 0">
          <span>⌕</span>
          <input
            placeholder={pickMode === "genres" ? "Search all Genres…" : "Search all Blocks…"}
            bind:value={pickQuery}
          />
        </div>
      </div>
      <div class="chips" style="padding: 8px 10px">
        {#each CHANNEL_FILTERS as chip (chip.key)}
          <button
            class="chip {chip.key !== 'ALL' ? 'fav' : ''} {pickFilter === chip.key ? 'on' : ''}"
            onclick={() => (pickFilter = chip.key)}
          >
            {chip.label}
          </button>
        {/each}
      </div>
      {#if !pickSearching}
        <div class="pickrail">
          {#each pickRail as entry (entry.name)}
            <button
              class="railchip {pickBlock === entry.name ? 'on' : ''}"
              onclick={() => (pickBlock = entry.name)}
            >
              {entry.name} <span>{entry.count}</span>
            </button>
          {/each}
        </div>
      {/if}
      <div class="bl">
        {#each pickVisible as channel (channelKey(channel))}
          <button class="r" onclick={() => choose(channel)}>
            <Logo name={channel.name} logo={channel.logo} size={40} />
            <div style="flex: 1">
              <div>
                {channel.name}{#if channel.favourite}<span style="color: var(--star)"> ★</span>{/if}
              </div>
              <div style="font-size: 11px; color: var(--dim)">
                CH {channel.number ?? "—"}{pickMode === "genres"
                  ? channel.genre
                    ? ` · ${channel.genre}`
                    : ""
                  : channel.blocks.length
                    ? ` · ${channel.blocks.join(", ")}`
                    : ""}
                {#each channel.blockFavourites as block (block)}
                  <span style="color: var(--star)"> ★ {block}</span>
                {/each}
              </div>
            </div>
          </button>
        {:else}
          <div class="notice" style="margin: 8px">
            {pickSearching ? `No channels match “${pickQuery.trim()}”` : "No channels here."}
          </div>
        {/each}
      </div>
      <div class="bf"><button class="btn" onclick={() => (pickSlot = null)}>Cancel</button></div>
    </div>
  </div>
{/if}
