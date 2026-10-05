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

Install the latest Docker image with...

```
docker create \
--name=STB-Proxy \
--restart=always \
-p 8084:8001 \
-e HOST=10.0.1.200:8084 \
-v </host/path>:/config \
chris230291/stb-proxy:latest
```

- Map whichever port you like to the default `8001`
- `HOST` should be the docker hosts ip + the port you chose
- Mounting `/config` is required for settings to persist through restarts
- To configure go to the `HOST` in a browser eg 10.0.1.200:8084


# Channel blocks

Make sets of channels available only when you want them.

- In the **Playlist Editor**, type a name in the **Block** column for each channel in the set, then **Save**. Channels with the same name form one block. A channel can be in several blocks: separate the names with commas.
- Or preview a channel and tick the blocks it belongs to, or type a new block name and click **Add**. Changes save right away.
- On the **Blocks** page, switch a block on or off. A channel is available when it's enabled on its own **or** in any block that's on, and it isn't marked dead.
- Clear a channel's block name to take it out of the block. A block disappears when no channel uses its name.
- Click **View** next to a block to list its channels, and play any of them right there.

# Favourites

- Click the star next to a channel (on the **Blocks** page, in the **Playlist Editor**, or in the preview) to make it a favourite. Click it again to remove it.
- The **Favourites** tab on the **Blocks** page lists your favourites so you can watch them quickly. **Favourites only**, above the editor table, filters the editor to them.
- Favourites are just for finding channels. They don't change what's in the playlist or Plex.

# Guide

- The **Guide** page searches the next 24 hours of programmes on every channel the portals carry, not just the ones in your lineup. Every word you type must appear in the title or description.
- Switch on **On now**, **In my lineup** or **Favourites** to narrow the results, or to browse without typing. **Hide dead** is on by default.
- Click play on a result to preview the channel. The preview has the same favourite, dead and blocks controls as everywhere else.
- The guide is fetched from the portal the first time you search (about 15 seconds) and kept for an hour. **Reload guide** fetches it again.
- If a portal has no bulk guide, only the channels in your lineup are searched.

# Dead channels

- Preview a channel in the editor and click **Mark dead** if it doesn't work. Dead channels are left out of the playlist, XMLTV, HDHomeRun lineup and Plex, even if they're enabled or in a block that's on.
- **Hide dead**, above the editor table, hides them from the list. Turn it off to find them again, and use **Mark working** in the preview to bring one back.
- If a preview doesn't start, the editor suggests trying again first, since the portal may just be busy with another stream.

# Plex sync

When STB-Proxy is added to Plex as an HDHomeRun tuner, it can keep the Plex DVR's channel list up to date.

- In **Settings → Plex**, enter the Plex address (eg `http://192.168.1.10:32400`) and your Plex token. The token is never shown again; leave the field blank to keep it.
- Switching a block, marking a channel dead or working, or saving editor changes that alter which channels are available then maps those channels in Plex and reloads its guide. The **Blocks** page shows the result of the last update and has a **Sync Plex now** button.
- If a portal can't be reached, or no channels would be left, Plex is left unchanged rather than emptied.

# Device-locked portals

Some portals only accept a MAC from the device that registered it. To use one, capture what that device sends when it logs in (its serial, model and related values). Add them to `devices.json` next to `config.json`, keyed by MAC:

```json
{
  "00:1A:79:XX:XX:XX": {
    "cookies": {"timezone": "America/Toronto"},
    "headers": {"User-Agent": "...", "X-User-Agent": "Model: MAG270; Link: WiFi"},
    "handshake": {"token": "", "prehash": "..."},
    "profile": {"sn": "...", "stb_type": "MAG270", "device_id": "", "device_id2": "", "signature": "", "hw_version_2": "..."}
  }
}
```

MACs that aren't listed log in as before.

# Development

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -t .
```
