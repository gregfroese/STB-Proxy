<script lang="ts">
  // A title's page. Placeholder until ticket 11 builds the detail (Play, Seasons, Episodes).
  import { route } from "../lib/router";

  const portal = $derived($route.query.get("portal") ?? "");
  const id = $derived($route.query.get("id") ?? "");
</script>

<div class="picker odpage">
  <div class="appbar">
    <button class="btn" onclick={() => history.back()}>‹ Back</button>
    <div class="brand">On Demand</div>
  </div>
  <div class="empty">This title's page isn't built yet ({portal} / {id}).</div>
</div>
