# Channel blocks, dead channels and Plex sync

Date: 2026-10-02
Status: approved in conversation, pending spec review

## Goal

Make sets of channels available on demand and keep broken channels out of the way:

- **Blocks**: name a set of channels and switch the whole set on or off in one click.
- **Dead channels**: mark a channel dead while previewing it, so it's hidden everywhere until unmarked.
- **Plex sync**: whenever the set of available channels changes because of a block switch or a dead mark, update the Plex DVR to match, so channels appear in or disappear from Plex without manual re-mapping.

Success means switching on a block makes its channels show up in Plex with guide data within about a minute, switching it off removes them, and a dead channel never reaches Plex, all without visiting Plex's DVR settings.

## Context

- STB-Proxy runs in LXC 115 at `192.168.5.71:8001`. This repo (`/code/stb-proxy`) is the source of truth and is deployed to `/opt/stb-proxy/app` there.
- Plex (`192.168.5.3:32400`) has DVR key 2 using STB-Proxy as an HDHomeRun tuner (device key 1) and `http://192.168.5.71:8001/xmltv` as its guide. Plex maps tuner channels by `GuideNumber` to XMLTV channel ids. STB-Proxy's XMLTV id for a channel is its custom EPG id or `portalId + channelId`.
- `loadConfig()` drops any per-portal or settings key not declared in `defaultPortal` / `defaultSettings`, and replaces empty values with the default. New keys must be declared there.
- `/settings/save` rebuilds settings from the form, treating every missing field as `"false"`.
- `/play/<portal>/<channel>` serves any channel whether or not it's enabled. Previews rely on this, and so does unmarking a dead channel.

## Rules for which channels are available

A channel is **available** when:

```
(individually enabled  OR  in a block that is on)  AND NOT dead
```

- A channel belongs to at most one block.
- Marking a channel dead or alive never changes its enabled switch or block membership.
- One helper, `availableChannels(portal)`, implements this rule. `/lineup.json`, `/xmltv` and `/playlist` all use it in place of reading `"enabled channels"` directly. No other code works out availability.

## Data model (config.json)

Per portal, declared in `defaultPortal`:

- `"channel blocks": {channelId: blockName}`: block membership, in the same style as `"custom genres"`.
- `"dead channels": [channelId, ...]`

Top level, ensured by `loadConfig()` with `setdefault`:

- `"blocks": {blockName: "true" | "false"}`: whether each block is on. A block exists while at least one channel names it. Saving the editor removes entries for blocks no channel names any more. A block with no entry is off.

Settings, declared in `defaultSettings`:

- `"plex url"`: default `""`, e.g. `http://192.168.5.3:32400`
- `"plex token"`: default `""`

Plex sync is enabled when both are set.

## Web interface

### Playlist editor (`editor.html`, `/editor_data`, `/editor/save`)

- **New "Block" column:** a text input like the Genre column. Edits are collected in a `blockEdits` list and saved by the existing Save button through `/editor/save`. An empty value removes the channel from its block.
- **Dead badge:** a red "dead" badge next to the channel name for dead channels. `/editor_data` adds `block` and `dead` fields to each row.
- **"Hide dead" toggle:** above the table, on by default. It's a client-side DataTables filter.
- **Preview pop-up:**
  - A "Mark dead" / "Mark working" button. It calls `POST /channel/dead` straight away, without the Save button, then updates the badge in the row and the button label.
  - If the `<video>` element fires `error`, or hasn't fired `playing` 15 seconds after opening, the pop-up shows "This channel didn't play. Mark it dead?" with a button that does the same as "Mark dead". Nothing is marked automatically.
- **Plex sync after the editor's Save:** if the save changed the set of available channels (enabled switches or block membership), it triggers a Plex sync. The result is shown with the existing flash message.

### Blocks page (`blocks.html`, new nav item "Blocks")

- **Listing:** one row per block, sorted by name, showing:
  - the name
  - the channel count and dead count, e.g. "12 channels (2 dead)"
  - an on/off switch
- **Sync status:** above the list, the time and outcome of the last Plex sync, and a "Sync Plex now" button. The status lives only in memory: a restart clears it.
- **Empty state:** with no blocks, the page explains how to create one by typing a block name in the editor's Block column.

### Settings (`settings.html`)

- **New "Plex" section:** a URL field and a token field.
  - The token field is a password input and is never filled with the saved value.
  - Leaving it blank keeps the saved token. `/settings/save` special-cases `"plex token"` so it isn't overwritten with an empty value.
- **Clearing the token:** a "Clear token" checkbox.

## Routes

| Route | Method | Purpose |
|---|---|---|
| `/blocks` | GET | Blocks page |
| `/blocks/toggle` | POST | Form fields `name`, `enabled`. Saves, syncs Plex, then flashes the result and redirects to `/blocks` |
| `/blocks/sync` | POST | Syncs Plex now, then flashes the result and redirects to `/blocks` |
| `/channel/dead` | POST | Form fields `portal`, `channelId`, `dead` (`"true"`/`"false"`). Saves, syncs Plex if the channel's availability changed, then returns JSON `{"dead": bool, "plex": "<outcome message>"}` |

All routes use `@authorise`, like the existing ones.

## Plex sync (`plex.py`)

`plex.py` is a small module with no Flask dependency. It exports `sync(plexUrl, token, tunerUri, lineupEntries) -> str` and raises `PlexSyncError` with a readable message on failure.

1. **Find the DVR:** `GET {plexUrl}/livetv/dvrs`, and pick the DVR with a `Device` whose `uri` equals `tunerUri` (`"http://" + host`). Take its device `key`.
   - No match → `PlexSyncError("No Plex DVR uses this tuner")`.
2. **Update the channel map:** `PUT {plexUrl}/media/grabbers/devices/{deviceKey}/channelmap` with:
   - `channelMappingByKey[<GuideNumber>]=<epgId>` and `channelMapping[<GuideNumber>]=<epgId>` for every available channel
   - `channelsEnabled=<comma-separated GuideNumbers>`

   The map comes from STB-Proxy's own data, not from Plex's suggestions.
3. **Reload the guide:** `POST {plexUrl}/livetv/dvrs/{dvrKey}/reloadGuide`.
4. **Return** e.g. `"Plex updated: 17 channels enabled"`.

All requests:
- send `X-Plex-Token` and `Accept: application/json`
- use a 30-second timeout
- treat a non-2xx status as a `PlexSyncError` that includes the status code

### Shared lineup builder

`lineupEntries` comes from a new `buildLineup()` in `app.py` that returns `GuideNumber`, `GuideName`, `URL` and `epgId` for every available channel. `/lineup.json` uses the same builder, without `epgId`, so Plex sync and the HDHomeRun lineup always agree.

### When a sync runs

A sync runs synchronously within the triggering request. It takes a few seconds: Plex calls back into STB-Proxy for `lineup.json` while the sync is in progress, and Waitress's 24 threads allow that.

### If the sync fails

- The STB-Proxy change is already saved and stays in effect.
- The error is logged and recorded as the last sync outcome.
- The user sees a warning flash, or the JSON `plex` message for `/channel/dead`.
- Retrying is manual, with "Sync Plex now".

### To confirm during implementation

Check whether Plex accepts mappings for tuner channels it hasn't seen yet from a channel map update alone. If it needs to refresh the tuner's channel list first, find the API call that does this (the Plex web app's "scan channels" request) and add it as step 1b.

## Security

- **Token storage:** the Plex token is stored unencrypted in `config.json`, inside the LXC.
- **Token display:** it's never sent back to the browser.
- **No login by default:** STB-Proxy's built-in login is off, so anyone on the LAN can use the new switches. This design leaves that unchanged; enabling the login is a separate decision.

## Testing

- **Unit tests** in `tests/`, run with `python3 -m unittest` and needing no new dependencies:
  - `availableChannels`: the enabled/block/dead combinations, including a dead channel in a block that's on, and a channel enabled individually while its block is off
  - `plex.py`: DVR selection by tuner URI, and the channel map query it builds. Mock the HTTP calls; don't hit a real server.
  - Settings save keeps the Plex token when the field is blank.
- **End-to-end checks** against the live LXC and Plex:
  1. Create a 2-channel test block and switch it on. Check `lineup.json`, `/xmltv`, and Plex's DVR channel map for the 2 new channels, each with the correct guide id, and that the guide reload imports programmes for them.
  2. Switch it off. Check that the channels are gone from all three and that the existing 15 channels are unchanged.
  3. Mark an enabled channel dead, check it's gone from Plex, then unmark it and check it's back.
  4. Point `plex url` at an unreachable address. Check that a block switch still applies, the warning appears, and "Sync Plex now" reports the error. Then restore the address.
  5. Remove the test block.

## Deployment

- **Source of truth:** `/code/stb-proxy` holds the code.
- **Deploy:** fast-forward `/opt/stb-proxy/app` from a git bundle, then run `systemctl restart stb-proxy`.
- **Config:** `config.json` and `devices.json` stay only in `/opt/stb-proxy/config`, outside the repo.
- **Git hygiene:** add a `.gitignore` for `__pycache__/` and `STB-Proxy.log`.

## Out of scope

- Scheduling blocks to switch on or off automatically
- Detecting dead channels automatically
- A channel belonging to more than one block
- Enabling STB-Proxy's login
