<script lang="ts">
  import { resetEpg } from "../lib/epg";
  import { clearLineup } from "../lib/lineup";
  import { resetMultiview } from "../lib/multiview";
  import { logout } from "../lib/api";
  import { navigate } from "../lib/router";
  import { accountLabel, clearSession, session } from "../lib/session";

  let busy = $state(false);

  const label = $derived(accountLabel($session));

  async function signOut() {
    if (busy) return;
    busy = true;
    try {
      await logout();
    } catch {
      /* clearing locally is enough */
    }
    clearSession();
    clearLineup();
    resetEpg();
    resetMultiview();
    navigate("/login", true);
  }
</script>

<div class="settings">
  <div class="appbar">
    <button class="btn" onclick={() => navigate("/")}>‹ Channels</button>
    <div class="spacer"></div>
    <div class="brand">Settings</div>
  </div>
  <div class="body">
    <div class="card">
      <h2>Account</h2>
      <div class="kv"><span>Signed in as</span><span>{label}</span></div>
      <div>
        <button class="btn danger" onclick={signOut} disabled={busy}>
          {busy ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </div>
    <div class="card">
      <h2>About</h2>
      <div class="kv"><span>STB Proxy (web viewer)</span><span>v{__APP_VERSION__}</span></div>
      <p class="notice" style="margin:0">
        Switch account by signing out and signing in again. Only the last username is stored in this
        browser.
      </p>
    </div>
  </div>
</div>
