<script lang="ts" module>
  // The picker's left rail (a horizontal strip on phones): one button per entry with its
  // count. Shared by Channels (Blocks/Genres) and On Demand (categories).

  export interface RailEntry {
    key: string;
    label: string;
    /** null hides the count (not known yet). */
    count: number | null;
  }
</script>

<script lang="ts">
  let {
    entries,
    active,
    onselect,
  }: {
    entries: RailEntry[];
    /** The highlighted entry's key, or null for none. */
    active: string | null;
    onselect: (key: string) => void;
  } = $props();
</script>

<div class="rail">
  {#each entries as entry (entry.key)}
    <button class="railbtn {active === entry.key ? 'on' : ''}" onclick={() => onselect(entry.key)}>
      {entry.label}
      {#if entry.count != null}<span class="rc">{entry.count}</span>{/if}
    </button>
  {/each}
</div>
