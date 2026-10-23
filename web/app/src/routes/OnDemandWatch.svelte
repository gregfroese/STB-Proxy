<script lang="ts">
  // The On Demand player (ticket 12; settled in On Demand issue 11): A's transport-bar
  // controls with B's end card, over an On Demand session's HLS. The title page opens the
  // session and hands it over (`playHandoff`); after a reload the player opens its own from
  // the address. The decisions live in lib/onDemandPlayerLogic.ts; this wires them up.
  import { onMount, tick } from "svelte";
  import { get } from "svelte/store";
  import { createFullscreen, type FullscreenController } from "../lib/fullscreen";
  import { attachOnDemand, type HlsHandle } from "../lib/hls";
  import {
    endSession,
    loadDetail,
    loadSeason,
    onDemandOff,
    playHandoff,
    probeSession,
    reportProgress,
    startSession,
  } from "../lib/onDemand";
  import { episodeRow, playErrorText, watchFromQuery, watchPath } from "../lib/onDemandDetailLogic";
  import { formatTime, isOnDemandOff, titlePath } from "../lib/onDemandLogic";
  import {
    ASPECT_LABELS,
    autoplaysAfter,
    controlsShown,
    createProgressReporter,
    doneTitle,
    endCardDue,
    endCardFor,
    nextAspect,
    nextCardText,
    nextEpisode,
    overlayCopy,
    playFailure,
    playerHeading,
    playerKey,
    seasonAfter,
    secondsLeft,
    STILL_WATCHING_AFTER,
    streamFailure,
    type AspectMode,
    type EndCard,
    type KeyContext,
    type PlayerKeyAction,
    type PlayerOverlay,
  } from "../lib/onDemandPlayerLogic";
  import { readAspect, saveAspect } from "../lib/prefs";
  import { navigate, route } from "../lib/router";
  import type {
    OnDemandDetail,
    OnDemandEpisode,
    OnDemandKey,
    OnDemandSeason,
    OnDemandSession,
  } from "../lib/types";

  const tv = document.documentElement.classList.contains("tv");

  const initial = watchFromQuery(get(route).query);
  const offered = get(playHandoff);
  // Taken once: Back and forward again must not reuse a session that has been released.
  playHandoff.set(null);
  const handoff =
    offered && initial && JSON.stringify(offered.start) === JSON.stringify(initial)
      ? offered
      : null;
  // Pushed from the title page, so Back returns there with history.back().
  const fromTitle = handoff != null;

  let videoEl: HTMLVideoElement | undefined = $state();
  let barEl: HTMLDivElement | undefined = $state();
  let playBtn: HTMLButtonElement | undefined = $state();
  let cardLeft: HTMLButtonElement | undefined = $state();
  let cardBack: HTMLButtonElement | undefined = $state();
  let modalFocus: HTMLButtonElement | undefined = $state();

  // What is playing.
  let key = $state<OnDemandKey | null>(initial?.key ?? null);
  let detail = $state<OnDemandDetail | null>(null);
  let season = $state<OnDemandSeason | null>(null);
  let episode = $state<OnDemandEpisode | null>(null);
  let next = $state<{ episode: OnDemandEpisode; season: OnDemandSeason | null } | null>(null);

  // The session and the stream.
  let session: OnDemandSession | null = null;
  let handle: HlsHandle | null = null;
  let openSeq = 0;
  let destroyed = false;
  let left = false;
  // Whether playback has reached its start position (progress is reported only after).
  let started = false;
  let userPaused = false;

  let opening = $state(true);
  let waiting = $state(false);
  let paused = $state(false);
  let position = $state(initial?.startSec ?? 0);
  let videoDuration = $state(0);
  let sessionDuration = $state<number | null>(null);
  const duration = $derived(sessionDuration ?? videoDuration);
  let muted = $state(false);
  let aspect = $state<AspectMode>("auto");

  let overlay = $state<PlayerOverlay | null>(null);
  let overlayMessage = $state<string | null>(null);
  let toast = $state<string | null>(null);
  let toastUntil = 0;
  let card = $state<EndCard | null>(null);
  let autoplays = 0;

  let nowMs = $state(Date.now());
  let lastInput = $state(Date.now());
  let dragPos = $state<number | null>(null);
  let flash = $state<{ text: string; side: "l" | "r" | "c" } | null>(null);
  let flashUntil = 0;
  let isFullscreen = $state(false);
  let fullWindow = $state(false);
  let fullscreen: FullscreenController | null = null;

  const shown = $derived(dragPos ?? position);
  const controlsUp = $derived(
    !card &&
      !overlay &&
      controlsShown({
        playing: !paused,
        busy: opening || waiting,
        dragging: dragPos != null,
        sinceInputMs: nowMs - lastInput,
      }),
  );
  const heading = $derived(
    detail
      ? playerHeading(detail, episode, season)
      : { title: handoff?.title ?? "On Demand", sub: "" },
  );
  const copy = $derived(overlay ? overlayCopy(overlay, position, overlayMessage) : null);
  const nextText = $derived(next ? nextCardText(next.episode, next.season) : null);
  const left15 = $derived(card ? secondsLeft(card, nowMs) : 0);
  const fraction = $derived(duration > 0 ? Math.min(1, shown / duration) : 0);

  /** Aspect is remembered per Movie, or per Series for its Episodes. */
  function aspectItem(k: OnDemandKey): string {
    return `${k.portal}/${"id" in k ? k.id : k.seriesId}`;
  }

  const progress = createProgressReporter({
    sample: () =>
      started && key
        ? { positionSec: position, durationSec: duration > 0 ? duration : null }
        : null,
    send: (sample, keepalive) => {
      if (key) void reportProgress(key, sample, keepalive).catch(() => {});
    },
  });

  // ---- the title, the Season and the next Episode

  let infoSeq = 0;
  async function loadInfo(k: OnDemandKey) {
    const seq = ++infoSeq;
    try {
      const found = await loadDetail(k.portal, "id" in k ? k.id : k.seriesId);
      if (seq !== infoSeq) return;
      detail = found;
      if ("id" in k) return;
      const current = found.seasons?.find((item) => item.id === k.seasonId) ?? null;
      const episodes = await loadSeason(k.portal, k.seriesId, k.seasonId);
      if (seq !== infoSeq) return;
      season = current;
      episode = episodes.find((item) => item.id === k.episodeId) ?? null;
      const following = nextEpisode(episodes, k.episodeId);
      if (following) {
        next = { episode: following, season: current };
        return;
      }
      const after = seasonAfter(found.seasons ?? [], k.seasonId);
      if (!after) return;
      const first = (await loadSeason(k.portal, k.seriesId, after.id))[0];
      if (seq === infoSeq && first) next = { episode: first, season: after };
    } catch {
      // The heading falls back to the hand-off's title, and there's no Next Episode.
    }
  }

  // ---- sessions

  function showToast(text: string | null) {
    toast = text;
    toastUntil = Date.now() + 4000;
  }

  async function open(k: OnDemandKey, startSec: number, replaces?: string, idleRestart = false) {
    const seq = ++openSeq;
    handle?.destroy();
    handle = null;
    session = null;
    started = false;
    opening = true;
    overlay = null;
    overlayMessage = null;
    card = null;
    position = startSec;
    try {
      const fresh = await startSession(k, replaces);
      if (seq !== openSeq || destroyed) {
        void endSession(fresh.session).catch(() => {});
        return;
      }
      attach(fresh, startSec);
    } catch (error) {
      if (seq !== openSeq || destroyed) return;
      opening = false;
      if (isOnDemandOff(error)) return;
      const failure = playFailure(error, idleRestart);
      overlay = failure.overlay;
      overlayMessage = playErrorText(error);
      showToast(failure.toast);
    }
  }

  function attach(fresh: OnDemandSession, startSec: number) {
    const media = videoEl;
    if (!media) return;
    session = fresh;
    sessionDuration = fresh.durationSec;
    started = false;
    position = startSec;
    opening = true;
    userPaused = false;
    media.muted = muted;
    handle = attachOnDemand({
      url: fresh.url,
      media,
      startSec,
      onFatal: () => void failed(fresh),
      onMutedAutoplay: () => (muted = true),
    });
  }

  /** The stream stopped: ask the session why (ADR 0005) and restart, or cover the picture. */
  async function failed(dead: OnDemandSession) {
    if (session !== dead) return;
    handle?.destroy();
    handle = null;
    const probe = await probeSession(dead.url);
    if (session !== dead || destroyed) return;
    const outcome = streamFailure(probe.status, probe.body);
    if (outcome.kind === "off") {
      session = null;
      onDemandOff();
      return;
    }
    if (outcome.kind === "restart" && key) {
      void open(key, position, dead.session, true);
      return;
    }
    progress.now();
    session = null;
    opening = false;
    waiting = false;
    if (outcome.kind === "overlay") {
      overlay = outcome.overlay;
      overlayMessage = null;
      // A stream that failed for another reason may still hold its slot.
      if (outcome.overlay === "error") void endSession(dead.session).catch(() => {});
    }
  }

  /** Resume (a fresh session, no `replaces`: the old one is gone) or Try again. */
  function resume() {
    if (key) void open(key, position);
  }

  /** The next Episode, handed over with `replaces` (⏭, the countdown, Play now, Continue). */
  function handover(how: "autoplay" | "manual") {
    if (!next || !detail || !key) return;
    progress.now();
    const target = next;
    const old = session?.session;
    const start = episodeRow(detail, target.episode, null).start;
    autoplays = autoplaysAfter(autoplays, how);
    key = start.key;
    episode = target.episode;
    season = target.season;
    next = null;
    const url = watchPath(start);
    if (fullscreen?.inWindowEntry()) fullscreen.setWindowUrl(url);
    navigate(url, true);
    void open(start.key, start.startSec, old);
    void loadInfo(start.key);
  }

  /** Back to the title page (cleanup — progress and DELETE — runs on destroy). */
  function leave() {
    if (left) return;
    left = true;
    const pushed = fullscreen?.release() ?? 0;
    if (fromTitle && history.length > 1) {
      history.go(-(1 + pushed));
      return;
    }
    const k = key ?? initial?.key;
    if (k) navigate(titlePath({ portal: k.portal, id: "id" in k ? k.id : k.seriesId }), true);
    else navigate("/ondemand", true);
  }

  /** On the way out (Back, a closed tab): the last report, and the slot released now. */
  function release() {
    progress.now(true);
    const current = session;
    session = null;
    if (current) void endSession(current.session, true).catch(() => {});
  }

  // ---- playback

  function playMedia() {
    const play = videoEl?.play();
    if (play && typeof play.catch === "function") play.catch(() => undefined);
  }

  function togglePlay() {
    const media = videoEl;
    if (!media || card || overlay || !session) return;
    if (media.paused) {
      userPaused = false;
      playMedia();
      showFlash("▶", "c");
    } else {
      userPaused = true;
      media.pause();
      showFlash("❚❚", "c");
    }
  }

  function seekTo(target: number) {
    const media = videoEl;
    if (!media || overlay || !session) return;
    const end = duration > 0 ? Math.max(0, duration - 1) : target;
    const at = Math.max(0, Math.min(end, target));
    const fromCard = card != null;
    card = null;
    media.currentTime = at;
    position = at;
    if (fromCard) {
      fullscreen?.refreshVideoLayer();
      playMedia();
    }
  }

  function seekBy(by: number) {
    if (card && by >= 0) return;
    seekTo(position + by);
    showFlash(`${by > 0 ? "+" : "−"}${Math.abs(by)} s`, by > 0 ? "r" : "l");
  }

  function playAgain() {
    seekTo(0);
  }

  function showFlash(text: string, side: "l" | "r" | "c") {
    flash = { text, side };
    flashUntil = Date.now() + 600;
  }

  function cycleAspect() {
    aspect = nextAspect(aspect);
    if (key) saveAspect(aspectItem(key), aspect);
    fullscreen?.refreshVideoLayer();
  }

  async function endCard() {
    progress.now();
    card = endCardFor({ hasNext: next != null, autoplays, now: Date.now() });
    fullscreen?.refreshVideoLayer();
    await tick();
    // Play now on the next-Episode card; Back to details on ✓ Watched.
    const target =
      card?.kind === "still" ? modalFocus : card?.kind === "next" ? cardLeft : cardBack;
    target?.focus();
  }

  // ---- video events

  function onPlaying() {
    opening = false;
    waiting = false;
    paused = false;
    // hls.js starts at `startPosition` and the native path seeks before play(), so the
    // first frame is already at the start.
    started = true;
  }

  function onTimeUpdate() {
    // Until playback reaches its start, the position stays the start (for Resume from).
    if (videoEl && started && dragPos == null && !videoEl.seeking) position = videoEl.currentTime;
  }

  function onDuration() {
    const value = videoEl?.duration ?? 0;
    videoDuration = Number.isFinite(value) ? value : 0;
  }

  function onPause() {
    paused = true;
    if (videoEl && !videoEl.ended) progress.now();
  }

  function onEnded() {
    paused = true;
    position = duration || position;
    void endCard();
  }

  // ---- input

  function input() {
    lastInput = Date.now();
    autoplays = autoplaysAfter(autoplays, "input");
  }

  function hideControls() {
    lastInput = 0;
  }

  async function focusAfter(target: () => HTMLElement | undefined) {
    if (!tv) return;
    await tick();
    target()?.focus();
  }

  function run(action: PlayerKeyAction, wasUp: boolean) {
    switch (action.type) {
      case "toggle":
        togglePlay();
        break;
      case "seek":
        seekBy(action.by);
        if (!wasUp) void focusAfter(() => barEl);
        break;
      case "fullscreen":
        fullscreen?.toggle();
        break;
      case "mute":
        muted = !muted;
        break;
      case "next":
        if (next) handover("manual");
        break;
      case "escape":
        if (isFullscreen) fullscreen?.toggle();
        else leave();
        break;
      case "back":
        if (controlsUp && !paused) hideControls();
        else if (fullWindow) fullscreen?.toggle();
        else leave();
        break;
      case "showControls":
        void focusAfter(() => playBtn);
        break;
    }
  }

  let holdStart = 0;
  let lastStep = 0;
  function onKey(event: KeyboardEvent) {
    if (event.target instanceof HTMLElement && event.target.matches("input,textarea")) return;
    const wasUp = controlsUp;
    input();
    const now = Date.now();
    if (!event.repeat) holdStart = now;
    const active = document.activeElement;
    let cardCtx: KeyContext["card"] = null;
    if (overlay || card?.kind === "still") cardCtx = "modal";
    else if (card)
      cardCtx = tv && active !== cardLeft && active !== document.body ? "modal" : "end";
    const action = playerKey(event, {
      tv,
      controlsVisible: wasUp,
      onBar: active === barEl,
      card: cardCtx,
      heldMs: event.repeat ? now - holdStart : 0,
    });
    if (!action) return;
    event.preventDefault();
    if (action.type === "seek") {
      // About five steps a second while a key is held.
      if (event.repeat && now - lastStep < 180) return;
      lastStep = now;
    }
    run(action, wasUp);
  }

  // A tap on the picture: a mouse click pauses; a touch toggles the controls, and a
  // double-tap on a side seeks ∓10 s.
  let lastTap = 0;
  function onPictureUp(event: PointerEvent) {
    const wasUp = controlsUp;
    input();
    if (event.pointerType === "mouse") {
      togglePlay();
      return;
    }
    const now = Date.now();
    if (now - lastTap < 300) {
      lastTap = 0;
      const target = event.currentTarget as HTMLElement;
      const box = target.getBoundingClientRect();
      seekBy(event.clientX - box.left < box.width / 2 ? -10 : 10);
      return;
    }
    lastTap = now;
    if (wasUp) hideControls();
  }

  function onStageMove(event: PointerEvent) {
    if (event.pointerType === "mouse") lastInput = Date.now();
  }

  function barTime(event: PointerEvent): number {
    const box = barEl?.getBoundingClientRect();
    if (!box || box.width === 0) return 0;
    return Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * duration;
  }

  function onBarDown(event: PointerEvent) {
    if (!duration || !session) return;
    input();
    barEl?.setPointerCapture?.(event.pointerId);
    dragPos = barTime(event);
  }

  function onBarMove(event: PointerEvent) {
    if (dragPos == null) return;
    lastInput = Date.now();
    dragPos = barTime(event);
  }

  function onBarUp() {
    if (dragPos == null) return;
    const target = dragPos;
    dragPos = null;
    seekTo(target);
  }

  // ---- lifecycle

  function onVisibility() {
    if (document.visibilityState === "hidden") progress.now(true);
  }

  onMount(() => {
    window.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", release);
    const controller = createFullscreen({
      video: () => videoEl,
      onChange: (state) => {
        isFullscreen = state.isFullscreen;
        fullWindow = state.fullWindow;
      },
      resumeAfterChange: () => !userPaused && !card && !overlay && session != null,
    });
    fullscreen = controller;

    let lastTick = Date.now();
    const timer = window.setInterval(() => {
      const now = Date.now();
      const dt = (now - lastTick) / 1000;
      lastTick = now;
      nowMs = now;
      if (started && session && !paused && !waiting && !overlay && !card) progress.played(dt);
      if (card) {
        const due = endCardDue(card, now);
        if (due === "autoplay") handover("autoplay");
        else if (due === "back") leave();
      }
      if (toast && now > toastUntil) toast = null;
      if (flash && now > flashUntil) flash = null;
    }, 250);

    if (initial) {
      aspect = readAspect(aspectItem(initial.key));
      void loadInfo(initial.key);
      if (handoff) attach(handoff.session, initial.startSec);
      else void open(initial.key, initial.startSec);
      // TV: the controls start up, with focus on ▶/❚❚ as when they come back.
      void focusAfter(() => playBtn);
    } else {
      opening = false;
    }

    return () => {
      destroyed = true;
      release();
      handle?.destroy();
      handle = null;
      controller.destroy();
      fullscreen = null;
      window.clearInterval(timer);
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", release);
    };
  });

  $effect(() => {
    if (videoEl) videoEl.muted = muted;
  });

  $effect(() => {
    if (overlay) void focusAfter(() => modalFocus);
  });
</script>

<div class="player odp-player" class:full={fullWindow}>
  <div
    class="stage odp-stage"
    class:carded={card != null && card.kind !== "still"}
    class:bare={!controlsUp}
    role="presentation"
    onpointermove={onStageMove}
  >
    <video
      bind:this={videoEl}
      class={aspect === "16:9"
        ? "a169"
        : aspect === "4:3"
          ? "a43"
          : aspect === "zoom"
            ? "zoom"
            : ""}
      playsinline
      onplaying={onPlaying}
      onwaiting={() => (waiting = true)}
      onseeking={() => (waiting = true)}
      onseeked={() => (waiting = false)}
      oncanplay={() => (waiting = false)}
      ontimeupdate={onTimeUpdate}
      ondurationchange={onDuration}
      onloadedmetadata={onDuration}
      onpause={onPause}
      onplay={() => (paused = false)}
      onended={onEnded}
      onvolumechange={() => (muted = videoEl?.muted ?? muted)}
    ></video>

    {#if initial}
      <div class="odp-tap" role="presentation" onpointerup={onPictureUp}></div>

      <div class="odp-controls" class:hidden={!controlsUp}>
        <div class="odp-top">
          {#if !tv}
            <button class="odp-btn" title="Back" onclick={leave}>‹</button>
          {/if}
          <div class="odp-head">
            <div class="odp-title">{heading.title}</div>
            {#if heading.sub}<div class="odp-sub">{heading.sub}</div>{/if}
          </div>
        </div>

        <div class="odp-center">
          <button class="odp-btn big" title="Back 10 s" onclick={() => seekBy(-10)}>⟲ 10</button>
          <button
            class="odp-btn big"
            bind:this={playBtn}
            title={paused ? "Play" : "Pause"}
            onclick={togglePlay}
          >
            {paused ? "▶" : "❚❚"}
          </button>
          <button class="odp-btn big" title="Forward 10 s" onclick={() => seekBy(10)}>10 ⟳</button>
        </div>

        <div class="odp-bottom">
          <div class="odp-barrow">
            <span>{formatTime(shown)}</span>
            <div
              class="odp-bar"
              bind:this={barEl}
              role="slider"
              tabindex="0"
              aria-label="Seek"
              aria-valuemin={0}
              aria-valuemax={Math.round(duration)}
              aria-valuenow={Math.round(shown)}
              aria-valuetext={formatTime(shown)}
              onpointerdown={onBarDown}
              onpointermove={onBarMove}
              onpointerup={onBarUp}
              onpointercancel={() => (dragPos = null)}
            >
              <div class="track"></div>
              <div class="played" style="width:{fraction * 100}%"></div>
              <div class="thumb" style="left:{fraction * 100}%"></div>
              {#if dragPos != null}
                <div class="bubble" style="left:{fraction * 100}%">{formatTime(dragPos)}</div>
              {/if}
            </div>
            <span>−{formatTime(Math.max(0, duration - shown))}</span>
          </div>
          <div class="odp-btnrow">
            <button class="odp-btn odp-pp" title={paused ? "Play" : "Pause"} onclick={togglePlay}>
              {paused ? "▶" : "❚❚"}
            </button>
            {#if next}
              <button class="odp-btn" onclick={() => handover("manual")}>⏭ Next Episode</button>
            {/if}
            <span class="spacer"></span>
            {#if !tv}
              <button
                class="odp-btn"
                title={muted ? "Unmute" : "Mute"}
                onclick={() => (muted = !muted)}
              >
                {muted ? "🔇" : "🔊"}
              </button>
            {/if}
            <button class="odp-btn" onclick={cycleAspect}>Aspect: {ASPECT_LABELS[aspect]}</button>
            <button
              class="odp-btn"
              title={isFullscreen ? "Exit full screen" : "Full screen"}
              onclick={() => fullscreen?.toggle()}
            >
              {isFullscreen ? "⤢" : "⛶"}
            </button>
          </div>
        </div>
      </div>

      {#if card && card.kind !== "still"}
        <div class="odp-end">
          <div class="txt">
            {#if card.kind === "next" && next && nextText}
              <div class="k">Next Episode · in {left15} s</div>
              <div class="n">{nextText.name}</div>
              {#if nextText.facts}<div class="d">{nextText.facts}</div>{/if}
              <div class="btns">
                <button class="btn primary" bind:this={cardLeft} onclick={() => handover("manual")}>
                  ▶ Play now
                </button>
                <button class="btn" onclick={leave}>Back to Episodes</button>
              </div>
            {:else}
              <div class="k"><span class="watched">✓ Watched</span></div>
              <div class="n">{detail ? doneTitle(detail, season) : heading.title}</div>
              <div class="d">Back to details in {left15} s</div>
              <div class="btns">
                <button class="btn" bind:this={cardLeft} onclick={playAgain}>↺ Play again</button>
                <button class="btn primary" bind:this={cardBack} onclick={leave}>
                  Back to details
                </button>
              </div>
            {/if}
          </div>
        </div>
      {/if}

      {#if card?.kind === "still" && next}
        <div class="errbox odp-modal">
          <div class="inner">
            <h2>Still watching {detail?.name ?? heading.title}?</h2>
            <p>{STILL_WATCHING_AFTER} Episodes have played in a row with no input.</p>
            <div class="btns">
              <button class="btn primary" bind:this={modalFocus} onclick={() => handover("manual")}>
                ▶ Continue with {next.episode.number != null
                  ? `E${next.episode.number}`
                  : "the next Episode"}
              </button>
              <button class="btn" onclick={leave}>Back</button>
            </div>
          </div>
        </div>
      {/if}

      {#if copy}
        <div class="errbox odp-modal">
          <div class="inner">
            <h2>{copy.title}</h2>
            <p>{copy.body}</p>
            <div class="btns">
              <button class="btn primary" bind:this={modalFocus} onclick={resume}
                >{copy.primary}</button
              >
              <button class="btn" onclick={leave}>Back</button>
            </div>
          </div>
        </div>
      {/if}

      {#if (opening || waiting) && !overlay && !card}
        <div class="odp-spin" aria-label="Loading"></div>
      {/if}
      {#if flash}
        <div class="odp-flash {flash.side}">{flash.text}</div>
      {/if}
      {#if toast}
        <div class="odp-toast" role="status">{toast}</div>
      {/if}
    {:else}
      <div class="errbox">
        <div class="inner">
          <h2>Nothing to play</h2>
          <p>This address doesn't name a Movie or an Episode.</p>
          <div class="btns">
            <button class="btn primary" onclick={() => navigate("/ondemand", true)}>
              On Demand
            </button>
          </div>
        </div>
      </div>
    {/if}
  </div>

  {#if initial}
    <div class="odp-info">
      <div class="odp-title">{heading.title}</div>
      {#if heading.sub}<div class="odp-sub">{heading.sub}</div>{/if}
      {#if next && nextText}
        <button class="btn odp-wide" onclick={() => handover("manual")}>
          ⏭ Next Episode · {nextText.name}
        </button>
      {/if}
      {#if detail?.description && !episode}
        <p>{detail.description}</p>
      {/if}
    </div>
  {/if}
</div>
