# Viewers reach the Guide through an account-scoped door

The operator Guide lives behind `@authorise` (`/guide/search`, `/channel/guide`) — operator-only and unscoped. Viewer clients (the companion app and the web viewer) now need to browse and search the schedule, so we exposed the Guide to **Accounts** through new routes (`GET /api/guide/search`, `GET /api/guide/channel`) guarded by `@feedAuthorise` and scoped with `viewerBlocks()`, mirroring `/api/lineup`. They reuse the existing `guide.py` engine and the single global `guideCache`, scoping per request through `search()`'s `keep()` seam (hidden-block aware, via `plexLineup(portal, viewerBlocks())`). The operator routes are untouched.

## Considered options

- *Let Accounts through the operator route* — rejected: the route applies the operator's filters (`favourites`, `lineup` using hidden-block-unaware `availableChannels`) and leaks operator-only result fields; it is the wrong scoping seam.
- *A per-account guide cache* — rejected: the schedule is the same for everyone, only the channel filter differs; a per-account copy multiplies the multi-MB cache for no benefit.
- *Keep the viewer clients on the raw `/xmltv` download* — rejected: multi-megabyte downloads per browse/search; the server door scopes and searches server-side instead (the Android now/next teaser, a best-effort single fetch, is left as-is).

## Consequences

- Two guide doors with different auth and scoping now exist; `guide.py` stays pure and shared, so the divergence lives only in each route's `keep()` predicate and result fields.
- The viewer door never exposes `refresh=true` (a global forced reload behind a viewer-triggerable route is a cache-stampede vector); the server cache stays hourly.
- The viewer search hit is self-contained but trimmed — it adds `epgId` (the clients' only programme↔channel join key) and drops the operator-only/redundant fields (`dead`, `available`, `favourite`, `blocks`, `link`), which the clients already hold from `/api/lineup`.
