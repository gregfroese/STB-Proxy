<script lang="ts">
  // One shelf on the All view: a heading with See all ›, and a row of up to 20 posters
  // fetched the first time the shelf comes near the screen.
  import { onDestroy } from "svelte";
  import { loadItems } from "../lib/onDemand";
  import { isOnDemandOff } from "../lib/onDemandLogic";
  import type { OnDemandItem, OnDemandPage } from "../lib/types";
  import PosterCard from "./PosterCard.svelte";

  let {
    title,
    count = null,
    path,
    scrollRoot,
    onpick,
    onseeall,
    onloaded,
  }: {
    title: string;
    count?: number | null;
    path: string;
    /** The element that scrolls the shelves, or null when the page scrolls (TV). */
    scrollRoot: Element | null;
    onpick: (item: OnDemandItem) => void;
    onseeall: () => void;
    onloaded?: (page: OnDemandPage) => void;
  } = $props();

  let el = $state<HTMLElement | null>(null);
  let items = $state<OnDemandItem[] | null>(null);
  let failed = $state(false);
  let started = false;
  const controller = new AbortController();

  async function load() {
    started = true;
    failed = false;
    try {
      const page = await loadItems(path, controller.signal);
      items = page.items;
      onloaded?.(page);
    } catch (error) {
      if (controller.signal.aborted || isOnDemandOff(error)) return;
      failed = true;
    }
  }

  $effect(() => {
    if (!el || started) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          void load();
        }
      },
      { root: scrollRoot, rootMargin: "400px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  });

  onDestroy(() => controller.abort());
</script>

<section class="odshelf" bind:this={el}>
  <div class="rowhead">
    <h3>{title}</h3>
    {#if count != null}<span class="rc">{count}</span>{/if}
    <button class="more" onclick={onseeall}>See all ›</button>
  </div>
  <div class="shelf">
    {#if items === null && !failed}
      <div class="shelfhint">Loading…</div>
    {:else if failed}
      <div class="shelfhint">
        Couldn't load this row.
        <button class="btn" onclick={() => void load()}>Try again</button>
      </div>
    {:else if items && items.length === 0}
      <div class="shelfhint">Nothing here yet.</div>
    {:else if items}
      {#each items as item (`${item.portal}:${item.id}`)}
        <PosterCard {item} {onpick} />
      {/each}
    {/if}
  </div>
</section>
