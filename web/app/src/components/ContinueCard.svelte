<script lang="ts">
  // A wide Continue watching card: art, a progress bar and "80 min left" or
  // "S2 · E4 · Name · Up next".
  import { continueLine, posterBadges } from "../lib/onDemandLogic";
  import type { OnDemandItem } from "../lib/types";

  let { item, onpick }: { item: OnDemandItem; onpick: (item: OnDemandItem) => void } = $props();

  let broken = $state(false);
  const progress = $derived(posterBadges(item).progress);
  const showImage = $derived(item.poster != null && !broken);
</script>

<button class="cwcard" onclick={() => onpick(item)} title={item.name}>
  <div class="art">
    {#if showImage}
      <img src={item.poster} alt="" loading="lazy" onerror={() => (broken = true)} />
    {/if}
    <span class="cwname">{item.name}</span>
    {#if progress != null}
      <span class="prog"><i style="width: {progress * 100}%"></i></span>
    {/if}
  </div>
  <div class="sub">{continueLine(item)}</div>
</button>
