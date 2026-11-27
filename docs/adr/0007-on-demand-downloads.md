# On Demand downloads are server-side files, queued until their portal is quiet

An **Account** with its new **Downloads** switch on (operator-set, default off, like On Demand itself in [ADR 0004](0004-on-demand-visibility.md)) can ask STB-Proxy to save a **Movie**, an **Episode** or a whole **Season** as an MP4 in the **Movies folder** or **TV Shows folder** setting, typically Plex's own library folders. Files are named the way Plex and Jellyfin expect (`<Movies folder>/<Name> (<Year>)/…`, `<TV Shows folder>/<Series> (<Year>)/Season 02/<Series> (<Year>) - S02E05.mp4`). Nothing is stored on the viewer's device. The list lives in `downloads.json` beside `config.json`.

The portal plays one session per MAC and the newest wins ([ADR 0005](0005-on-demand-playback-session.md)), so a download and a viewer can't share it. Downloads therefore **give way to every viewer**:
- A download starts only once nobody has streamed from its portal for 3 minutes, one per portal at a time, oldest first.
- While it runs it holds one slot in `occupied` (kind `download`, no Tuner), so it shows on the Streams page.
- Any admission on that portal (live, preview, recording, an On Demand session) first stops the download and frees its slot, before the viewer is admitted. The download goes back to the queue, keeping the segments it had.
- It reads the HLS through an `ondemandsession.Session` (the same link handling and eviction rules as playback), appends segments to `<folder>/.stb-proxy-partial/<id>.ts` (hidden, so the library skips it; on the same disk, so the remux needs no copy), and resumes from the last whole segment. When all are in, ffmpeg remuxes the file into the library.
- An eviction by another device (a 401, 403 or 404 from storage) counts as "busy" and waits for quiet again. After 5 tries in a row that get no further, the download fails with a reason; asking again re-queues it.

Asking for an item that's already queued, running or downloaded returns that download, so there is one download per item, shared by every Account that can see it. Only the Account that asked can cancel an unfinished one; only the operator deletes a finished file.

## Considered options

- *Download to the viewer's device (browser download, offline playback in the app):* rejected for now. It needs on-the-fly HLS to MP4 serving through the BFF and offline storage in the app, for less benefit than a file Plex and Jellyfin already serve.
- *Run downloads at once and let viewers wait, or let the download win:* rejected. A download would cut off live TV, or be cut off by it every few minutes.
- *Re-mint and carry on after an eviction:* rejected for the same reason as in ADR 0005: it would evict the device that just started watching.

## Consequences

- On a portal that's busy every evening, downloads run overnight.
- A download can saturate the home connection while it runs; it only runs while nothing else streams from that portal, but other portals' viewers share the link.
- Downloaded files aren't playable in the viewer apps yet; they show up through Plex or Jellyfin.
