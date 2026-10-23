<script lang="ts">
  import { onMount, untrack } from "svelte";
  import Logo from "../components/Logo.svelte";
  import { epg, loadEpg } from "../lib/epg";
  import { timeRange } from "../lib/format";
  import { lineup, loadLineup } from "../lib/lineup";
  import { attachStream, type StreamHandle } from "../lib/stream";
  import { channelKey, effectiveGroupMode, launchGroupFor } from "../lib/pickerLogic";
  import { groupMode } from "../lib/prefs";
  import {
    epgRefreshAction,
    fullscreenStrategy,
    programmeProgress,
    resolveNowNext,
    scopeZapList,
    zapIndex,
    type PlaybackError,
  } from "../lib/playerLogic";
  import { guardPopState, navigate, route } from "../lib/router";
  import { parseScope, watchUrl } from "../lib/zapScope";
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
  // "page" full screen: the player fills the window (and the page is fullscreened
  // when the browser allows it), rather than the video element going full screen.
  let fullWindow = $state(false);

  const params = $derived({
    portal: $route.query.get("portal") ?? "",
    id: $route.query.get("id") ?? "",
  });

  const channels = $derived($lineup?.channels ?? []);
  const channel = $derived(
    channels.find((item) => item.portal === params.portal && item.channelId === params.id) ?? null,
  );
  const mode = $derived(effectiveGroupMode($groupMode, $lineup?.blocks ?? []));
  const scope = $derived.by(() => {
    const parsed = parseScope($route.query);
    if (parsed.kind === "group" && !parsed.block && channel) {
      const block = launchGroupFor(mode, channel, null);
      return { kind: "group" as const, block, label: block };
    }
    return parsed;
  });
  const scopeLabel = $derived(scope.kind === "group" ? scope.label || scope.block : scope.label);
  const zapChannels = $derived(channel ? scopeZapList(channels, scope, mode, channel) : []);
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
    // A vertical swipe on the stage moves channel (up = next); a tap with no
    // movement unmutes. A control's own pointer (the mute button, chevrons, …) is
    // ignored here so the two never fight.
    const SWIPE_MIN = 44;
    let startY = 0;
    let startX = 0;
    let fromButton = false;
    let moved = false;
    const onDown = (event: PointerEvent) => {
      fromButton = !!(event.target as HTMLElement | null)?.closest("button");
      if (fromButton) return;
      startY = event.clientY;
      startX = event.clientX;
      moved = false;
    };
    const onMove = (event: PointerEvent) => {
      if (fromButton) return;
      const dy = event.clientY - startY;
      const dx = event.clientX - startX;
      if (Math.abs(dy) > 8 && Math.abs(dy) > Math.abs(dx)) moved = true;
    };
    const onUp = (event: PointerEvent) => {
      if (fromButton) {
        fromButton = false;
        return;
      }
      const dy = event.clientY - startY;
      const dx = event.clientX - startX;
      if (Math.abs(dy) >= SWIPE_MIN && Math.abs(dy) > Math.abs(dx)) {
        zap(dy < 0 ? 1 : -1);
      } else if (!moved) {
        muted = false;
      }
      moved = false;
    };
    const onCancel = () => {
      fromButton = false;
      moved = false;
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onCancel);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onCancel);
    };
  });

  function goto(target: Channel) {
    // In "window" full screen the current history entry is the full-screen one
    // (Back leaves full screen), so a zap replaces it rather than stacking.
    const url = watchUrl(target, scope);
    if (fullWindowEntry) fullWindowUrl = url;
    navigate(url, fullWindowEntry);
  }

  function zap(delta: number) {
    if (!channel || zapChannels.length === 0) return;
    const index = zapChannels.findIndex(
      (item) => item.portal === channel.portal && item.channelId === channel.channelId,
    );
    const next = zapIndex(zapChannels.length, index < 0 ? 0 : index, delta);
    if (next >= 0) goto(zapChannels[next]);
  }

  function retry() {
    retryKey += 1;
    error = null;
  }

  function waitForTuner() {
    retry();
  }

  // TV browsers (Fire TV) draw the picture on a hardware layer that doesn't follow
  // CSS size changes: the stage grows but the picture keeps its old size and place.
  // Hiding the video for a couple of frames makes the browser rebuild that layer at
  // the video's current size. Playback carries on underneath.
  let refreshTimer = 0;
  function refreshVideoLayer() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => {
      const video = videoEl;
      if (!video) return;
      video.style.visibility = "hidden";
      video.style.display = "none";
      void video.offsetHeight;
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          video.style.display = "";
          video.style.visibility = "";
        }),
      );
    }, 50);
  }

  // "window" full screen pushes a history entry, so the remote's Back (which a TV
  // app's WebView turns into history.back()) leaves full screen, not the page.
  let fullWindowEntry = false;
  // The playing channel's URL while in "window" full screen, restored on Back.
  let fullWindowUrl = "";

  // Claims Back before the router follows it: after zaps the entry below is an
  // older channel, and switching to it would restart the stream. Put the playing
  // channel's URL there instead.
  function onBack(): boolean {
    if (!fullWindowEntry) return false;
    fullWindowEntry = false;
    navigate(fullWindowUrl, true);
    setFullWindow(false);
    return true;
  }

  function setFullWindow(on: boolean) {
    fullWindow = on;
    isFullscreen = on || document.fullscreenElement != null;
    refreshVideoLayer();
  }

  function toggleFullscreen() {
    if (isFullscreen) {
      if (fullWindowEntry) {
        history.back();
        return;
      }
      setFullWindow(false);
      if (document.fullscreenElement) void document.exitFullscreen();
      return;
    }
    const coarse = window.matchMedia?.("(pointer: coarse)").matches ?? false;
    const strategy = fullscreenStrategy(navigator.userAgent, coarse);
    if (strategy === "video") {
      const request = videoEl?.requestFullscreen?.();
      if (request && typeof request.catch === "function") request.catch(() => undefined);
      return;
    }
    setFullWindow(true);
    if (strategy === "window") {
      fullWindowUrl = location.pathname + location.search;
      history.pushState(null, "", fullWindowUrl);
      fullWindowEntry = true;
      return;
    }
    const request = document.documentElement.requestFullscreen?.();
    if (request && typeof request.catch === "function") request.catch(() => undefined);
  }

  function onFullscreenChange() {
    // Leaving the browser's full screen (Back, Esc) also leaves the full-window player.
    if (document.fullscreenElement == null && fullWindow) setFullWindow(false);
    else refreshVideoLayer();
    isFullscreen = fullWindow || document.fullscreenElement != null;
    if (videoEl && videoEl.paused) {
      const play = videoEl.play();
      if (play && typeof play.catch === "function") play.catch(() => undefined);
    }
  }

  function onKey(event: KeyboardEvent) {
    if (event.target instanceof HTMLElement && event.target.matches("input,textarea")) return;
    if (event.key === "Escape" && fullWindow) {
      event.preventDefault();
      toggleFullscreen();
      return;
    }
    if (event.key === "ArrowUp" || event.key === "PageUp") {
      event.preventDefault();
      zap(1);
    } else if (event.key === "ArrowDown" || event.key === "PageDown") {
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
    window.addEventListener("resize", refreshVideoLayer);
    const releaseBack = guardPopState(onBack);
    return () => {
      releaseBack();
      window.clearTimeout(refreshTimer);
      window.removeEventListener("resize", refreshVideoLayer);
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
      } (now ${rate}%) · rate ${video.playbackRate} · rs ${video.readyState} · window ${innerWidth}×${
        innerHeight
      } · box ${video.clientWidth}×${video.clientHeight} · fs ${
        document.fullscreenElement?.tagName.toLowerCase() ?? "off"
      }${fullWindow ? (fullWindowEntry ? " +window" : " +page") : ""}${document.documentElement.classList.contains("tv") ? " · tv" : ""}`;
    }, 1000);
    return () => window.clearInterval(timer);
  });
</script>

<div class="player" class:full={fullWindow}>
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
        <div class="live"><span class="dot"></span>LIVE{channel ? ` · ${scopeLabel}` : ""}</div>
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
          <div class="num">CH {channel.number ?? "—"} · {scopeLabel}</div>
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

          <h3>{scopeLabel} — channel up/down</h3>
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
