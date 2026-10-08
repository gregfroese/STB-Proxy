# Multiview and recording

Date: 2026-10-08
Status: approved design, awaiting spec review

## Goal

Watch several channels at once on a Multiview page, and record channels (now, or on a
schedule) so STB-Proxy can replace Plex's DVR. Everything shares the portal's limited
connections ("tuners") through one pool with clear priorities.

## Decisions

| Topic | Decision |
| --- | --- |
| Recording's purpose | Replace Plex DVR: schedule from STB-Proxy's guide, keep files and a list of recordings here |
| Storage | A configurable recordings folder; in production a Proxmox bind mount (dataset or NAS share) into the container |
| Playback | A Recordings page that plays files in the browser, and file names a Plex/Jellyfin library understands |
| Schedules | One programme picked from the guide (with padding) and a manual slot (channel, start, duration). No series rules or repeating slots |
| Tuner conflicts | Priority Plex/Jellyfin/apps > recordings > browser previews. Higher priority may stop a lower one; nothing else is ever stopped |
| Multiview layout | A dedicated page with a tile grid; the corner preview on other pages stays as it is |
| Watching a recording | Watching the channel being recorded joins the same shared stream: one tuner |
| Stopping | Scheduled recordings can be cancelled before they start and stopped while running (keeping what was recorded) |

## Approach

A recording is a client of `/play`, like Plex: the recorder runs ffmpeg against
`http://127.0.0.1:<port>/play/<portal>/<channel>?recording=<id>`. It inherits stream
sharing, MAC selection, link fetching and fallbacks, and the tuner rules live in one place
(`/play`). The alternative, joining a `SharedStream` from inside the recorder, would
duplicate that logic.

## 1. Tuner pool

- **Capacity** is the `hdhr tuners` setting: the number of distinct channels open at once,
  across all portals. A channel shared by several viewers counts once.
- **Kinds of viewer**, decided per `/play` request:
  - preview: `web=true`
  - recording: `recording=<id>`
  - client: anything else (Plex, Jellyfin, apps)
  A shared stream's priority is the highest priority among its current viewers.
- **Admission.** A request for a channel that's already open joins it, as today. A request
  for a new channel when the pool is full frees a tuner by stopping one stream whose
  viewers are all of lower priority than the request, oldest first. If none qualifies, it
  answers HTTP 503 with `{"error": "All tuners are busy"}`.
  - Clients may stop preview-only streams.
  - Recordings may stop preview-only streams.
  - Previews never stop anything.
- **Stopped previews** end their response. The tile or player shows "<who> needed this
  tuner" with Retry. The server records why each preview stream ended, keyed by the
  browser's viewer id and tile id, and the page asks for it on error.
- **Several previews per browser.** The `stopPreview(portal, viewer)` rule (one preview
  per browser per portal) is replaced by an explicit tile id: `/play/...?web=true&viewer=<id>&tile=<n>`.
  A new preview stops only the same tile's previous one, and closing a tile frees its
  tuner at once (`linger=False`, as today).
- **Redirect stream method** (Settings → stream method not ffmpeg) bypasses sharing, so
  those streams can't be counted. The pool counts shared streams only; previews and
  recordings always use ffmpeg.
- `/streaming` and `/api/status` report each stream's viewer kinds.

## 2. Recording

### Schedule and storage

- `recordings.json` beside config.json holds scheduled, running and finished recordings,
  written atomically like config.json.
- Each recording has:
  - id, portal, channelId, channel name, title, start, stop
  - padding (before and after, applied when scheduling)
  - status: `scheduled`, `recording`, `done`, `partial`, `missed`, `cancelled`, `failed`
  - file path, size, gaps (list of start/stop of interruptions), error message
- **Settings:**
  - `recordings folder`: empty means recording is off and its controls are hidden
  - `padding before`: default 2 minutes
  - `padding after`: default 5 minutes

### Ways to record

- **Record now**, from a Multiview tile or the corner preview. It runs until stopped, or
  until an optional "stop after" duration.
- **Programme from the guide.** It records the programme's start/stop as of scheduling,
  plus padding.
- **Manual slot:** channel, start date and time, duration.
- **Overlaps.** Scheduling warns, but still schedules, when more recordings would overlap
  than there are tuners.

### Running

- A scheduler thread wakes every 15 seconds and starts due recordings.
- **Command:** each recording is one ffmpeg reading the local `/play` URL, copying video,
  encoding audio to AAC, and writing MPEG-TS to `<folder>/.partial/<id>.ts`.
- **Stream drops.** If ffmpeg ends before the stop time, the recorder reconnects and
  appends to the same `.ts`. Each gap is recorded and the status becomes `partial`.
- **No tuner (503).** The recorder retries every 30 seconds. If it never gets one before
  the stop time, the status is `missed`.
- **Finishing.** At the stop time the recorder stops ffmpeg and remuxes the `.ts` to
  `.mp4` (`-c copy -movflags +faststart`). It then deletes the `.ts`, so a remux failure
  keeps the `.ts` and sets `failed` with the error.
- **Restarts.** At startup, a recording whose window is still open resumes, with a gap
  noted. One whose window has passed is finished from its `.ts` if one exists; otherwise
  it's `missed`.

### Stopping and cancelling

- **Cancel** a scheduled recording before it starts: status `cancelled`, no file. From the
  Recordings page or by clicking the guide's record mark again.
- **Stop** a running recording: it finishes at once as above and keeps what it has.
- **Delete** a finished recording: removes its file and its entry.

### Files

- Path: `<folder>/<Title>/<Title> - YYYY-MM-DD HH.MM.mp4`. The title is the programme
  name, or the channel name for manual slots and record-now.
- Characters that aren't allowed in file names are replaced. A second recording with the
  same name gets ` (2)`.
- Plex and Jellyfin can use the folder as a library: one folder per show, dated entries.

### Recordings page (`/recordings`)

- **Scheduled tab:** upcoming and running recordings, with Cancel or Stop, and a running
  recording's elapsed time and size.
- **Recorded tab:** title, channel, date, length, size and status (with gaps for
  partial), plus Play in the browser (served with range requests), Download and Delete.
- The page shows free space in the recordings folder.
- The guide marks programmes that are scheduled. Its programme details get a Record button.

## 3. Multiview (`/multiview`)

- **Nav:** a new Multiview entry.
- **Layouts:** 1, 2 side by side, 2×2, 3×3, and "1 big + small" (big tile about two thirds
  of the width, the rest stacked; the divider can be dragged). Full window with F or a
  button.
- **Adding channels:** each empty tile has "+ Add channel", a search over the lineup (from
  `/editor_data`) with favourites first. The corner preview on other pages gets "Send to
  Multiview".
- **Remembered layout:** tiles and layout are kept in the browser's localStorage and
  reopened on load, each needing a tuner again.
- **Each tile has:**
  - video: the same fragmented-MP4 preview stream
  - header: logo, channel name, current programme and progress
  - controls:
    - ⏺ record now (red while recording, with Stop)
    - 🔊 make this tile the one with sound (only one tile is unmuted; clicking a tile
      also moves sound to it)
    - ⤢ make big
    - swap channel
    - ✕ close (frees the tuner)
- **Channel up/down** applies to the tile with sound.
- **Errors:**
  - a tile with no free tuner shows "No free tuner" and Retry
  - a preview stopped for a higher-priority viewer shows who needed the tuner, and Retry
  - other failures show the existing Retry and Mark dead panel
- **Tiles vs tuners.** There may be more tiles than tuners. Tiles on the same channel, or
  on a channel Plex is watching, share one.

## 4. Testing and rollout

- **Unit tests** in `tests/`, with ffmpeg and the portal stubbed as the current tests do:
  - pool admission and priority, including "a stream shared with a higher-priority viewer
    isn't stopped", and the 503 response
  - several previews per browser, and a tile's previous preview being stopped
  - scheduling, padding, overlap warning, cancel, stop, restart recovery, missed, partial
    and failed
  - file naming and collisions, and remux
- **Template tests** check that Multiview and Recordings render.
- **Browser checks** run against a local throwaway config. Live-portal checks only happen
  when `/streaming` is empty.
- **Memory:** each preview remux or recording ffmpeg is roughly 15–30 MB. With two tuners
  this fits the 1 GB container.
- **Shipping**, as three PRs, each deployed and merged in turn:
  1. tuner pool and Multiview
  2. record now, Recordings page, recordings settings
  3. scheduled recordings (guide and manual slot)
- **Before PR 2 is deployed:** add the bind mount for the recordings folder (which dataset
  or share to be confirmed then).

## Out of scope

- Series rules and repeating slots
- Watching a recording from the start while it is still recording (timeshift)
- Transcoding video
- Re-checking guide times for already scheduled programmes
