# Changelog

STB-Proxy is a fork of [Chris230291/STB-Proxy](https://github.com/Chris230291/STB-Proxy), which had no version numbers. Version 1.0.0 is everything added since the fork. From here on, every change bumps the version: the minor number for new features, the patch number for fixes.

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
