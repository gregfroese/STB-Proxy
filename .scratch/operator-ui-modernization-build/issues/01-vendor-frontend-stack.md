# 01: Vendor the front-end stack and load it locally

**What to build:** The Operator UI renders fully with no internet connection. Vendor **Bootstrap 5.3.8**, **Bootstrap Icons 1.13.2** (the icon font, with `fonts/` a sibling of the CSS so `@font-face` resolves), **jQuery 3.7.1**, and **DataTables 2.3.8 + Buttons 3.2.6** (Bootstrap-5 integration) into `static/vendor/`, using the manifest and hashes in `research/vendored-asset-recipe.md`. Switch the shared shell from the CDN tags to local `url_for('static', …)` references, and set `data-bs-theme="dark"` on `<html>`, replacing the `bg-dark`/`table-dark` hacks.

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] No CDN tags remain; every stylesheet, script and icon font loads from `static/vendor/`.
- [x] The Bootstrap Icons font resolves (the `fonts/` directory sits beside the CSS).
- [x] `data-bs-theme="dark"` is set on `<html>` and the app renders dark.
- [x] A test asserts every `vendor/…` reference resolves to a file on disk.
- [x] With the network disconnected, every page renders styled, with icons.
