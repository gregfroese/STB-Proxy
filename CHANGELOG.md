# Changelog

STB-Proxy is a fork of [Chris230291/STB-Proxy](https://github.com/Chris230291/STB-Proxy), which had no version numbers. Version 1.0.0 is everything added since the fork. From here on, every change bumps the version: the minor number for new features, the patch number for fixes.

## [1.18.3] - 2026-10-22

### Web viewer

- **Full screen in Downloader (and other TV apps' built-in browsers)**: full screen now grows the player to fill the browser instead of asking for real full screen. Fire TV draws video on a hardware layer positioned by the app's browser view, so once the page was handed to a separate full-screen view the picture stayed at its old size. The remote's Back button leaves full screen (and stays on the channel you zapped to), instead of leaving the page. Silk and desktop browsers keep real full screen.

## [1.18.2] - 2026-10-22

### Web viewer

- **Full screen on Fire TV, take two**: the player now filled the screen, but Fire TV kept drawing the picture at its old size and place (it snapped to full size only for a moment when leaving full screen). Fire TV draws video on a hardware layer that doesn't follow page layout changes, so the player now briefly hides and re-shows the video whenever its size changes (full screen on/off, window resize), which makes the browser redraw the picture at the new size. Playback continues.
- `?debug=1` on the player now also shows the window size, the video's on-page size and the full-screen state, to diagnose TV browsers.

## [1.18.1] - 2026-10-22

### Web viewer

- **Full screen fills the TV**: on Fire TV (Silk, or the Downloader app's browser) and on desktop, full screen now grows the player to cover the whole screen and fullscreens the page. Before, TV browsers hid everything around the video but left the picture at its old size. Phones still fullscreen the video itself. Back or Esc leaves full screen, and the ⤢ button stays on screen.
- **Download the app from Downloader**: the **Download the Android app (APK)** link no longer uses the `download` attribute, which Downloader's built-in browser silently ignores. It's now a plain link; the server already sends the APK as an attachment, so every browser still downloads it.
- **Channel list scrolls on TV**: on TV browsers the channel grid now scrolls the page itself (the group list stays pinned on the left), because Silk's cursor and a WebView's D-pad don't scroll a box inside the page.

## [1.18.0] - 2026-10-22

### Android app

- **One navigation everywhere**: Channels, Guide, Multiview and Settings are always one step away. On Android TV a slim icon rail sits on the left and widens to show labels when you press Left into it; on phones it's a bottom navigation bar. Settings is no longer reachable only from some screens, and the per-screen button rows are gone.
- **Consistent screens**: every screen shares the same header (title, account, its own action such as Refresh), spacing and focus ring. Settings is regrouped into cards (Proxy, Channel grouping, Accounts, Sign out).
- **Search works with a remote**: on Android TV the search box (Channels and Guide) is now reachable with the D-pad. Press OK to type; the keyboard's Search key takes you to the results, and Up/Down or Back leave the box.
- **Text fields no longer trap the remote**: moving over a text field in Settings or Login on TV no longer pops the keyboard and captures the D-pad; press OK to edit.
- **Back returns where you were**: coming back from the player puts focus on the channel you were watching, Back from Multiview returns to the screen that opened it, and Back from any top-level screen goes to Channels, then exits.
- **Guide opens on a group**: the Guide now starts on the first Block/Genre instead of an empty list.
- **Aspect per channel**: the player has an **Aspect** button (Auto / 16:9 / 4:3 / Zoom), remembered per channel, for channels whose stream reports the wrong picture shape (typically SD channels that don't flag widescreen). Auto now sizes the picture with media3's own presentation state (non-square SD pixels included) and hides the previous channel's last frame until the new one is drawn.
- **Portrait player clears the status bar**: on phones the picture and its buttons sit below the clock/status icons and the camera cutout instead of underneath them.
- **Swipe hint**: swiping up or down on the video (player and Multiview on phones) shows which way you're going and the channel it lands on, then confirms the switch.

## [1.17.0] - 2026-10-18

### Web viewer

- **Download the app from the login page**: the sign-in screen now has a **Download the Android app (APK)** link, so the companion app can be grabbed before logging in. The BFF's `/companion.apk` is served without a session for this (the app still needs an account to use).

## [1.16.0] - 2026-10-18

### Guide — Android app & web viewer

- **Guide screen**: both viewers gain a **Guide** for browsing the schedule. Channels are grouped the way you group them (**Blocks** or **Genres**), with a **programme search** (words / prefix / contains / exact / regex), an **On now** filter and a channel-name sub-filter. Expanding a channel shows its next-24-hour timeline, with progress on the programme airing now; tapping a programme plays its channel.
- **Scoped to your account**: the Guide comes from new account-scoped endpoints (`GET /api/guide/search`, `GET /api/guide/channel`) that reuse the operator's guide engine but hide dead channels and hidden ("STB-Proxy only") Blocks. The web viewer reaches them through its BFF, which caches a channel's timeline per account.
- **Channel up/down follows where you launched**: a channel opened from search walks the result set; from **On now**, that list; from the picker, its Block or Genre. The scope's label shows in the player.
- **Channel up/down by gesture**: the web player takes **PageUp**/**PageDown** and a vertical swipe on the video; the Android phone player takes a vertical swipe (Android TV keeps the D-pad). In **Multiview**, **ChannelUp**/**ChannelDown** (TV) and a phone swipe step the focused/audio tile through the whole lineup.

## [1.15.0] - 2026-10-18

### Web viewer

- **Companion app download**: the web viewer's Settings has a **Download the Android app (APK)** link. The BFF streams the APK STB-Proxy already serves from its static folder, so the browser (which can't reach STB-Proxy directly) can sideload it. Login is required, same as the rest of the viewer.

## [1.14.0] - 2026-10-18

### Playlist Editor

- **Filter by portal**: a **Portal** dropdown beside the genre and block filters narrows the editor to one portal's channels, with each portal's name and channel count. Like the other filters it's remembered between visits and kept in saved filters.

## [1.13.0] - 2026-10-18

### Blocks

- **Remove a block**: a trash button on each row of the Blocks page takes every channel out of the block. Since a block only exists while it holds channels, this removes it — its entry is also dropped from the operator's order, the **hidden** and **default** sets, its block favourites and any accounts assigned it, and Plex/Jellyfin are re-synced if the lineup changed. Handy after switching servers, when the old channel numbers no longer exist.

## [1.12.0] - 2026-10-18

### Android app & web viewer

- **Channel grouping**: a per-device **Channel grouping** switch in each viewer's Settings lets the picker arrange channels by the portal's **Genres** instead of **Blocks**.
- **Blocks still scope the lineup**: whichever grouping is chosen, a channel only present in an off or hidden Block never appears. When an account has no Blocks at all, the picker falls back to Genres automatically so nothing lands in a lone "Other" bucket.
- Genres are merged across portals by name; channels the portal gives no genre for group under **Other**. The player's channel up/down (and Multiview's picker) follow the active group.

## [1.11.0] - 2026-10-18

### Added

- **Portals**: a **Duplicate** button on a portal's edit dialog copies it — same URL, MACs, proxy, logos and channel edits — under "Name (copy)", **switched off** so nothing starts using it until you turn it on.

## [1.10.1] - 2026-10-18

### Fixed

- **Portals**: the Add/Edit modal scrolls again, so the **Add** and **Save** buttons are reachable when the device-lock fields make the form taller than the screen.
- **Portals**: adding or saving now shows a spinner and "Testing portal…" while it logs in over the network, instead of appearing to do nothing, and portal lookups time out after 15 seconds instead of hanging.

## [1.10.0] - 2026-10-13

### Changed

- **Operator UI modernisation**: the whole Operator UI is restyled on a vendored front-end stack — **Bootstrap 5.3.8**, **Bootstrap Icons 1.13.2**, **jQuery 3.7.1** and **DataTables 2.3.8 + Buttons** (no CDN) — behind a single **token theme** (`static/theme.css`) and a **shared shell** (grouped top bar, skip link, bottom-right toasts, hamburger sheet).
- **Canonical components**: token cards, tables, forms and switches, buttons (including labelled icon buttons), tabs, modals, notices, badges and empty states, plus the shared card grid, composed across every page.
- **Page restyle**: Dashboard, Streams, Recordings, Multiview, Playlist Editor, Guide, Blocks, Portals, Accounts, Settings and Changelog are rebuilt from those components.
- **Light mode**: a `data-bs-theme` switch with a sun/moon toggle and a no-FOUC inline script, alongside the default dark theme.

## [1.9.0] - 2026-10-13

### Web viewer

- A new **web viewer client** (`web/`), a browser app that mirrors the Android companion: log in as an Account, browse channels grouped by Block, play one channel with now/next EPG, or watch a Multiview — for desktop and phone equally.
- **BFF + SPA**: a small **FastAPI** server (`web/bff/`) holds Account credentials server-side, proxies the int-only STB-Proxy's `/api/lineup`, `/xmltv` (as now/next `/api/epg`) and live `/play` (as `/stream/…`), and serves a **Svelte 5 + Vite + TypeScript** SPA (`web/app/`). The proxy stays off the internet; no CORS.
- **Auth**: login form → server-side sessions (opaque token, Fernet-encrypted credentials, `__Host-session` HttpOnly cookie), idle 60 min + absolute 12 h, ~15 min credential re-validation, per-username login backoff, CSRF and security headers.
- Hosted on LXC 119 `stb-proxy-web` behind Caddy at `watch.home.gregfroese.com`; `web/deploy.sh` builds and restarts the systemd unit.

### Active streams page

- A new **Streams** page (nav **Streams**) lists every active stream: **who is watching** (the Account username, or the client IP for anonymous players), the client IP, the kind of viewer (client / recording / preview), the portal, MAC, channel and duration. Each stream has a **Stop** button that ends it and frees its tuner.
- `/streaming` now includes the resolved `account` for each stream, so the Dashboard and the Streams page can name the viewer behind a shared connection (e.g. the web viewer's BFF).

## [1.8.0] - 2026-10-12

### Android app

- A custom **launcher icon** and **TV banner** (a screen with a play triangle), replacing the placeholder.
- The APK is now named **`STB-Proxy-Companion-<version>.apk`** (`./gradlew assembleCompanion`).
- Docs: the README describes the app as the **companion app** for STB-Proxy.

## [1.7.1] - 2026-10-12

### Android app

- **Fix**: the picker's title no longer wraps on a narrow phone — the title sits on its own line, with **Refresh / Multiview / Settings** below it.
- Docs: the README now covers viewer accounts and the Android app, with phone and Android TV screenshots.

## [1.7.0] - 2026-10-12

### Block ordering

- **Order your blocks**: the Blocks page has **up/down** buttons to arrange them, saved as a top-level `block order` in `config.json`. The order is used everywhere — the Blocks page, the Accounts and Default-blocks pickers, and the Android app's block rail (via `/api/lineup`).

## [1.6.2] - 2026-10-12

### Accounts

- The **Accounts** page now marks blocks that are **switched off** (`Canada — off`) alongside STB-Proxy-only ones. A block must be **on** (Blocks page) to contribute channels, even to an account it's assigned to — this makes it obvious why assigning an off block changes nothing.

## [1.6.1] - 2026-10-12

### Android app

- **Refresh the lineup**: a **Refresh** button on the picker (phone and TV). The lineup also reloads on launch and when you switch accounts.
- **Fix**: on TV, the Multiview top bar (Back / **Grid** layout / Refresh) is reachable again — press **Up** from the top row of Tiles, then Left/Right to pick an item and Enter to activate it.

## [1.6.0] - 2026-10-12

### Favourites in the app

- **`/api/lineup`** now carries each channel's **`favourite`** flag and its **`blockFavourites`** list, and sorts favourites first (overall favourites, then block favourites, then the rest by number and name).
- The Android picker has **All / ★ Favourites / ★ Block faves** filter chips, and favourites sort to the top of the list.

### Android TV Multiview

- The **D-pad drives Multiview directly**: Left/Right/Up/Down move between Tiles, and selecting a Tile opens a **screen-level action bar** (Pick / Swap / Audio / Remove / Close) navigated with Left/Right and Enter — so you can set a Tile's **audio source** or **change its channel**.
- TV buttons now show a bright focus ring when selected.

## [1.5.1] - 2026-10-12

### Android app

- **TV single view is full-screen**: the guide starts hidden (the video fills the screen); a **Guide** button overlays it, the remote's **Back** closes it, and a second **Back** leaves the player.
- **TV Multiview gets a layout chooser**: a **Grid** button cycles **1×1 / 2×1 / 1×2 / 2×2**. The first Tile is focused so the remote can navigate the grid, and selecting an empty Tile opens the channel picker.
- **Fix**: Settings and the Accounts list were dark text on the dark background; the theme now sets a proper content colour, so everything is readable.
- **Switching accounts reloads the channel lineup** — the picker no longer keeps the previous account's channels.

## [1.5.0] - 2026-10-12

### Accounts

- **STB-Proxy-only blocks can be assigned to accounts.** A hidden block is still kept out of anonymous and operator requests, the public API, Plex and Jellyfin — but you can now assign it to an **Account**, and that account sees its channels on every feed (`/playlist`, `/xmltv`, `/lineup.json`, `/lineup.post` and `/api/lineup`). Hidden blocks are marked in the Accounts block picker; the anonymous **Default blocks** picker still excludes them.

## [1.4.1] - 2026-10-12

### Android app

- **Fix: the screen no longer sleeps while watching.** Keep-screen-on is now a reference-counted window flag, so moving between the player and Multiview (or between Tiles) no longer drops it.

## [1.4.0] - 2026-10-12

### Android app

- **Channel pickers are a list now**: each channel is one row — logo, full-width name (so long names show), channel number, a now/next teaser and its Block tags — in the picker and in the Multiview **Pick channel** overlay, instead of grid boxes.
- **Fixes**: the Multiview full-screen button no longer wraps vertically in portrait, and the player/Multiview buttons are kept to a single line.

## [1.3.0] - 2026-10-12

### Android app

- **Controls that get out of the way**: the on-screen controls fade after a few seconds and return on a tap or a remote key, in the single player and in Multiview.
- **Video keeps its shape**: streams are letterboxed to their real aspect ratio instead of being stretched — in the player and in every Multiview Tile. Multiview in portrait now stacks two Tiles rather than stretching one to fill the screen.
- **Full-screen Multiview** on phones, with the same full-screen toggle as the player.
- **A dismissible guide**: the full-screen now/next panel has a ✕ Close button and can be swiped off to the right.
- **The screen stays awake** while a video is playing.
- **Multiview playback fixes**: Tiles no longer take audio focus from each other (which could freeze the silent Tile), and each Tile uses a texture surface for reliability.

## [1.2.0] - 2026-10-12

### Android app

- **Full-screen playback**: the player fills the screen in landscape, hiding the system bars, and a **Full screen** button does the same in any orientation. While full-screen, a **Guide** button shows or hides the now/next sidebar as an overlay.
- **Multiview is easier to reach**: a labelled **Multiview** button on the channel picker and in the player, next to a clearer **Settings** button.
- The app's **version** is shown on the Login and Settings screens.
- Screens keep clear of the system bars (status and navigation).

## [1.1.0] - 2026-10-12

### Viewer accounts

- **Accounts**: viewer logins (username and password) for the feed endpoints, each mapped to a set of **Blocks**. A request authenticating as an account gets its public channels plus the channels of its assigned, switched-on blocks. Hidden (STB-Proxy only) blocks stay invisible to accounts. Passwords are stored only as salted PBKDF2-SHA256 hashes.
- A new **Accounts** page to create, edit, reset the password of, enable or delete accounts, and to assign their blocks. Renaming or emptying a block keeps every account's assignment in step.
- The operator login and the API token are unchanged; accounts are viewer-only, over HTTP Basic, so Plex, Jellyfin and any M3U/HDHomeRun player are scoped per account for free.

### Account-scoped feeds and API

- `/playlist`, `/xmltv`, `/lineup.json` and `/lineup.post` are scoped to the account presented in the request. Operator and unauthenticated requests behave exactly as before.
- **`GET /api/lineup`**: one flat, enveloped JSON endpoint for clients — `account`, `blocks`, `channels` (each with portal, name, number, logo, genre, XMLTV id, its blocks and a relative play URL) and `failedPortals`. It uses the same account credentials as the feeds.
- **Default blocks**: an optional, default-off setting on the Blocks page that scopes requests with no account the same way an account's blocks do. It is not a filter, so individually enabled public channels stay visible.

### Android app — "STB Proxy"

- A single app for **phone and Android TV** (launcher entry only), sideloaded as a self-signed release APK. Log in as an account over HTTP Basic; several accounts can share one proxy address.
- **Channel picker** grouped by block: a block rail (TV) or chip strip (phone) beside a grid of channel tiles with logo, number, name and block tags, and a search across every block.
- **Player** with a persistent now/next sidebar (TV) or bottom sheet (phone), channel up/down through the block a channel was launched from, and clear states for all-tuners-busy, an unreachable stream and a redirect.
- **Multiview**: several channels at once — 2 × 2 on TV, 1 × 2 on phone landscape, a single full-bleed tile in portrait — with per-tile pick, swap, audio and remove, and tuner budgeting.

## [1.0.0] - 2026-10-09

### Channel blocks

- **Blocks**: group channels and switch the whole group on or off. A channel is in your lineup when it's enabled on its own or in a block that's on, and it isn't dead. One rule drives the playlist, XMLTV, HDHomeRun lineup and Plex sync. [#1](https://github.com/gregfroese/STB-Proxy/pull/1)
- A **Blocks** page, with the channels and dead count of each block, and a **Favourites** tab. [#1](https://github.com/gregfroese/STB-Proxy/pull/1), [#2](https://github.com/gregfroese/STB-Proxy/pull/2)
- A channel can be in several blocks. Add many channels to a block, or take them out, in one go from the Playlist Editor. Dead counts stay live. [#15](https://github.com/gregfroese/STB-Proxy/pull/15)
- **Rename** a block; its channels, state, saved filters and favourites move with it. [#23](https://github.com/gregfroese/STB-Proxy/pull/23)
- **STB-Proxy only** blocks: hidden from the API, and when on, their channels stay out of Plex and Jellyfin but still play in STB-Proxy. [#23](https://github.com/gregfroese/STB-Proxy/pull/23), [#29](https://github.com/gregfroese/STB-Proxy/pull/29)
- **Block favourites**: favourites within a block, apart from the overall ones. They come first in the block's list, with a **Favourites only** switch, and channel up / down follows them. [#28](https://github.com/gregfroese/STB-Proxy/pull/28)

### Dead channels and favourites

- **Mark dead** a channel that doesn't play, from the preview or from any list without playing it. Dead channels are left out of everything sent to players. [#1](https://github.com/gregfroese/STB-Proxy/pull/1), [#6](https://github.com/gregfroese/STB-Proxy/pull/6)
- **Favourites**, starred from any list or the player. [#2](https://github.com/gregfroese/STB-Proxy/pull/2)

### Playing channels

- A **preview player** docked in the corner, so pages stay usable while a channel plays. [#4](https://github.com/gregfroese/STB-Proxy/pull/4)
- **Channel up / down** (Page Up / Page Down) through the list a channel was played from. [#6](https://github.com/gregfroese/STB-Proxy/pull/6)
- **Full screen** with the controls as an overlay, and previews that start in about half a second. [#7](https://github.com/gregfroese/STB-Proxy/pull/7)
- **Now and next** in the player, and any channel's schedule from every list. [#12](https://github.com/gregfroese/STB-Proxy/pull/12)
- Previews work through a reverse proxy, and browsers behind one proxy are told apart. [#13](https://github.com/gregfroese/STB-Proxy/pull/13)
- **Multiview**: several channels at once, in layouts of 1, 2, 2 × 2 and 3 × 3, or one big tile with three small ones. The divider can be dragged, and one tile plays sound. [#24](https://github.com/gregfroese/STB-Proxy/pull/24)
- Multiview's channel picker has **Search**, **Favourites** and **Blocks** tabs. The make-big button switches back to the view you had. [#25](https://github.com/gregfroese/STB-Proxy/pull/25)

### Recording

- **Record now** from a Multiview tile or the preview player: until stopped, until the programme on now ends, or for 30 minutes to 2 hours. Recordings are saved as MP4 files that Plex and Jellyfin can use as a library. [#26](https://github.com/gregfroese/STB-Proxy/pull/26)
- A **Recordings** page: what's recording now, and what's recorded, which you can play in the browser, download or delete. [#26](https://github.com/gregfroese/STB-Proxy/pull/26)
- Recordings survive dropped streams and restarts, and keep room on the disk for their MP4. [#26](https://github.com/gregfroese/STB-Proxy/pull/26)
- **Watch a recording from the start**, or the channel **live**, while it records. Channels being recorded get a **REC** badge. [#27](https://github.com/gregfroese/STB-Proxy/pull/27)

### Guide

- A searchable **Guide** of every channel's programmes, with filters for on now, your lineup, favourites and dead channels. [#3](https://github.com/gregfroese/STB-Proxy/pull/3)
- A search language for the guide and the Playlist Editor's filter bar: whole words, word starts with, contains, exact name or regex, with "or", "leave out" and phrases. Filters can be saved by name. [#16](https://github.com/gregfroese/STB-Proxy/pull/16)

### Channel logos

- Logos matched by name from the [iptv-org](https://github.com/iptv-org/database) database, or set your own. [#14](https://github.com/gregfroese/STB-Proxy/pull/14)
- Choose each portal's logo source, and refresh logos on demand. [#21](https://github.com/gregfroese/STB-Proxy/pull/21)

### Plex and Jellyfin

- **Plex DVR sync**: lineup changes map the channels in Plex and reload its guide. [#1](https://github.com/gregfroese/STB-Proxy/pull/1)
- Syncs run one at a time and are retried when Plex can't be reached. [#17](https://github.com/gregfroese/STB-Proxy/pull/17)
- **Jellyfin**: set up its Live TV from STB-Proxy, and keep it in step with every lineup change. [#18](https://github.com/gregfroese/STB-Proxy/pull/18)
- Large lineups fit into Plex's channel map, and Jellyfin's tuner has no stream limit of its own. [#19](https://github.com/gregfroese/STB-Proxy/pull/19)

### Tuners and portal connections

- **One portal connection per channel**, shared by every player and browser preview watching it. [#20](https://github.com/gregfroese/STB-Proxy/pull/20), [#22](https://github.com/gregfroese/STB-Proxy/pull/22)
- **One tuner pool**, capped by the Tuners setting. A new channel stops a preview to make room for Plex or a recording, and players never stop each other. [#24](https://github.com/gregfroese/STB-Proxy/pull/24)

### Portals and accounts

- **Device lock** settings (model, serial, device IDs, signature) in the portal form. The portal's API address is found from whatever address you type. [#9](https://github.com/gregfroese/STB-Proxy/pull/9), [#10](https://github.com/gregfroese/STB-Proxy/pull/10)
- **Account activity** on the Dashboard: whether another app or box is using each MAC. [#15](https://github.com/gregfroese/STB-Proxy/pull/15)

### Integrations

- A JSON **API** for Home Assistant and others: status, and blocks you can switch on or off. Calls need an API token from Settings. [#17](https://github.com/gregfroese/STB-Proxy/pull/17)

### Reliability and setup

- The config can't be lost in a crash, memory use is lower, and channel switching is faster and more reliable. [#5](https://github.com/gregfroese/STB-Proxy/pull/5)
- A working Docker image and a Docker Compose quick start. The container stops promptly. [#8](https://github.com/gregfroese/STB-Proxy/pull/8), [#10](https://github.com/gregfroese/STB-Proxy/pull/10), [#11](https://github.com/gregfroese/STB-Proxy/pull/11)
- A version number in the menu (linking to this changelog), on the Settings page, in the API's status and in the log.
