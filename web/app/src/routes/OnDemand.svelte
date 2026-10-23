<script lang="ts">
  // On Demand browse and search (ticket 10; layout from On Demand issue 09, variant A with
  // B's shelves): search, sort chips and status pills over a category rail. All shows
  // shelves; a category, a search or See all shows a poster grid with infinite scroll.
  import { onDestroy, onMount, tick, untrack } from "svelte";
  import { get } from "svelte/store";
  import ContinueCard from "../components/ContinueCard.svelte";
  import OnDemandShelf from "../components/OnDemandShelf.svelte";
  import PosterCard from "../components/PosterCard.svelte";
  import Rail from "../components/Rail.svelte";
  import { ApiError } from "../lib/api";
  import { loadCategories, loadContinue, loadItems } from "../lib/onDemand";
  import {
    SEARCH_DEBOUNCE_MS,
    SORTS,
    activeSort,
    allShelves,
    appendPage,
    backLabel,
    browseFromQuery,
    browsePath,
    browseView,
    debounce,
    emptyText,
    initialPaging,
    isOnDemandOff,
    itemsPath,
    nextOffset,
    searchHint,
    searchTerm,
    sentinel,
    statusPills,
    titlePath,
    type Browse,
    type ItemsQuery,
    type OnDemandSort,
  } from "../lib/onDemandLogic";
  import { navigate, route } from "../lib/router";
  import { accountLabel, session } from "../lib/session";
  import type { OnDemandCategories, OnDemandItem } from "../lib/types";

  const tv = document.documentElement.classList.contains("tv");

  const browse = $derived(browseFromQuery($route.query));
  const view = $derived(browseView(browse));
  const term = $derived(searchTerm(browse.q));
  const searching = $derived(term !== null);

  let typed = $state(browseFromQuery(get(route).query).q);
  let cats = $state.raw<OnDemandCategories | null>(null);
  let catsError = $state<string | null>(null);
  let continueItems = $state.raw<OnDemandItem[]>([]);
  /** The All count: the total of an unfiltered listing, once one has loaded. */
  let allTotal = $state<number | null>(null);
  let mainEl = $state<HTMLElement | null>(null);
  const scrollRoot = $derived(tv ? null : mainEl);

  const pageController = new AbortController();

  function go(next: Browse) {
    navigate(browsePath(next), true);
  }

  async function fetchCategories() {
    catsError = null;
    try {
      cats = await loadCategories(pageController.signal);
    } catch (error) {
      if (pageController.signal.aborted || isOnDemandOff(error)) return;
      catsError = error instanceof ApiError ? error.message : "Couldn't load On Demand.";
    }
  }

  async function fetchContinue() {
    try {
      continueItems = await loadContinue(pageController.signal);
    } catch {
      continueItems = [];
    }
  }

  onMount(() => {
    void fetchCategories();
    void fetchContinue();
  });

  const applySearch = debounce((value: string) => {
    const current = browseFromQuery(get(route).query);
    if (searchTerm(value) === searchTerm(current.q)) return;
    go({ ...current, q: searchTerm(value) ?? "", allGrid: false });
  }, SEARCH_DEBOUNCE_MS);

  function selectCategory(key: string) {
    applySearch.cancel();
    typed = "";
    go({ category: key, q: "", sort: browse.sort, allGrid: false });
    mainEl?.scrollTo?.({ top: 0 });
  }

  function chooseSort(sort: OnDemandSort) {
    go({ ...browse, sort, allGrid: browse.allGrid || view === "shelves" });
  }

  function pick(item: OnDemandItem) {
    navigate(titlePath(item, backLabel(browse, categoryName)));
  }

  const categoryName = $derived(
    browse.category
      ? (cats?.categories.find((category) => category.id === browse.category)?.name ??
          browse.category)
      : null,
  );

  const railEntries = $derived([
    { key: "", label: "All", count: allTotal },
    ...(cats?.categories ?? []).map((category) => ({
      key: category.id,
      label: category.name,
      count: category.count,
    })),
  ]);

  const pills = $derived(cats ? statusPills(cats.portals, Date.now() / 1000) : []);
  const shelves = $derived(cats ? allShelves(continueItems, cats.categories) : []);

  // ---- the grid: infinite scroll over offset/limit ----

  const query = $derived<ItemsQuery>({
    category: browse.category,
    q: term ?? "",
    sort: browse.sort,
  });
  const gridKey = $derived(view === "grid" ? itemsPath(query, 0) : null);

  let paging = $state.raw(initialPaging());
  let loading = $state(false);
  let gridError = $state<string | null>(null);
  let generation = 0;
  let gridController: AbortController | null = null;
  let sentinelEl = $state<HTMLElement | null>(null);
  let observer: IntersectionObserver | null = null;

  async function loadMore() {
    const offset = nextOffset(paging);
    if (offset === null || loading || gridKey === null) return;
    const mine = generation;
    const signal = gridController?.signal;
    const asked = query;
    loading = true;
    gridError = null;
    try {
      const page = await loadItems(itemsPath(asked, offset), signal);
      if (mine !== generation) return;
      paging = appendPage(paging, page);
      if (asked.category === "" && asked.q === "") allTotal = page.total;
    } catch (error) {
      if (mine !== generation || signal?.aborted || isOnDemandOff(error)) return;
      gridError = error instanceof ApiError ? error.message : "Couldn't load more titles.";
    } finally {
      if (mine === generation) loading = false;
    }
    // Still in view (a short page or a tall screen)? Re-observing fires again if so.
    await tick();
    if (mine === generation && observer && sentinelEl) {
      observer.unobserve(sentinelEl);
      observer.observe(sentinelEl);
    }
  }

  $effect(() => {
    const key = gridKey;
    untrack(() => {
      generation += 1;
      gridController?.abort();
      gridController = key ? new AbortController() : null;
      paging = initialPaging();
      loading = false;
      gridError = null;
      if (key) void loadMore();
    });
  });

  $effect(() => {
    const el = sentinelEl;
    const root = scrollRoot;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void untrack(() => loadMore());
      },
      { root, rootMargin: "600px 0px" },
    );
    io.observe(el);
    observer = io;
    return () => {
      io.disconnect();
      if (observer === io) observer = null;
    };
  });

  const line = $derived(sentinel(paging, emptyText(browse.q, categoryName)));

  onDestroy(() => {
    applySearch.cancel();
    pageController.abort();
    gridController?.abort();
  });

  const label = $derived(accountLabel($session));
</script>

<div class="picker odpage">
  <div class="appbar">
    <div class="brand">
      On Demand
      <small>{label}</small>
    </div>
    <div class="spacer"></div>
    <button class="btn" onclick={() => navigate("/")}>Channels</button>
    <button class="btn" onclick={() => navigate("/guide")}>Guide</button>
    <button class="btn" onclick={() => navigate("/multiview")}>Multiview</button>
    <button class="btn" onclick={() => navigate("/settings")}>Settings</button>
  </div>

  <div class="search">
    <span>⌕</span>
    <input
      placeholder="Search all titles…"
      bind:value={typed}
      oninput={() => applySearch(typed)}
      onkeydown={(event) => {
        if (event.key === "Enter") {
          applySearch.cancel();
          applySearch(typed);
        }
      }}
    />
  </div>

  <div class="chips">
    {#each SORTS as chip (chip.key)}
      <button
        class="chip {activeSort(browse.sort, searching) === chip.key ? 'on' : ''}"
        onclick={() => chooseSort(chip.key)}
      >
        {chip.label}
      </button>
    {/each}
    {#if searching}
      <span class="odhint">{searchHint(categoryName, browse.sort)}</span>
    {/if}
  </div>

  {#if pills.length > 0}
    <div class="odstatus">
      {#each pills as pill (pill.portal)}
        <span class="pill {pill.status}">{pill.text}</span>
      {/each}
    </div>
  {/if}

  {#if catsError}
    <div style="padding: 0 14px 10px">
      <div class="error-banner noticerow">
        <span>{catsError}</span>
        <button class="btn" onclick={() => void fetchCategories()}>Try again</button>
      </div>
    </div>
  {/if}

  <div class="bwrap">
    <Rail entries={railEntries} active={browse.category} onselect={selectCategory} />
    <div class="odmain" bind:this={mainEl}>
      {#if view === "shelves"}
        {#if !cats}
          <div class="empty">{catsError ? "" : "Loading…"}</div>
        {:else}
          {#each shelves as shelf (shelf.key)}
            {#if shelf.kind === "continue"}
              <section class="odshelf">
                <div class="rowhead"><h3>{shelf.title}</h3></div>
                <div class="shelf cw">
                  {#each continueItems as item (`${item.portal}:${item.id}`)}
                    <ContinueCard {item} onpick={pick} />
                  {/each}
                </div>
              </section>
            {:else if shelf.kind === "recent"}
              <OnDemandShelf
                title={shelf.title}
                path={shelf.path}
                {scrollRoot}
                onpick={pick}
                onseeall={() => go({ category: "", q: "", sort: browse.sort, allGrid: true })}
                onloaded={(page) => (allTotal = page.total)}
              />
            {:else}
              <OnDemandShelf
                title={shelf.title}
                count={shelf.count}
                path={shelf.path}
                {scrollRoot}
                onpick={pick}
                onseeall={() => selectCategory(shelf.category)}
              />
            {/if}
          {/each}
        {/if}
      {:else}
        <div class="pgrid">
          {#each paging.items as item (`${item.portal}:${item.id}`)}
            <PosterCard {item} onpick={pick} />
          {/each}
          <div class="sentinel" bind:this={sentinelEl}>
            {#if gridError}
              <span>{gridError}</span>
              <button class="btn" onclick={() => void loadMore()}>Try again</button>
            {:else}
              {line.text}
            {/if}
          </div>
        </div>
      {/if}
    </div>
  </div>
</div>
