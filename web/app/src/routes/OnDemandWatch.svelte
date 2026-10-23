<script lang="ts">
  // The On Demand player's route. A stub until ticket 12 builds the player: it shows what
  // the title page handed over (the session, the item and where to start) and releases the
  // session on leave, so the slot isn't held until it idles out.
  import { onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { endSession, playHandoff } from "../lib/onDemand";
  import { watchFromQuery } from "../lib/onDemandDetailLogic";
  import { clock } from "../lib/onDemandLogic";
  import { route } from "../lib/router";

  const start = watchFromQuery(get(route).query);
  const offered = get(playHandoff);
  // Taken once: Back and forward again must not reuse a session that has been released.
  playHandoff.set(null);
  const handoff =
    offered && start && JSON.stringify(offered.start) === JSON.stringify(start) ? offered : null;

  onDestroy(() => {
    if (handoff) void endSession(handoff.session.session).catch(() => {});
  });
</script>

<div class="picker odpage">
  <div class="appbar">
    <button class="btn" onclick={() => history.back()}>‹ Back</button>
    <div class="brand">{handoff?.title ?? "On Demand"}</div>
  </div>
  <div class="empty">
    {#if handoff}
      The On Demand player isn't built yet. Session {handoff.session.session} would start at
      {clock(handoff.start.startSec)}.
    {:else}
      The On Demand player isn't built yet. Open the title again to play it.
    {/if}
  </div>
</div>
