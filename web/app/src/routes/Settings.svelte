<script lang="ts">
  import { resetEpg } from "../lib/epg";
  import { clearLineup } from "../lib/lineup";
  import { resetMultiview } from "../lib/multiview";
  import { logout } from "../lib/api";
  import { groupMode } from "../lib/prefs";
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
      <h2>Channel grouping</h2>
      <p class="notice" style="margin:0 0 8px">
        How the channel picker arranges its rail. Blocks are only used when the account has any;
        otherwise the picker groups by the portal's Genres either way.
      </p>
      <div class="chips" style="padding:0">
        <button
          class="chip {$groupMode === 'blocks' ? 'on' : ''}"
          onclick={() => groupMode.set("blocks")}
        >
          Blocks
        </button>
        <button
          class="chip {$groupMode === 'genres' ? 'on' : ''}"
          onclick={() => groupMode.set("genres")}
        >
          Genres
        </button>
      </div>
    </div>
    <div class="card">
      <h2>Companion app</h2>
      <p class="notice" style="margin:0 0 8px">
        On Android TV or phone, sideload the STB-Proxy companion app — the same channels, player and
        Multiview as this page.
      </p>
      <a class="btn" href="/companion.apk" download>Download the Android app (APK)</a>
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
