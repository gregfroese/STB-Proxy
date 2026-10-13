<script lang="ts">
  let {
    name,
    logo = null,
    size = 56,
  }: { name: string; logo?: string | null; size?: number } = $props();

  const initials = $derived(
    name
      .replace(/[^A-Za-z0-9 ]/g, "")
      .split(/\s+/)
      .filter(Boolean)
      .map((word) => word[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?",
  );
  const hue = $derived([...name].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 360);
</script>

{#if logo}
  <img class="logo-img" src={logo} alt="" style="width:{size}px;height:{size}px" />
{:else}
  <div
    class="logo"
    style="width:{size}px;height:{size}px;font-size:{Math.round(
      size / 4,
    )}px;background:hsl({hue} 45% 32%)"
  >
    {initials}
  </div>
{/if}
