<script lang="ts">
  import { untrack } from "svelte";
  import { attachStream, type StreamHandle } from "../lib/stream";
  import { tileStatus, type MultiviewTile } from "../lib/multiviewLogic";
  import type { PlaybackError } from "../lib/playerLogic";
  import Logo from "./Logo.svelte";

  let {
    tile,
    audio,
    error,
    armed = false,
    focused = false,
    retryKey = 0,
    onError,
    onPick,
    onSwap,
    onAudio,
    onRemove,
    onTileClick,
    onRetry,
  }: {
    tile: MultiviewTile;
    audio: boolean;
    error: PlaybackError | null;
    armed?: boolean;
    focused?: boolean;
    retryKey?: number;
    onError: (slot: number, error: PlaybackError | null) => void;
    onPick: (slot: number) => void;
    onSwap: (slot: number) => void;
    onAudio: (slot: number) => void;
    onRemove: (slot: number) => void;
    onTileClick: (slot: number) => void;
    onRetry: (slot: number) => void;
  } = $props();

  let videoEl: HTMLVideoElement | undefined = $state();
  let handle: StreamHandle | null = null;

  const status = $derived(tileStatus(tile, error));

  // A control's click must not reach the tile's own click (which would swap/focus).
  const act = (handler: (slot: number) => void) => (event: MouseEvent) => {
    event.stopPropagation();
    handler(tile.slot);
  };

  $effect(() => {
    const channel = tile.channel;
    const retry = retryKey;
    void retry;
    if (!channel || !videoEl) return;
    handle?.destroy();
    handle = null;
    onError(tile.slot, null);
    const media = videoEl;
    const startMuted = untrack(() => !audio);
    media.muted = startMuted;
    handle = attachStream({
      tsUrl: channel.url,
      portal: channel.portal,
      channelId: channel.channelId,
      media,
      muted: startMuted,
      onError: (playbackError) => onError(tile.slot, playbackError),
      onPlaying: () => onError(tile.slot, null),
    });
    if (handle == null) onError(tile.slot, { kind: "unreachable" });
    return () => {
      handle?.destroy();
      handle = null;
    };
  });

  $effect(() => {
    if (videoEl) videoEl.muted = !audio;
  });
</script>

{#if tile.channel}
  <div
    class="mvtile {audio ? 'audio' : ''} {armed ? 'swapping' : ''} {focused
      ? 'focused'
      : ''} tile{tile.slot}"
    role="button"
    tabindex="0"
    onclick={() => onTileClick(tile.slot)}
    onkeydown={(event) => {
      if (event.key === "Enter" || event.key === " ") onTileClick(tile.slot);
    }}
  >
    <video bind:this={videoEl} playsinline></video>

    <div class="tagbadge">
      <Logo name={tile.channel.name} logo={tile.channel.logo} size={22} />
      {tile.channel.name}
    </div>
    {#if audio}<div class="audiobadge">🔊 AUDIO</div>{/if}

    {#if status.kind === "tuner_busy"}
      <div class="statemsg">
        <div class="inner">
          <div>⏳</div>
          <h4>All tuners busy</h4>
          <p>No free tuner for this tile — STB-Proxy is at its limit.</p>
          <div class="btns">
            <button class="btn primary" onclick={act(onRetry)}>Retry</button>
            <button class="btn" onclick={act(onRemove)}>Remove</button>
          </div>
        </div>
      </div>
    {:else if status.kind === "failed"}
      <div class="statemsg">
        <div class="inner">
          <div>⚠</div>
          <h4>Stream unreachable</h4>
          <p>Couldn't reach {tile.channel.name} on the proxy.</p>
          <div class="btns">
            <button class="btn primary" onclick={act(onRetry)}>Retry</button>
            <button class="btn" onclick={act(onRemove)}>Remove</button>
          </div>
        </div>
      </div>
    {/if}

    <div class="tilechip">
      <button class="tbtn" onclick={act(onPick)}>Pick</button>
      <button class="tbtn" onclick={act(onSwap)}>Swap</button>
      <button class="tbtn {audio ? 'rec' : ''}" title="Audio here" onclick={act(onAudio)}>🔊</button
      >
      <button class="tbtn" onclick={act(onRemove)}>✕</button>
    </div>
  </div>
{:else}
  <button class="mvtile empty tile{tile.slot}" onclick={() => onPick(tile.slot)}>
    ＋ Add channel
  </button>
{/if}
