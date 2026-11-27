<script lang="ts">
  // A Movie's or Series' page (ticket 11; layout from On Demand issue 09): poster and facts,
  // Play under the facts (Resume / Start over / Play again, Mark watched), then the
  // description, genres and credits. A Series adds Season chips and its Episode list.
  // Play opens the session here, so its errors show inline, then hands it to the player.
  // With Downloads on for the login, Download asks STB-Proxy to save the Movie, an Episode
  // or a whole Season in its downloads folder (nothing is kept in the browser).
  import { onDestroy, tick, untrack } from "svelte";
  import { ApiError } from "../lib/api";
  import {
    cancelDownload,
    endSession,
    loadDetail,
    loadDownloads,
    loadSeason,
    markWatched,
    playHandoff,
    requestDownload,
    startSession,
    type DownloadRequest,
  } from "../lib/onDemand";
  import {
    DOWNLOAD_POLL_MS,
    briefsByItem,
    canCancel,
    downloadButton,
    downloadErrorText,
    episodeDownloadText,
    isActive,
    itemKey,
  } from "../lib/onDemandDownloadLogic";
  import {
    credits,
    episodeRow,
    facts,
    genreTags,
    markedProgress,
    movieActions,
    openingSeason,
    playErrorText,
    playTitle,
    seasonErrorText,
    seasonLabel,
    seriesPlay,
    TITLE_GONE,
    watchPath,
    type PlayStart,
  } from "../lib/onDemandDetailLogic";
  import { isOnDemandOff, titleBack } from "../lib/onDemandLogic";
  import { navigate, route } from "../lib/router";
  import type {
    OnDemandDetail,
    OnDemandDownloadBrief,
    OnDemandEpisode,
    OnDemandKey,
  } from "../lib/types";

  const tv = document.documentElement.classList.contains("tv");

  const portal = $derived($route.query.get("portal") ?? "");
  const id = $derived($route.query.get("id") ?? "");
  const backText = $derived(titleBack($route.query));

  let detail = $state.raw<OnDemandDetail | null>(null);
  let loadError = $state<{ text: string; retry: boolean } | null>(null);
  let posterBroken = $state(false);

  let seasonId = $state<string | null>(null);
  let episodes = $state.raw<Record<string, OnDemandEpisode[]>>({});
  let seasonError = $state<string | null>(null);

  let playing = $state(false);
  let playError = $state<{ text: string; start: PlayStart; title: string } | null>(null);
  let errorEl = $state<HTMLElement | null>(null);
  let primaryEl = $state<HTMLButtonElement | null>(null);

  let marking = $state(false);
  let markError = $state<string | null>(null);

  /** Downloads learnt since the page loaded, by item key (null: cancelled), over what the
   * detail and Episode lists said. */
  let briefs = $state.raw<Map<string, OnDemandDownloadBrief | null>>(new Map());
  let asking = $state(false);
  let downloadError = $state<string | null>(null);

  let controller: AbortController | null = null;

  async function load(p: string, i: string) {
    controller?.abort();
    const mine = new AbortController();
    controller = mine;
    detail = null;
    loadError = null;
    posterBroken = false;
    seasonId = null;
    episodes = {};
    seasonError = null;
    playError = null;
    markError = null;
    briefs = new Map();
    downloadError = null;
    try {
      const loaded = await loadDetail(p, i, mine.signal);
      if (mine.signal.aborted) return;
      detail = loaded;
      if (loaded.kind === "series") {
        seasonId = openingSeason(loaded.seasons ?? [], loaded.upNext);
        if (seasonId) void fetchSeason(seasonId);
      }
      if (tv) {
        await tick();
        primaryEl?.focus();
      }
    } catch (error) {
      if (mine.signal.aborted || isOnDemandOff(error)) return;
      const missing = error instanceof ApiError && error.code === "not_found";
      loadError = missing
        ? { text: TITLE_GONE, retry: false }
        : {
            text: error instanceof ApiError ? error.message : "Couldn't load this title.",
            retry: true,
          };
    }
  }

  async function fetchSeason(season: string) {
    const series = detail;
    const signal = controller?.signal;
    if (!series || episodes[season]) return;
    seasonError = null;
    try {
      const loaded = await loadSeason(series.portal, series.id, season, signal);
      if (signal?.aborted) return;
      episodes = { ...episodes, [season]: loaded };
    } catch (error) {
      if (signal?.aborted || isOnDemandOff(error)) return;
      if (seasonId === season) {
        seasonError = seasonErrorText(error);
      }
    }
  }

  function chooseSeason(season: string) {
    seasonId = season;
    seasonError = null;
    void fetchSeason(season);
  }

  $effect(() => {
    const p = portal;
    const i = id;
    untrack(() => void load(p, i));
  });

  onDestroy(() => controller?.abort());

  function briefFor(key: OnDemandKey, fromList: OnDemandDownloadBrief | null | undefined) {
    const k = itemKey(key);
    return briefs.has(k) ? briefs.get(k) : (fromList ?? null);
  }

  function learn(entries: [string, OnDemandDownloadBrief | null][]) {
    const next = new Map(briefs);
    for (const [k, brief] of entries) next.set(k, brief);
    briefs = next;
  }

  async function askDownload(what: DownloadRequest) {
    if (asking) return;
    asking = true;
    downloadError = null;
    try {
      const items = await requestDownload(what);
      learn([...briefsByItem(items)]);
    } catch (error) {
      if (!isOnDemandOff(error)) downloadError = downloadErrorText(error);
    } finally {
      asking = false;
    }
  }

  async function cancel(key: OnDemandKey, brief: OnDemandDownloadBrief) {
    downloadError = null;
    try {
      await cancelDownload(brief.id);
      learn([[itemKey(key), null]]);
    } catch (error) {
      if (!isOnDemandOff(error)) downloadError = downloadErrorText(error);
    }
  }

  // While a download on show is queued or running, look again now and then.
  $effect(() => {
    const keys = shownKeys;
    if (!keys.some(({ brief }) => isActive(brief))) return;
    const timer = setInterval(async () => {
      try {
        const known = briefsByItem((await loadDownloads(controller?.signal)).items);
        learn(keys.map(({ key }) => [itemKey(key), known.get(itemKey(key)) ?? null]));
      } catch {
        /* try again next time */
      }
    }, DOWNLOAD_POLL_MS);
    return () => clearInterval(timer);
  });

  function back() {
    if ($route.query.has("from") && history.length > 1) history.back();
    else navigate("/ondemand");
  }

  async function play(start: PlayStart, title: string) {
    if (playing) return;
    playing = true;
    playError = null;
    try {
      const session = await startSession(start.key);
      if (controller?.signal.aborted) {
        // The viewer left while it started: don't hold the slot until it idles out.
        void endSession(session.session).catch(() => {});
        return;
      }
      playHandoff.set({ start, session, title });
      navigate(watchPath(start));
    } catch (error) {
      if (isOnDemandOff(error)) return;
      playError = { text: playErrorText(error), start, title };
      await tick();
      errorEl?.scrollIntoView?.({ block: "nearest" });
    } finally {
      playing = false;
    }
  }

  async function toggleWatched() {
    const current = detail;
    if (!current || marking) return;
    const watched = !(current.progress?.watched ?? false);
    marking = true;
    markError = null;
    try {
      await markWatched({ portal: current.portal, id: current.id }, watched);
      if (detail === current) {
        // A failed Play's Try again would start where the old buttons said; drop it.
        playError = null;
        detail = {
          ...current,
          progress: markedProgress(current.progress, watched, Math.floor(Date.now() / 1000)),
        };
      }
    } catch (error) {
      if (!isOnDemandOff(error)) markError = "Couldn't save that. Try again.";
    } finally {
      marking = false;
    }
  }

  const movie = $derived(detail?.kind === "movie" ? movieActions(detail.progress) : null);
  const firstSeason = $derived(detail?.seasons?.[0]?.id ?? null);
  const series = $derived(
    detail?.kind === "series"
      ? seriesPlay(detail, firstSeason ? (episodes[firstSeason] ?? null) : null)
      : null,
  );
  const seasons = $derived(detail?.seasons ?? []);
  const seasonNumber = $derived(seasons.find((season) => season.id === seasonId)?.number ?? null);
  const shownEpisodes = $derived(seasonId ? (episodes[seasonId] ?? null) : null);
  const rows = $derived(
    detail && shownEpisodes
      ? shownEpisodes.map((episode) => ({
          episode,
          row: episodeRow(detail!, episode, detail!.upNext),
        }))
      : [],
  );
  const movieKey = $derived(
    detail?.kind === "movie" ? { portal: detail.portal, id: detail.id } : null,
  );
  const movieDownload = $derived(movieKey ? briefFor(movieKey, detail?.download) : null);
  const episodeKey = (episode: OnDemandEpisode): OnDemandKey => ({
    portal: detail!.portal,
    seriesId: detail!.id,
    seasonId: episode.seasonId,
    episodeId: episode.id,
  });
  const episodeDownloads = $derived(
    detail && shownEpisodes
      ? new Map(shownEpisodes.map((e) => [e.id, briefFor(episodeKey(e), e.download)]))
      : new Map<string, OnDemandDownloadBrief | null | undefined>(),
  );
  /** What's on show that may have a download, for polling. */
  const shownKeys = $derived(
    movieKey
      ? [{ key: movieKey as OnDemandKey, brief: movieDownload }]
      : (shownEpisodes ?? []).map((e) => ({
          key: episodeKey(e),
          brief: episodeDownloads.get(e.id),
        })),
  );
  const seasonDownloadable = $derived(
    (shownEpisodes ?? []).some((e) => downloadButton(episodeDownloads.get(e.id)).canStart),
  );
  const factParts = $derived(detail ? facts(detail) : []);
  const genres = $derived(genreTags(detail?.genres));
  const creditRows = $derived(detail ? credits(detail) : []);
  const showPoster = $derived(detail?.poster != null && !posterBroken);

  function playSeries() {
    if (!detail || !series?.start) return;
    const next = detail.upNext;
    const first = firstSeason ? episodes[firstSeason]?.[0] : undefined;
    const episode = next
      ? { seasonNumber: next.seasonNumber, number: next.episodeNumber, name: next.name }
      : {
          seasonNumber: seasons[0]?.number ?? null,
          number: first?.number ?? null,
          name: first?.name ?? null,
        };
    void play(series.start, playTitle(detail.name, episode));
  }

  function playEpisode(episode: OnDemandEpisode, start: PlayStart) {
    if (!detail) return;
    void play(
      start,
      playTitle(detail.name, { seasonNumber, number: episode.number, name: episode.name }),
    );
  }
</script>

<div class="picker odpage">
  <div class="appbar">
    <button class="btn" onclick={back}>{backText}</button>
    <div class="brand">On Demand</div>
  </div>

  <div class="odmain">
    {#if loadError}
      <div class="odtitle-msg">
        <div class="error-banner noticerow">
          <span>{loadError.text}</span>
          {#if loadError.retry}
            <button class="btn" onclick={() => void load(portal, id)}>Try again</button>
          {/if}
        </div>
      </div>
    {:else if !detail}
      <div class="empty">Loading…</div>
    {:else}
      <div class="oddetail">
        <div class="odposter">
          <div class="poster {showPoster ? '' : 'none'}">
            {#if showPoster}
              <img src={detail.poster} alt="" onerror={() => (posterBroken = true)} />
            {:else}
              <span class="pname">{detail.name}</span>
            {/if}
          </div>
        </div>

        <div class="odinfo">
          <h1>{detail.name}</h1>
          {#if detail.originalName}<div class="orig">{detail.originalName}</div>{/if}
          {#if factParts.length > 0 || detail.ageRating || detail.rating != null}
            <div class="facts">
              {#if factParts.length > 0}<span>{factParts.join(" · ")}</span>{/if}
              {#if detail.ageRating}<span class="age">{detail.ageRating}</span>{/if}
              {#if detail.rating != null}<span class="star">★ {detail.rating}</span>{/if}
            </div>
          {/if}

          <div class="actions">
            {#if movie}
              <button
                class="btn primary"
                bind:this={primaryEl}
                disabled={playing}
                onclick={() =>
                  void play(
                    {
                      key: { portal: detail!.portal, id: detail!.id },
                      startSec: movie.primary.startSec,
                    },
                    detail!.name,
                  )}
              >
                {movie.primary.label}
              </button>
              {#if movie.startOver}
                <button
                  class="btn"
                  disabled={playing}
                  onclick={() =>
                    void play(
                      { key: { portal: detail!.portal, id: detail!.id }, startSec: 0 },
                      detail!.name,
                    )}
                >
                  Start over
                </button>
              {/if}
              <button
                class="btn {movie.mark.watched ? 'watched' : ''}"
                disabled={marking}
                aria-pressed={movie.mark.watched}
                onclick={() => void toggleWatched()}
              >
                {movie.mark.label}
              </button>
              {#if detail.canDownload && movieKey}
                {@const button = downloadButton(movieDownload)}
                <button
                  class="btn {movieDownload?.status === 'done' ? 'watched' : ''}"
                  disabled={!button.canStart || asking}
                  title={button.hint ?? undefined}
                  onclick={() => void askDownload(movieKey!)}
                >
                  {button.label}
                </button>
                {#if movieDownload && canCancel(movieDownload)}
                  <button class="btn" onclick={() => void cancel(movieKey!, movieDownload!)}>
                    Cancel download
                  </button>
                {/if}
              {/if}
            {:else if series}
              <button
                class="btn primary"
                bind:this={primaryEl}
                disabled={playing || !series.start}
                onclick={playSeries}
              >
                {series.label}
              </button>
              {#if series.sub}<span class="rsub">{series.sub}</span>{/if}
            {:else if detail.kind === "series"}
              <span class="rsub">No Episodes to play yet.</span>
            {/if}
            {#if playing}<span class="rsub">Starting…</span>{/if}
          </div>

          {#if playError}
            <div class="error-banner noticerow playerr" bind:this={errorEl}>
              <span>{playError.text}</span>
              <button class="btn" onclick={() => void play(playError!.start, playError!.title)}>
                Try again
              </button>
            </div>
          {/if}
          {#if markError}<div class="inlineerr">{markError}</div>{/if}
          {#if downloadError}<div class="inlineerr">{downloadError}</div>{/if}

          {#if detail.description}<p class="desc">{detail.description}</p>{/if}
          {#if genres.length > 0}
            <div class="genretags">
              {#each genres as genre (genre)}<span class="tag">{genre}</span>{/each}
            </div>
          {/if}
          {#if creditRows.length > 0}
            <dl class="credits">
              {#each creditRows as credit (credit.label)}
                <dt>{credit.label}</dt>
                <dd>
                  {credit.value}
                  {#if credit.more}<span class="more">{credit.more}</span>{/if}
                </dd>
              {/each}
            </dl>
          {/if}

          {#if detail.kind === "series" && seasons.length > 0}
            <div class="chips seasons">
              {#each seasons as season (season.id)}
                <button
                  class="chip {season.id === seasonId ? 'on' : ''}"
                  onclick={() => chooseSeason(season.id)}
                >
                  {seasonLabel(season)}
                </button>
              {/each}
            </div>
            {#if detail.canDownload && seasonId && shownEpisodes && shownEpisodes.length > 0}
              <div class="actions seasondl">
                <button
                  class="btn"
                  disabled={!seasonDownloadable || asking}
                  title="Save every Episode of this Season in STB-Proxy's downloads folder"
                  onclick={() =>
                    void askDownload({
                      portal: detail!.portal,
                      seriesId: detail!.id,
                      seasonId: seasonId!,
                    })}
                >
                  {seasonDownloadable ? "Download this Season" : "Season downloaded or queued"}
                </button>
              </div>
            {/if}
            {#if seasonError}
              <div class="error-banner noticerow">
                <span>{seasonError}</span>
                <button class="btn" onclick={() => seasonId && void fetchSeason(seasonId)}>
                  Try again
                </button>
              </div>
            {:else if !shownEpisodes}
              <div class="rsub">Loading Episodes…</div>
            {:else if rows.length === 0}
              <div class="rsub">No Episodes in this Season.</div>
            {:else}
              <div class="eplist">
                {#each rows as { episode, row } (episode.id)}
                  {@const dlText = episodeDownloadText(episodeDownloads.get(episode.id))}
                  {@const dl = episodeDownloads.get(episode.id)}
                  <div class="eprow">
                    <button
                      class="ep {row.upNext ? 'upnext' : ''}"
                      disabled={playing}
                      onclick={() => playEpisode(episode, row.start)}
                    >
                      <span class="n">{row.number}</span>
                      <span class="nm">{row.name}</span>
                      {#if row.upNext}<span class="badge">Up next</span>{/if}
                      {#if row.status}<span class="st {row.watched ? 'w' : ''}">{row.status}</span
                        >{/if}
                      {#if dlText}<span
                          class="st dl {dl?.status === 'done' ? 'w' : ''}"
                          title={dl?.error ?? undefined}>{dlText}</span
                        >{/if}
                      {#if row.progress != null}
                        <span class="prog" style="width: {row.progress * 100}%"></span>
                      {/if}
                    </button>
                    {#if detail.canDownload && downloadButton(dl).canStart}
                      <button
                        class="btn epdl"
                        disabled={asking}
                        title="Download this Episode"
                        aria-label="Download {row.name}"
                        onclick={() => void askDownload(episodeKey(episode))}>↓</button
                      >
                    {:else if dl && canCancel(dl)}
                      <button
                        class="btn epdl"
                        title="Cancel this download"
                        aria-label="Cancel the download of {row.name}"
                        onclick={() => void cancel(episodeKey(episode), dl)}>×</button
                      >
                    {:else if detail.canDownload}
                      <span class="epdl" aria-hidden="true"></span>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          {/if}

          <div class="src-line">From {detail.portalName}</div>
        </div>
      </div>
    {/if}
  </div>
</div>
