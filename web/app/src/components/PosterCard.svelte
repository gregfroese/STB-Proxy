<script lang="ts">
  // A 2:3 poster with its title, year, ★ rating and portal; badges for Series, ✓ Watched
  // and a Resume point. Without a poster (or when it fails to load) the title is drawn.
  import { posterBadges } from "../lib/onDemandLogic";
  import type { OnDemandItem } from "../lib/types";

  let { item, onpick }: { item: OnDemandItem; onpick: (item: OnDemandItem) => void } = $props();

  let broken = $state(false);
  const badges = $derived(posterBadges(item));
  const showImage = $derived(item.poster != null && !broken);
</script>

<button class="pcard" onclick={() => onpick(item)} title={item.name}>
  <div class="poster {showImage ? '' : 'none'}">
    {#if showImage}
      <img src={item.poster} alt="" loading="lazy" onerror={() => (broken = true)} />
    {:else}
      <span class="pname">{item.name}</span>
    {/if}
    {#if badges.series}<span class="kind">Series</span>{/if}
    {#if badges.watched}<span class="wmark" title="Watched">✓</span>{/if}
    {#if badges.progress != null}
      <span class="prog"><i style="width: {badges.progress * 100}%"></i></span>
    {/if}
  </div>
  <div class="ptitle">{item.name}</div>
  <div class="pmeta">
    {#if item.year != null}<span>{item.year}</span>{/if}
    {#if item.rating != null}<span class="star">★ {item.rating}</span>{/if}
    <span class="src">{item.portalName}</span>
  </div>
</button>
