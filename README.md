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


# Channel blocks

Make sets of channels available only when you want them.

- In the **Playlist Editor**, type a name in the **Block** column for each channel in the set, then **Save**. Channels with the same name form one block. A channel can be in several blocks: separate the names with commas.
- Or preview a channel and tick the blocks it belongs to, or type a new block name and click **Add**. Changes save right away.
- To sort channels into blocks quickly, switch on **Hide channels in blocks** in the editor, play the first channel, tick its block (it leaves the list) and press channel up to go on to the next one.
- On the **Blocks** page, switch a block on or off. A channel is available when it's enabled on its own **or** in any block that's on, and it isn't marked dead.
- Clear a channel's block name to take it out of the block. A block disappears when no channel uses its name.
- Click **View** next to a block to list its channels, and play any of them right there.

# Favourites

- Click the star next to a channel (on the **Blocks** page, in the **Playlist Editor**, or in the preview) to make it a favourite. Click it again to remove it.
- The **Favourites** tab on the **Blocks** page lists your favourites so you can watch them quickly. **Favourites only**, above the editor table, filters the editor to them.
- Favourites are just for finding channels. They don't change what's in the playlist or Plex.

# Preview player

- Play a channel from the editor, a block, your favourites or the guide. It plays in a panel in the corner, so the page stays usable.
- **Channel up / down** (or **Page Up / Page Down**) moves through the list you started from, as currently filtered and sorted.
- Picking another channel stops the one playing straight away, so switching is quick.
- The player shows what's on now and next under the channel name. The ☰ button (or **G**) opens the channel's schedule; in full screen it sits down the right-hand side.
- Every channel list (Playlist Editor, Blocks, Guide results) has a ☰ button that shows a channel's schedule without playing it.
- **Full screen** (the ⤢ button, **F**, or double-click the video) keeps the channel buttons, blocks and **Mark dead** on screen as an overlay. It fades after a few seconds; move the mouse to bring it back.

# Channel logos

- STB-Proxy shows channel logos in the Playlist Editor, Blocks, Guide and player, and puts them in the playlist and XMLTV (so Plex shows them too).
- Many portals send no logos. STB-Proxy then matches channels by name to the [iptv-org](https://github.com/iptv-org/database) database, which it downloads in the background when it starts and refreshes weekly (`logo-index.json` next to `config.json`). It only uses clear matches, so some channels get none.
- To set or fix one, paste an image URL into the channel's **Logo** column in the Playlist Editor and **Save**. Clearing it goes back to the automatic logo.
- **Settings → Find channel logos** turns the matching (and the download) off.

# Guide

- The **Guide** page searches the next 24 hours of programmes on every channel the portals carry, not just the ones in your lineup. Every word you type must appear in the title or description.
- Switch on **On now**, **In my lineup** or **Favourites** to narrow the results, or to browse without typing. **Hide dead** is on by default.
- Click play on a result to preview the channel. The preview has the same favourite, dead and blocks controls as everywhere else.
- The guide is fetched from the portal the first time you search (about 15 seconds) and kept for an hour. **Reload guide** fetches it again.
- If a portal has no bulk guide, only the channels in your lineup are searched.

# Dead channels

- Preview a channel and click **Mark dead** if it doesn't work, or click ⊘ next to a channel in any list to mark it dead (or working again) without playing it. Dead channels are left out of the playlist, XMLTV, HDHomeRun lineup and Plex, even if they're enabled or in a block that's on.
- **Hide dead**, above the editor table, hides them from the list. Turn it off to find them again, and use **Mark working** in the preview to bring one back.
- If a preview doesn't start, the editor suggests trying again first, since the portal may just be busy with another stream.

# Plex sync

When STB-Proxy is added to Plex as an HDHomeRun tuner, it can keep the Plex DVR's channel list up to date.

- In **Settings → Plex**, enter the Plex address (eg `http://192.168.1.10:32400`) and your Plex token. The token is never shown again; leave the field blank to keep it.
- Switching a block, marking a channel dead or working, or saving editor changes that alter which channels are available then maps those channels in Plex and reloads its guide. The **Blocks** page shows the result of the last update and has a **Sync Plex now** button.
- If a portal can't be reached, or no channels would be left, Plex is left unchanged rather than emptied.

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

# Development

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -t .
```
