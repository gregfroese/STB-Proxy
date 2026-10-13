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
    type MultiviewLayout,
  } from "../lib/multiviewLogic";
  import { audioSlot, layout, tileErrors, tiles } from "../lib/multiview";
  import type { PlaybackError } from "../lib/playerLogic";
  import { navigate } from "../lib/router";
  import type { Channel } from "../lib/types";

  const LAYOUT_KEY = "stbproxy.multiview.layout";
  const TILES_KEY = "stbproxy.multiview.tiles";

  let pickSlot = $state<number | null>(null);
  let armed = $state<number | null>(null);
  let pickQuery = $state("");
  let retryKeys = $state<Record<number, number>>({});
  let hydrationKeys: (string | null)[] = [];
  let hydrated = false;

  onMount(() => {
    void loadLineup();
    void loadEpg();
    const savedLayout = localStorage.getItem(LAYOUT_KEY) as MultiviewLayout | null;
    if (savedLayout && LAYOUTS.some((entry) => entry.key === savedLayout)) {
      layout.set(savedLayout);
    }
    try {
      const saved = localStorage.getItem(TILES_KEY);
      if (saved) hydrationKeys = JSON.parse(saved) as (string | null)[];
    } catch {
      hydrationKeys = [];
    }
  });

  $effect(() => {
    const line = $lineup;
    if (!line || hydrated || hydrationKeys.length === 0) return;
    hydrated = true;
    const byKey = new Map(line.channels.map((c) => [`${c.portal}:${c.channelId}`, c]));
    tiles.update((list) =>
      list.map((tile, index) => {
        const key = hydrationKeys[index];
        const channel = key ? byKey.get(key) : undefined;
        return channel ? { ...tile, channel } : tile;
      }),
    );
  });

  $effect(() => {
    localStorage.setItem(
      TILES_KEY,
      JSON.stringify(
        $tiles.map((tile) =>
          tile.channel ? `${tile.channel.portal}:${tile.channel.channelId}` : null,
        ),
      ),
    );
  });

  $effect(() => {
    localStorage.setItem(LAYOUT_KEY, $layout);
  });

  const channels = $derived($lineup?.channels ?? []);
  const shown = $derived(visibleTiles($tiles, $layout));
  const audio = $derived(effectiveAudioSlot($tiles, $audioSlot));

  const pickMatches = $derived.by(() => {
    const needle = pickQuery.trim().toLowerCase();
    if (!needle) return channels;
    return channels.filter(
      (channel) =>
        channel.name.toLowerCase().includes(needle) || (channel.number ?? "").includes(needle),
    );
  });

  const gridClass = $derived($layout === "big" ? "big" : $layout === "2x2" ? "two" : "three");

  function setError(slot: number, error: PlaybackError | null) {
    tileErrors.update((map) => ({ ...map, [slot]: error }));
  }

  function openPick(slot: number) {
    pickSlot = slot;
    pickQuery = "";
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

  function activate(slot: number) {
    if (armed != null && armed !== slot) {
      tiles.update((list) => swapTiles(list, armed as number, slot));
      armed = null;
      return;
    }
    armed = null;
    retryKeys = { ...retryKeys, [slot]: (retryKeys[slot] ?? 0) + 1 };
  }
</script>

<div class="multiview">
  <div class="mvbar">
    <button class="btn" onclick={() => navigate("/")}>‹ Channels</button>
    <div class="brand">Multiview</div>
    <div class="spacer"></div>
    <div class="seg">
      {#each LAYOUTS as option (option.key)}
        <button class={$layout === option.key ? "on" : ""} onclick={() => layout.set(option.key)}>
          {option.label}
        </button>
      {/each}
    </div>
    <button class="btn" onclick={() => navigate("/settings")}>Settings</button>
  </div>

  <div class="mvgrid {gridClass}">
    {#each shown as tile (tile.slot)}
      <MultiviewTile
        {tile}
        audio={audio === tile.slot}
        error={$tileErrors[tile.slot] ?? null}
        armed={armed === tile.slot}
        retryKey={retryKeys[tile.slot] ?? 0}
        onError={setError}
        onPick={openPick}
        onSwap={swap}
        onAudio={(slot) => audioSlot.set(slot)}
        onRemove={remove}
        onActivate={activate}
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
      <div style="padding: 8px 10px">
        <div class="search" style="margin: 0">
          <span>⌕</span>
          <input placeholder="Search channels…" bind:value={pickQuery} />
        </div>
      </div>
      <div class="bl">
        {#each pickMatches as channel (`${channel.portal}:${channel.channelId}`)}
          <button class="r" onclick={() => choose(channel)}>
            <Logo name={channel.name} logo={channel.logo} size={40} />
            <div>
              <div>{channel.name}</div>
              <div style="font-size: 11px; color: var(--dim)">
                CH {channel.number ?? "—"}{channel.blocks.length
                  ? ` · ${channel.blocks.join(", ")}`
                  : ""}
              </div>
            </div>
          </button>
        {:else}
          <div class="notice" style="margin: 8px">No channels.</div>
        {/each}
      </div>
      <div class="bf"><button class="btn" onclick={() => (pickSlot = null)}>Cancel</button></div>
    </div>
  </div>
{/if}
