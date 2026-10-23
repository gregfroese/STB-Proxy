# On Demand playback is a per-viewer session that holds a MAC slot and never re-mints on 403

Viewers reach On Demand through a third door, `/api/ondemand/*`, next to `/api/lineup` and the Guide door ([ADR 0002](0002-viewer-guide-door.md)). It is gated by `@feedAuthorise` and `viewerOnDemand()` ([ADR 0004](0004-on-demand-visibility.md)). Playback is an **On Demand session**:
- `POST /api/ondemand/play` admits the viewer, mints the portal link server-side and returns a session URL.
- STB-Proxy rewrites the portal's HLS master and media playlists so that every URI points back at `/api/ondemand/session/<sid>/…`, and passes the segments through. Storage hosts and tokens never reach a client.
- A session is never shared between viewers. It holds one **Streams Per MAC** slot but no **Tuner**, and it releases the slot after 120 s with no request or on `DELETE`.

The user's portal really allows one playback session per MAC, and the newest session wins. Re-minting a link after a 403 would then evict whoever just started playing, so **the server never re-mints mid-session**. A session that gets a 403 ends, and the client gets **410 `session_ended`** with a reason (`idle`, `evicted`, `stopped`). Clients restart silently only after `idle`, which is STB-Proxy's own timeout, and always through normal admission. After `evicted` or `stopped` the viewer has to press Resume.

## Considered options

- *Research 02's byte-Range pass-through as the media path:* rejected for v1. The live portal serves HLS (research 08), and a progressive-file path could not be tested against any portal we have. The play response carries `type` (`"hls"` for now), so a `"file"` path can be added later.
- *Transparent re-mint on 401/403/404/410, retried once (research 02):* rejected. On this portal a 403 more often means "evicted by a newer session" than "expired", and re-minting then evicts that session in turn. Two viewers could take turns killing each other.
- *Count a session as a Tuner:* rejected. A Tuner is a distinct live Channel, and Plex sizes its DVR from the Tuner count. The real limit is the per-MAC slot, and live admission already refuses Plex with 503 when that slot is taken.
- *Let the portal evict instead of refusing at admission:* rejected. The portal silently kills the older stream, while a 503 tells the viewer why.

## Consequences

- With Streams Per MAC set to the portal's real limit (1 on the user's portal), STB-Proxy never causes an eviction itself. A 403 then means another device on the MAC, or an expired token, and either way the viewer decides whether to take the slot back.
- A paused viewer loses the slot after 120 s, and a live viewer may take it in the meantime. On un-pause, the client's automatic restart can then get 503.
- Going to the next Episode passes `replaces: <sid>` so the viewer's own session hands its slot over atomically. A second device on the same Account gets 503; it does not take over.
