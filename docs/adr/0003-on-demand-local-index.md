# On Demand is served from a local index, not passed through to the portal

STB-Proxy crawls each enabled portal's On Demand catalogue into a SQLite file (`ondemand.sqlite`, beside `config.json`) and answers every browse, count, sort and search request from it, instead of passing list pages through to the portal. A Stalker portal pages its catalogue 14 items at a time with no bigger page size, searches actors, directors and years as well as titles, and has no year sort. Only a local index gives viewers exact counts once hidden categories are filtered out (an item can sit in up to three categories), title-only search, the same four sorts on every portal, and one merged, paged catalogue across portals. SQLite (stdlib, with FTS5) keeps the ~54k-row index on disk, so it costs a few MB of RAM on the 1 GB LXC rather than the 30–50 MB of an in-memory index.

## Considered options

- *Pass-through with a short-TTL page cache and portal-side `search=`*: rejected. Every scroll costs 0.3–0.5 s against the portal, and search results include actor matches. Filtering hidden categories leaves short pages and approximate totals, and paging "All" or search across several portals means interleaving pages from each.
- *An in-memory index of Python dicts*: rejected. Tens of MB of RAM, and it is lost on every restart, which means a ~65-minute re-crawl each time.

## Consequences

- New items appear after the next refresh, not instantly: an incremental `sortby=added` pull every 2 h, plus a full weekly re-crawl that drops removed items. The first crawl takes about an hour at 1 request/s, and viewers see a partial (newest-first) catalogue while it runs.
- A portal is only crawled once some **Account** has On Demand switched on.
- Seasons and Episodes are not crawled. They are fetched when a viewer opens a Series and cached for about 6 h, so Episode titles are not searchable.
- The file is a disposable cache: if it is lost or corrupt, a fresh crawl rebuilds it. Resume and watched state must not live in it.
