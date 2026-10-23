# On Demand resume points live in their own durable SQLite file and are reported by the client

**Resume points**, **Watched** markers and **Up next** belong to an **Account** and must survive restarts, re-crawls and devices. They live in `ondemand-progress.sqlite` beside `config.json`, one row per (Account username, item). That file is **durable**: unlike `ondemand.sqlite` ([ADR 0003](0003-on-demand-local-index.md)), it is never deleted or rebuilt, and nothing in it can be re-fetched from a portal. It is `ATTACH`ed to the index connection, so browse, search and detail queries join progress in one query.

Clients report progress through `PUT /api/ondemand/progress`. The route is keyed by item, not by **On Demand session**, and reports do not count as session activity. A paused player therefore still lets its session idle out and frees its MAC slot ([ADR 0005](0005-on-demand-playback-session.md)), and the report written on pause is already on the server. **Up next** is worked out when a report is written. An Episode becoming Watched moves the Series' pointer to the next Episode, using the Season list STB-Proxy already fetched to mint the link. Episode rows also keep their Season number, Episode number and name. **Continue watching** and `upNext` then render from local data and never call the portal when read.

## Considered options

- *Store progress in `config.json` beside the Account:* rejected. `config.json` is rewritten in full and fsynced on every save, and it would be rewritten every 30 s per viewer.
- *Store it in `ondemand.sqlite`:* rejected. That file is a disposable cache, and deleting it to force a rebuild must never cost viewers their history.
- *Infer position on the server from segment requests:* rejected. It needs no client work, but it is off by the player's buffer depth and cannot see a pause.
- *Report through the session (`/session/<sid>/progress`):* rejected. The report would either keep a paused session alive, holding the portal's only slot, or fail once the session had idled out.
- *Compute Up next when read:* rejected. Continue watching would need a Seasons and an Episodes call per Series on a cold cache, on a portal that rate-limits.

## Consequences

- Rows are deleted with their Account or their portal. Rows whose item has vanished, or is now hidden, are kept and skipped wherever they don't join, so a re-crawl that brings the item back restores them.
- Resume points untouched for 180 days are pruned. Watched markers are capped at 10,000 per Account, oldest first.
