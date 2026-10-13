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
  import { channelKey, searchChannels } from "../lib/pickerLogic";
  import type { PlaybackError } from "../lib/playerLogic";
  import { navigate } from "../lib/router";
  import type { Channel } from "../lib/types";

  let pickSlot = $state<number | null>(null);
  let armed = $state<number | null>(null);
  let pickQuery = $state("");
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

  const pickMatches = $derived(searchChannels(channels, pickQuery));

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
      <div style="padding: 8px 10px">
        <div class="search" style="margin: 0">
          <span>⌕</span>
          <input placeholder="Search channels…" bind:value={pickQuery} />
        </div>
      </div>
      <div class="bl">
        {#each pickMatches as channel (channelKey(channel))}
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
