# STB-Proxy

- Play STB portal streams in regular m3u media players
- Responds as HD Homerun for Plex etc
- Configuration through web UI
- Combine multiple portals
- Enable/disable channels individually
- Rename channels
- Set custom genres
- Modify channel numbers
- Override epg
- Set fallback channels
- Support for multiple MACs/Streams per Portal
- Channel blocks: group channels and switch the whole group on or off
- Mark channels dead from the preview so they're hidden everywhere
- Keeps a Plex DVR's channel list in step automatically
- Works with portals that lock a MAC to a specific device


# Setup

## Quick start with Docker Compose

1. Get the code: `git clone https://github.com/gregfroese/STB-Proxy.git && cd STB-Proxy`
2. Edit `docker-compose.yml`:
   - `HOST`: this machine's LAN address and port, e.g. `192.168.1.10:8001`. It goes into the playlist, XMLTV and tuner links, so players must be able to reach it.
   - `TZ`: your time zone, e.g. `America/Edmonton`.
3. Start it: `docker compose up -d`
4. Open `http://<HOST>/` in a browser and add your portal under **Portals**. Paste the portal address your box or STB Emulator uses; STB-Proxy finds the API address behind it.

Settings and edits are kept in `./config/config.json`. If a portal locks its MACs to a device, put `devices.json` in the same folder. The container runs as root, so files it creates there belong to root.

To update: `git pull && docker compose up -d` (the compose file rebuilds the image from the new code each time).

## Docker without Compose

```
docker build -t stb-proxy .
docker run -d --name stb-proxy --restart unless-stopped \
  -p 8001:8001 \
  -e HOST=192.168.1.10:8001 \
  -e TZ=Etc/UTC \
  -v /path/to/config:/config \
  stb-proxy
```

- Map whichever host port you like to `8001`, and use that port in `HOST`.
- Mounting `/config` is required for settings to survive restarts.

## Without Docker

Needs Python 3 with Flask, Requests and Waitress, plus ffmpeg and ffprobe. Run `python3 app.py` with `HOST` set as above and `CONFIG` pointing at where `config.json` should live. It serves on port 8001.


# Finding channels in the Playlist Editor

The bar above the table filters by name, genre, block and whether a channel is enabled. Your browser remembers the filters.

- **Whole words** (the default): `TSN` finds "TSN 1 FHD" but not "SPORTSNET". **Word starts with**: `sport` finds "Sportsnet" and "Sports Max". **Contains**, **Exact name** and **Regex** are there too.
- Words must all match; a comma means "or"; `-word` leaves out; quotes keep a phrase together. For example: `TSN, "sportsnet one" -4k`.
- **Select all shown** and channel up/down follow the filters.
- **Save** keeps the current filters (and switches) under a name; pick it from **Saved filters** to apply it again, or **Delete** it. Saved filters live in `config.json`, so every browser sees them.

# Channel blocks

Make sets of channels available only when you want them.

- In the **Playlist Editor**, type a name in the **Block** column for each channel in the set, then **Save**. Channels with the same name form one block. A channel can be in several blocks: separate the names with commas.
- Or preview a channel and tick the blocks it belongs to, or type a new block name and click **Add**. Changes save right away.
- To put many channels in a block at once, tick them in the Playlist Editor (or filter the list and press **Select all shown**), type or pick the block name above the table, and press **Add to block**. **Remove from block** takes them out. Both save straight away.
- To sort channels into blocks quickly, switch on **Hide channels in blocks** in the editor, play the first channel, tick its block (it leaves the list) and press channel up to go on to the next one.
- On the **Blocks** page, switch a block on or off. A channel is available when it's enabled on its own **or** in any block that's on, and it isn't marked dead.
- Clear a channel's block name to take it out of the block. A block disappears when no channel uses its name.
- Click **View** next to a block to list its channels, and play any of them right there.
- Click ✎ next to a block to rename it. Its channels, on/off state and saved filters move to the new name.
- Click the eye next to a block to make it **STB-Proxy only**. Home Assistant and other API users don't see it, and when it's on, its channels don't go to Plex or Jellyfin (the HDHomeRun lineup, playlist and XMLTV). They still play everywhere in STB-Proxy: previews, Multiview, the guide and recordings. A channel that's also enabled on its own, or in another block that's on, still goes to Plex.

# Favourites

- Click the star next to a channel (on the **Blocks** page, in the **Playlist Editor**, or in the preview) to make it a favourite. Click it again to remove it.
- The **Favourites** tab on the **Blocks** page lists your favourites so you can watch them quickly. **Favourites only**, above the editor table, filters the editor to them.
- Favourites are just for finding channels. They don't change what's in the playlist or Plex.
- A block can have favourites of its own, apart from your overall favourites. On the **Blocks** page, click **View** on a block, then the blue bookmark next to a channel. A block's favourites come first in its list, and **Favourites only** shows just them. While a channel from that block plays in the preview player, the bookmark is in the player too, and channel up / down moves through the list you see. They don't appear in the Favourites tab.

# Preview player

- Play a channel from the editor, a block, your favourites or the guide. It plays in a panel in the corner, so the page stays usable.
- **Channel up / down** (or **Page Up / Page Down**) moves through the list you started from, as currently filtered and sorted.
- Picking another channel stops the one playing straight away, so switching is quick.
- **Send to Multiview** (▦) moves the channel to a Multiview tile, so you can watch it alongside others.
- If the preview can't get a tuner, or Plex needs the one it's using, the player says so instead of suggesting the channel is dead.
- The player shows what's on now and next under the channel name. The ☰ button (or **G**) opens the channel's schedule; in full screen it sits down the right-hand side.
- Every channel list (Playlist Editor, Blocks, Guide results) has a ☰ button that shows a channel's schedule without playing it.
- **Full screen** (the ⤢ button, **F**, or double-click the video) keeps the channel buttons, blocks and **Mark dead** on screen as an overlay. It fades after a few seconds; move the mouse to bring it back.

# Multiview

- **Multiview** (in the menu) plays several channels at once. Pick a layout: 1, 2 side by side, 2 × 2, 3 × 3, or one big tile with three small ones (drag the line between them to resize).
- Click **Add channel** in an empty tile to pick its channel: **Search** every channel by name or number (favourites, then your lineup, first), browse your **Favourites**, or open one of your **Blocks** that's switched on and pick from its channels (its favourites first; the bookmark and **Favourites only** work as on the Blocks page). A tile picked from a block keeps channel up / down within that block, or its favourites. The picker opens where you left it, so filling several tiles from one block is quick.
- One tile plays sound, outlined in yellow: click a tile (or its 🔈 button) to hear it. **Page Up / Page Down** changes that tile's channel, through your lineup.
- ⤢ makes a tile the big one; on the big tile it turns into ⤡, which goes back to the layout you had before. ⇄ changes a tile's channel, and ✕ closes it, which frees its tuner. **F** fills the window.
- Each different channel needs a tuner (see Streams and portal connections). Tiles on the same channel, or on a channel Plex is watching, share one. With more tiles than tuners, the extra tiles say **No free tuner**. If Plex needs a tuner a tile is using, the tile stops and says so. **Try again** once a tuner is free.
- Your browser remembers the tiles and layout, and opens them again next time.

# Recording

- Set **Recordings folder** in Settings → Recording to a folder STB-Proxy can write to, such as a mounted share. Empty turns recording off.
- Record from a Multiview tile or the preview player with the red ⏺ button. Choose how long: until you stop it, until the programme on now ends, or 30 minutes, 1 hour or 2 hours.
- A recording shares the channel with anything else watching it, so watching what you record uses no extra tuner. It can take a tuner from a browser preview, never from Plex or another player.
- **Recordings** (in the menu) lists what's recording now, with **Stop**, and what's recorded. You can play recordings in the browser, download them or delete them. Files are saved as `Title/Title - date time.mp4`, so Plex or Jellyfin can use the folder as a library.
- If the portal drops the stream, the recording reopens it and carries on, and the recording is marked **partial**, with the gaps noted. It also carries on after STB-Proxy restarts.
- Starting a recording needs 1 GB free in the folder, and a recording stops, keeping what it has, when less than 300 MB is left.

# Channel logos

- STB-Proxy shows channel logos in the Playlist Editor, Blocks, Guide and player, and puts them in the playlist and XMLTV (so Plex and Jellyfin show them too).
- Logos come from the portal, or are looked up by channel name in the [iptv-org](https://github.com/iptv-org/database) database, which STB-Proxy downloads in the background and refreshes weekly (`logo-index.json` next to `config.json`). The lookup only uses clear matches, so some channels get none.
- Each portal picks where its logos come from (**Portals**, open the portal, **Channel logos**):
  - **The portal's, looked up where it has none** (the default)
  - **Looked up, the portal's where none is found**: for portals whose own logos are poor
  - **The portal's only**: no lookup (and no download, if no portal uses it)
  - **Looked up only**
- **Refresh logos**, next to that choice, applies it straight away: it loads the portal's channel list and the iptv-org logos afresh, matches them again and updates Plex and Jellyfin. The portal's card then shows how many channels got a logo from where. No need to remove and add the portal again.
- To set or fix one, paste an image URL into the channel's **Logo** column in the Playlist Editor and **Save**. Your own logo always wins; clearing it goes back to the automatic one.

# Guide

- The **Guide** page searches the next 24 hours of programmes on every channel the portals carry, not just the ones in your lineup.
- The search uses the same language as the Playlist Editor's name filter: words must all match, a comma means "or", `-word` leaves out, quotes keep a phrase together. The default, **Words start with**, finds `oiler` in "Oilers" without matching `tsn` inside "Sportsnet". **Whole words**, **Contains**, **Exact title** and **Regex** are there too.
- **Channel** limits results to channels whose names match, e.g. `TSN, sportsnet -4k`. With only a channel filled in, it lists what's on those channels.
- Switch on **On now**, **In my lineup** or **Favourites** to narrow the results, or to browse without typing. **Hide dead** is on by default.
- **Save** keeps the current search under a name, as in the Playlist Editor.
- Click play on a result to preview the channel. The preview has the same favourite, dead and blocks controls as everywhere else.
- The guide is fetched from the portal the first time you search (about 15 seconds) and kept for an hour. **Reload guide** fetches it again.
- If a portal has no bulk guide, only the channels in your lineup are searched.

# Dead channels

- Preview a channel and click **Mark dead** if it doesn't work, or click ⊘ next to a channel in any list to mark it dead (or working again) without playing it. Dead channels are left out of the playlist, XMLTV, HDHomeRun lineup and Plex, even if they're enabled or in a block that's on.
- **Hide dead**, above the editor table, hides them from the list. Turn it off to find them again, and use **Mark working** in the preview to bring one back.
- If a preview doesn't start, the editor suggests trying again first, since the portal may just be busy with another stream.

# Streams and portal connections

Portals limit how many streams an account can play at once (often 1 or 2 per MAC). Set **Streams Per MAC** on the Portals page to your account's limit (0 = no limit), and **Tuners** in Settings → HDHomeRun to the total, so Plex knows too. When a portal's limit is passed, it usually cuts off the stream that has been playing longest.

Everything watching the same channel (Plex and Jellyfin, browser previews, or Jellyfin checking a channel just before playing it) shares one portal connection: STB-Proxy reads the channel once and sends it to all of them. A shared stream counts once against Streams Per MAC, and closes a few seconds after the last viewer leaves (at once when you switch a preview to another channel). The Dashboard shows how many are sharing each stream. Each player still buffers on its own, so the same channel can be a few seconds apart in Plex, Jellyfin and the browser.

**Tuners** is also how many different channels STB-Proxy opens at once, across all portals. When they're all in use and something wants a new channel, STB-Proxy makes room by stopping a browser preview, oldest first: Plex, Jellyfin and other players come before previews. A preview never stops anything, and a stream that a player is also watching is never stopped. If nothing can make room, the request gets "All tuners are busy" (HTTP 503) and a preview says **No free tuner**.

# Plex sync

When STB-Proxy is added to Plex as an HDHomeRun tuner, it can keep the Plex DVR's channel list up to date.

- In **Settings → Plex**, enter the Plex address (eg `http://192.168.1.10:32400`) and your Plex token. The token is never shown again; leave the field blank to keep it.
- Switching a block, marking a channel dead or working, or saving editor changes that alter which channels are available then maps those channels in Plex and reloads its guide. The **Blocks** page shows the result of the last update and has a **Sync now** button (Plex and Jellyfin).
- If a portal can't be reached, or no channels would be left, Plex is left unchanged rather than emptied.
- If Plex can't be reached, STB-Proxy tries again after 1, 2, 5, 10, 15 and 20 minutes.

# Jellyfin

STB-Proxy can be Jellyfin's Live TV source and keep it up to date.

1. In Jellyfin, make an API key under **Dashboard → API Keys**.
2. In STB-Proxy's **Settings → Jellyfin**, enter the Jellyfin address (eg `http://192.168.1.10:8096`) and the key, and **Save**.
3. Press **Set up Jellyfin Live TV**. It adds STB-Proxy to Jellyfin as an M3U tuner (`/playlist`) and an XMLTV guide (`/xmltv`), unless they're there already, and loads the channels.

From then on, anything that changes the lineup (blocks, dead marks, editor saves, the API) also has Jellyfin reload its channels and guide, with the same retries as Plex. Pressing **Set up** again reloads them too.

# Device-locked portals

Some portals only accept a MAC from the device that registered it. If adding a portal says it refused your MAC, but the MAC works on your box or in STB Emulator:

1. Edit the portal (or add it again) and switch on **Device lock**.
2. Fill in the box's **model and serial number**; many portals check only those. In STB Emulator they're under Settings → Profiles → your profile → STB configuration. On a MAG box, the serial number is in Settings → System information.
3. Save. If the portal still refuses the MAC, add the device ID, device ID 2 and signature from the same screen. Make one change at a time: some portals briefly refuse logins after several in quick succession.
4. Once it's accepted, STB-Proxy logs in with those details from then on.

Some portals check more than that: values only the box's own login reveals, captured from its traffic. Put those in **Advanced** as JSON.

The details are saved in `devices.json` next to `config.json`, keyed by MAC. You can also edit that file directly:

```json
{
  "00:1A:79:XX:XX:XX": {
    "cookies": {"timezone": "Europe/London"},
    "headers": {"User-Agent": "...", "X-User-Agent": "Model: MAG254; Link: Ethernet"},
    "handshake": {"token": "", "prehash": "..."},
    "profile": {"sn": "...", "stb_type": "MAG254", "device_id": "", "device_id2": "", "signature": "", "hw_version_2": "..."}
  }
}
```

MACs that aren't listed log in as before.

# Account activity

The **Dashboard** shows, for each MAC, whether anything else is using it: another STB-Proxy, an app, or a box or emulator. Portals don't say who else is connected, but each profile request reports when the account's previous one was, and real boxes check in and report what they're playing. STB-Proxy compares that with its own requests whenever it logs in. **Check now** asks the portal straight away.

# Home Assistant and other integrations

STB-Proxy has a small JSON API under `/api/`. Every call needs the API token from **Settings → Integrations**, sent as `Authorization: Bearer <token>` (or an `X-API-Key` header). **New token** there replaces it.

| Call | What it does |
| --- | --- |
| `GET /api/status` | Lineup size, active streams, tuners in use, viewers by kind (client, recording, preview), blocks, last Plex sync, and whether anything else is using your MACs |
| `GET /api/blocks` | Every block: name, on or off, channel and dead counts |
| `GET /api/blocks/<name>` | One block (the name ignores case) |
| `POST /api/blocks/<name>` with `{"enabled": true}` or `false` | Switch a block on or off |
| `POST /api/blocks/<name>/on`, `/off`, `/toggle` | The same, without a body |
| `GET /api/plex`, `GET /api/jellyfin` | The last Plex sync or Jellyfin refresh, and when it will try again if it failed |
| `POST /api/sync` | Update Plex and Jellyfin now (`/api/plex/sync` does the same) |

Blocks made **STB-Proxy only** on the **Blocks** page are left out of every call: they aren't listed, `/api/blocks/<name>` answers 404 for them, and their channels don't count in `lineup`.

Switching a block updates Plex and Jellyfin, and the reply says whether that worked. If one can't be reached (say it's restarting), STB-Proxy tries again after 1, 2, 5, 10, 15 and 20 minutes. Syncs run one at a time, so a burst of changes ends in one sync with the final state.

Example `configuration.yaml` (put `Bearer <your token>` in `secrets.yaml` as `stb_proxy_auth`):

```yaml
switch:
  - platform: rest
    name: NHL block
    resource: http://192.168.1.10:8001/api/blocks/NHL
    body_on: '{"enabled": true}'
    body_off: '{"enabled": false}'
    is_on_template: "{{ value_json.enabled }}"
    headers:
      Authorization: !secret stb_proxy_auth
      Content-Type: application/json

rest_command:
  stb_proxy_sync_plex:
    url: http://192.168.1.10:8001/api/sync
    method: post
    headers:
      Authorization: !secret stb_proxy_auth

rest:
  - resource: http://192.168.1.10:8001/api/status
    scan_interval: 60
    headers:
      Authorization: !secret stb_proxy_auth
    sensor:
      - name: STB-Proxy lineup channels
        value_template: "{{ value_json.lineup }}"
      - name: STB-Proxy active streams
        value_template: "{{ value_json.streams }}"
    binary_sensor:
      - name: STB-Proxy Plex in sync
        value_template: "{{ value_json.plex.ok }}"
      - name: STB-Proxy account shared
        value_template: "{{ value_json.otherLogins > 0 or value_json.boxOn }}"
```

# Development

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -t .
```

Versions follow [SemVer](https://semver.org): every change that ships bumps `VERSION` in `version.py` (minor for new features, patch for fixes), adds its entry at the top of [CHANGELOG.md](CHANGELOG.md), and is tagged `vX.Y.Z` with a GitHub release. A test checks that the changelog's newest entry matches `version.py`. STB-Proxy shows its version in the menu (linking to the changelog), on the Settings page, in `/api/status` and in the startup log.
