<script lang="ts">
  import type { Channel } from "../lib/types";
  import { OTHER_BLOCK, extraBlockCount } from "../lib/pickerLogic";
  import Logo from "./Logo.svelte";

  let {
    channel,
    activeBlock,
    searching = false,
    onpick,
  }: {
    channel: Channel;
    activeBlock: string | null;
    searching?: boolean;
    onpick: (channel: Channel) => void;
  } = $props();

  const extra = $derived(extraBlockCount(channel, activeBlock, searching));
  const dimOthers = $derived(!searching && activeBlock != null && activeBlock !== OTHER_BLOCK);
</script>

<button
  class="tile"
  onclick={() => onpick(channel)}
  title={`${channel.number ?? ""} ${channel.name}`.trim()}
>
  {#if channel.number}<span class="tnum">{channel.number}</span>{/if}
  {#if channel.favourite}<span class="favmark">★</span>{/if}
  <Logo name={channel.name} logo={channel.logo} size={56} />
  <div class="tnm">{channel.name}</div>
  <div class="tags">
    {#if channel.blocks.length > 0}
      {#each channel.blocks as block (block)}
        <span class="tag {dimOthers && block !== activeBlock ? 'extra' : ''}">{block}</span>
      {/each}
    {:else}
      <span class="tag other">ungrouped</span>
    {/if}
    {#each channel.blockFavourites as block (block)}
      <span class="tag bfav">★ {block}</span>
    {/each}
  </div>
  {#if extra > 0}<span class="plus">+{extra}</span>{/if}
</button>
