<script lang="ts">
  import { onMount } from "svelte";
  import { navigate, route } from "./lib/router";
  import { installUnauthorizedHandler, loadSession, session, sessionChecked } from "./lib/session";
  import Login from "./routes/Login.svelte";
  import Picker from "./routes/Picker.svelte";
  import Player from "./routes/Player.svelte";
  import Multiview from "./routes/Multiview.svelte";
  import Guide from "./routes/Guide.svelte";
  import Settings from "./routes/Settings.svelte";
  import OnDemand from "./routes/OnDemand.svelte";
  import OnDemandTitle from "./routes/OnDemandTitle.svelte";

  onMount(() => {
    installUnauthorizedHandler();
    void loadSession();
  });

  const authed = $derived($session !== null);

  $effect(() => {
    if (!$sessionChecked) return;
    if (!authed && $route.name !== "login") navigate("/login", true);
    else if (authed && $route.name === "login") navigate("/", true);
  });
</script>

{#if !$sessionChecked}
  <div class="boot">Loading…</div>
{:else if !authed}
  <Login />
{:else if $route.name === "settings"}
  <Settings />
{:else if $route.name === "player"}
  <Player />
{:else if $route.name === "multiview"}
  <Multiview />
{:else if $route.name === "guide"}
  <Guide />
{:else if $route.name === "ondemand"}
  <OnDemand />
{:else if $route.name === "ondemandTitle"}
  <OnDemandTitle />
{:else}
  <Picker />
{/if}
