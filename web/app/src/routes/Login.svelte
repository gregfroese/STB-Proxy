<script lang="ts">
  import { ApiError, login } from "../lib/api";
  import { clearLineup } from "../lib/lineup";
  import { navigate } from "../lib/router";
  import { sessionMessage, setSession } from "../lib/session";

  let username = $state(localStorage.getItem("stbproxy.username") ?? "");
  let password = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  const shownError = $derived(error ?? $sessionMessage);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    error = null;
    sessionMessage.set(null);
    try {
      const info = await login(username.trim(), password);
      localStorage.setItem("stbproxy.username", username.trim());
      clearLineup();
      setSession(info);
      navigate("/", true);
    } catch (caught) {
      error = caught instanceof ApiError ? caught.message : "Could not sign in.";
    } finally {
      busy = false;
    }
  }
</script>

<div class="login">
  <form class="card" onsubmit={submit}>
    <div>
      <h1>STB Proxy</h1>
      <p class="sub">Sign in with your viewer account.</p>
    </div>
    {#if shownError}
      <div class="error-banner">{shownError}</div>
    {/if}
    <div class="field">
      <label for="username">Username</label>
      <input
        id="username"
        autocomplete="username"
        autocapitalize="none"
        bind:value={username}
        disabled={busy}
      />
    </div>
    <div class="field">
      <label for="password">Password</label>
      <input
        id="password"
        type="password"
        autocomplete="current-password"
        bind:value={password}
        disabled={busy}
      />
    </div>
    <button class="btn primary" type="submit" disabled={busy}>
      {busy ? "Signing in…" : "Sign in"}
    </button>
    <a class="btn" href="/companion.apk" download>Download the Android app (APK)</a>
  </form>
</div>
