<script lang="ts">
  import { onMount, untrack } from "svelte";
  import Logo from "../components/Logo.svelte";
  import { epg, loadEpg } from "../lib/epg";
  import { timeRange } from "../lib/format";
  import { lineup, loadLineup } from "../lib/lineup";
  import { attachStream, type StreamHandle } from "../lib/stream";
  import { channelsInBlock, channelKey, launchBlockFor } from "../lib/pickerLogic";
  import {
    epgRefreshAction,
    programmeProgress,
    resolveNowNext,
    zapTarget,
    type PlaybackError,
  } from "../lib/playerLogic";
  import { navigate, route } from "../lib/router";
  import type { Channel } from "../lib/types";

  let videoEl: HTMLVideoElement | undefined = $state();
  let stageEl: HTMLDivElement | undefined = $state();
  let handle: StreamHandle | null = null;
  let error = $state<PlaybackError | null>(null);
  let muted = $state(true);
  let retryKey = $state(0);
  let now = $state(new Date());
  let lastComputed = $state(new Date());
  let isFullscreen = $state(false);

  const params = $derived({
    portal: $route.query.get("portal") ?? "",
    id: $route.query.get("id") ?? "",
    block: $route.query.get("block") ?? "",
  });

  const channels = $derived($lineup?.channels ?? []);
  const channel = $derived(
    channels.find((item) => item.portal === params.portal && item.channelId === params.id) ?? null,
  );
  const launchBlock = $derived(channel ? params.block || launchBlockFor(channel, null) : "");
  const zapChannels = $derived(channel ? channelsInBlock(channels, launchBlock) : []);
  const stored = $derived(channel?.epgId ? ($epg[channel.epgId] ?? null) : null);
  const resolved = $derived(resolveNowNext(stored, now));
  const progress = $derived(programmeProgress(resolved?.now ?? null, now));

  $effect(() => {
    const current = channel;
    const retry = retryKey;
    void retry;
    if (!current || !videoEl) return;
    error = null;
    handle?.destroy();
    handle = null;
    const media = videoEl;
    const startMuted = untrack(() => muted);
    media.muted = startMuted;
    handle = attachStream({
      tsUrl: current.url,
      portal: current.portal,
      channelId: current.channelId,
      media,
      muted: startMuted,
      onError: (playbackError) => {
        error = playbackError;
      },
      onPlaying: () => {
        error = null;
      },
    });
    return () => {
      handle?.destroy();
      handle = null;
    };
  });

  $effect(() => {
    if (videoEl) videoEl.muted = muted;
  });

  $effect(() => {
    const el = stageEl;
    if (!el) return;
    const unmute = () => (muted = false);
    el.addEventListener("pointerdown", unmute);
    return () => el.removeEventListener("pointerdown", unmute);
  });

  function goto(target: Channel) {
    navigate(
      `/watch?portal=${encodeURIComponent(target.portal)}&id=${encodeURIComponent(
        target.channelId,
      )}&block=${encodeURIComponent(launchBlock)}`,
    );
  }

  function zap(delta: number) {
    if (!channel) return;
    const target = zapTarget(channels, launchBlock, channel, delta);
    if (target) goto(target);
  }

  function retry() {
    retryKey += 1;
    error = null;
  }

  function waitForTuner() {
    retry();
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
      return;
    }
    // Fullscreen the video element itself: fullscreening a container that holds
    // an MSE video stalls playback on some Android Chrome versions.
    const request = videoEl?.requestFullscreen();
    if (request && typeof request.catch === "function") request.catch(() => undefined);
  }

  function onFullscreenChange() {
    isFullscreen = document.fullscreenElement != null;
    if (videoEl && videoEl.paused) {
      const play = videoEl.play();
      if (play && typeof play.catch === "function") play.catch(() => undefined);
    }
  }

  function onKey(event: KeyboardEvent) {
    if (event.target instanceof HTMLElement && event.target.matches("input,textarea")) return;
    if (event.key === "ArrowUp") {
      event.preventDefault();
      zap(1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      zap(-1);
    }
  }

  function onVisibility() {
    if (document.visibilityState === "visible") {
      void loadEpg(true);
      now = new Date();
      lastComputed = new Date();
    }
  }

  onMount(() => {
    void loadLineup();
    void loadEpg();
    const timer = window.setInterval(() => {
      const current = channel;
      const stop = current?.epgId ? ($epg[current.epgId]?.now?.stop ?? null) : null;
      const action = epgRefreshAction(new Date(), lastComputed, stop);
      if (action === "REFETCH") void loadEpg(true);
      if (action !== "NONE") {
        lastComputed = new Date();
        now = new Date();
      }
    }, 30000);
    window.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
    };
  });

  const errorIcon = $derived(
    error?.kind === "all_tuners_busy" ? "⏳" : error?.kind === "redirect" ? "↪" : "⚠",
  );
  const errorTitle = $derived(
    error?.kind === "all_tuners_busy"
      ? "All tuners are busy"
      : error?.kind === "redirect"
        ? "Redirecting to portal"
        : "Stream unreachable",
  );
  const errorBody = $derived(
    error?.kind === "all_tuners_busy"
      ? "STB-Proxy has no free tuner right now — every tuner is in use."
      : error?.kind === "redirect"
        ? "The portal answered 302; the BFF follows it server-side, so the portal URL never reaches the browser. Shown for diagnostics."
        : "Couldn't reach STB-Proxy right now. Check it's running and on the same network.",
  );

  // Playback telemetry, shown when the URL carries ?debug=1.
  const debug = $derived($route.query.get("debug") === "1");
  let debugText = $state("");
  let prevFrames = 0;
  let prevDropped = 0;

  $effect(() => {
    if (!debug) return;
    const timer = window.setInterval(() => {
      const video = videoEl;
      if (!video) return;
      const buffered = video.buffered;
      const ahead = buffered.length ? buffered.end(buffered.length - 1) - video.currentTime : 0;
      const quality = video.getVideoPlaybackQuality?.();
      const speed = handle?.stats().speedKBps ?? 0;
      const deltaFrames = (quality?.totalVideoFrames ?? 0) - prevFrames;
      const deltaDropped = (quality?.droppedVideoFrames ?? 0) - prevDropped;
      prevFrames = quality?.totalVideoFrames ?? prevFrames;
      prevDropped = quality?.droppedVideoFrames ?? prevDropped;
      const rate = deltaFrames > 0 ? Math.round((deltaDropped / deltaFrames) * 100) : 0;
      debugText = `${handle?.mode() ?? "?"} · ${video.videoWidth}×${video.videoHeight} · speed ${speed.toFixed(
        0,
      )} KB/s · buffer ${ahead.toFixed(1)}s · dropped ${quality?.droppedVideoFrames ?? "?"}/${
        quality?.totalVideoFrames ?? "?"
      } (now ${rate}%) · rate ${video.playbackRate} · rs ${video.readyState}`;
    }, 1000);
    return () => window.clearInterval(timer);
  });
</script>

<div class="player">
  <div class="split">
    <div class="stage" bind:this={stageEl}>
      <video bind:this={videoEl} playsinline></video>

      {#if error}
        <div class="errbox">
          <div class="inner">
            <div class="erricon">{errorIcon}</div>
            <h2>{errorTitle}</h2>
            <p>{errorBody}</p>
            {#if error.kind === "redirect" && error.target}
              <div class="url">{error.target}</div>
            {/if}
            <div class="btns">
              {#if error.kind !== "redirect"}
                <button class="btn primary" onclick={retry}>Retry</button>
              {/if}
              {#if error.kind === "all_tuners_busy"}
                <button class="btn" onclick={waitForTuner}>Wait for a free tuner</button>
              {/if}
              {#if error.kind === "unreachable"}
                <button class="btn" onclick={() => navigate("/settings")}>Open Settings</button>
              {/if}
              <button class="btn" onclick={() => zap(1)}>Try next channel ›</button>
            </div>
          </div>
        </div>
      {:else}
        <div class="live"><span class="dot"></span>LIVE{channel ? ` · ${launchBlock}` : ""}</div>
        <button class="chev l" title="Channel down" onclick={() => zap(-1)}>‹</button>
        <button class="chev r" title="Channel up" onclick={() => zap(1)}>›</button>
      {/if}

      <div class="chiprow">
        <button class="iconbtn" title="Channels" onclick={() => navigate("/")}>☰</button>
        <button class="iconbtn" title={muted ? "Unmute" : "Mute"} onclick={() => (muted = !muted)}>
          {muted ? "🔇" : "🔊"}
        </button>
        <button
          class="iconbtn"
          title={isFullscreen ? "Exit full screen" : "Full screen"}
          onclick={toggleFullscreen}
        >
          {isFullscreen ? "⤢" : "⛶"}
        </button>
        <button class="iconbtn" title="Multiview" onclick={() => navigate("/multiview")}>▦</button>
      </div>
      {#if debug}
        <div class="debug">{debugText}</div>
      {/if}
    </div>

    <aside class="side">
      {#if channel}
        <div class="head">
          <div class="num">CH {channel.number ?? "—"} · {launchBlock}</div>
          <div class="nm">{channel.name}</div>
        </div>
        <div class="body">
          <h3>On now</h3>
          {#if resolved?.now}
            <div class="pcard">
              <div class="pt">{resolved.now.title}</div>
              <div class="pm">
                {timeRange(resolved.now)}{resolved.now.description
                  ? ` · ${resolved.now.description}`
                  : ""}
              </div>
              <div class="bar"><i style="width:{Math.round(progress * 100)}%"></i></div>
            </div>
          {:else}
            <div class="pcard"><div class="pm">No guide data.</div></div>
          {/if}

          <h3>Up next</h3>
          {#if resolved?.next}
            <div class="pcard">
              <div class="pt">{resolved.next.title}</div>
              <div class="pm">{timeRange(resolved.next)}</div>
            </div>
          {:else}
            <div class="pcard"><div class="pm">No guide data.</div></div>
          {/if}

          <h3>{launchBlock} — channel up/down</h3>
          <div class="zaplist">
            {#each zapChannels as item (channelKey(item))}
              <button
                class="z {channelKey(item) === channelKey(channel) ? 'on' : ''}"
                onclick={() => goto(item)}
              >
                <Logo name={item.name} logo={item.logo} size={38} />
                <div class="zn">
                  {item.name}
                  <small>
                    CH {item.number ?? "—"} · {item.epgId
                      ? ($epg[item.epgId]?.now?.title ?? "")
                      : ""}
                  </small>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {:else if $lineup}
        <div class="body"><div class="notice">Channel not found.</div></div>
      {:else}
        <div class="body"><div class="notice">Loading…</div></div>
      {/if}
    </aside>
  </div>
</div>
