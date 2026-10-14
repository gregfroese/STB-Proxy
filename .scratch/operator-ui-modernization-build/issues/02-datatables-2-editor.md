# 02: Upgrade the Playlist Editor to DataTables 2

**What to build:** The Playlist Editor's grid keeps working on DataTables 2. Migrate the `dom:` string to a `layout:` config, recreating the three custom bars (`dead-filter`, `filter-bar`, `bulk-bar`) as named `div` features that `initComplete` continues to fill, preserving the visual order (buttons + dead-filter, then search + length; filter bar; bulk bar; table; info + pager). Keep `buttons`, the custom `ext.search`/`ext.order` plugins and the `orderDataType` defs, and set `deferRender: false` so v1's always-present row nodes are preserved. First grep templates and static for DataTables-1 class names (`dataTables_`, `sorting_`, `paginate`) — DT2 renamed them to a `dt-` prefix — and migrate any found.

**Blocked by:** 01 (vendored DataTables 2).

**Status:** resolved

- [x] The filter bar, bulk bar and dead-filter render in the same visual order as before.
- [x] Search, length menu, info and pager all work.
- [x] Row selection, bulk add/remove and dead filtering behave exactly as before.
- [x] No DataTables-1 class names remain in templates or static.
- [x] The editor is fully usable; the existing test suite is green.
