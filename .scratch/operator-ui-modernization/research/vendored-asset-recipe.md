# Research: vendored asset recipe

Ticket: `.scratch/operator-ui-modernization/issues/02-research-vendored-asset-recipe.md`
Status: research complete (fact-finding only — no application code/templates changed)
Researched: 2026-10-13

Goal: the concrete recipe for vendoring and upgrading the Operator UI's front-end
assets, pinned to versions and exact figures, to feed the modernisation spec.

All hashes below were obtained by downloading the exact file and computing the
digest with `openssl dgst -sha384 -binary | openssl base64 -A`, except where marked
*vendor-published* (Bootstrap's docs publish SRI; cdnjs publishes sha512; DataTables
and the Bootstrap Icons npm dist publish none per-file). Nothing here is invented.

## Key decisions (summary)

- Pin **Bootstrap 5.3.8** (latest 5.3.x), **Bootstrap Icons 1.13.2**, **jQuery 3.7.1**,
  **DataTables 2.3.8 + Buttons 3.2.6 (Bootstrap 5 integration)**.
- Vendor the **Bootstrap Icons icon font** (`bootstrap-icons.min.css` + `woff2`/`woff`),
  not the SVG sprite. Reason: the repo already uses `<i class="fa fa-…">` in ~hundreds of
  places; the font keeps that `<i>` pattern (`<i class="bi bi-…">`), whereas the sprite
  forces every icon to become an inline `<svg><use></svg>`. The sprite is documented as the
  fallback/no-webfont option but is **not** the recommendation. Full FA→BI name mapping is
  ticket #04, out of scope here.
- Vendor **DataTables' combined build** (2 files) plus **jQuery as its own file**. DataTables 2.x
  combined builds **no longer bundle jQuery** (the `jq-…` path segment is gone; the URL 404s),
  so jQuery must be loaded separately. This is a change from the current `dt-1.11.3` build.
- Buttons pairing: **Buttons 2.x pairs with DataTables 1.x; Buttons 3.x pairs with DataTables 2.x.**
  (`datatables.net-buttons-bs5@2.4.3` depends on `datatables.net-bs5@^1.13.0`; `@3.2.6` on `^2`.)
  The current template bundles Buttons 2.0.1; both must move to the v3 line together with DT2.
- The `dom:` string in `editor.html` still *works* in DataTables 2 but DataTables 2's default CSS
  no longer styles `dom` output; migrate to `layout:`. The custom plugin hooks
  (`$.fn.dataTable.ext.search` / `.ext.order` / `orderDataType`) all still work.

## Vendored file manifest

Recommended set. "References" is the current CDN `<link>`/`<script>` the vendored file replaces.

| Vendored file | Version | Download URL | SRI (sha384) | What references it |
|---|---|---|---|---|
| `bootstrap/bootstrap.min.css` | 5.3.8 | `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css` (or `https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/5.3.8/css/bootstrap.min.css`) | `sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB` *(vendor-published & verified)* | `templates/base.html:10-11` (currently BS 5.0.1 cdnjs) |
| `bootstrap/bootstrap.bundle.min.js` | 5.3.8 | `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js` (or `https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/5.3.8/js/bootstrap.bundle.min.js`) | `sha384-FKyoEForCGlyvwx9Hj09JcYn3nv7wiPVlz7YYwJrWVcXK/BmnVDxM+D2scQbITxI` *(vendor-published & verified)* | `templates/base.html:14-15` (currently BS 5.0.1 cdnjs) |
| `jquery/jquery.min.js` | 3.7.1 | `https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js` (or `https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js`) | `sha384-1H217gwSVyLSIfaLxHbE7dRb3v4mYCKbpQvzx0cegeju1MVsGrX5xXxAvs/HgeFs` *(computed; matches cdnjs sha512 dist)* | New file (jQuery 3.6.0 is currently bundled inside the DT 1.11.3 build) |
| `datatables/datatables.min.css` | DataTables 2.3.8 + Buttons 3.2.6 (bs5) | `https://cdn.datatables.net/v/bs5/dt-2.3.8/b-3.2.6/datatables.min.css` | `sha384-sm1mfSf79YhYg4t+lCBxHTXU9bnJw/Sjh5nysQj17a2QIKaDDSd7q30k7EY4J64j` *(computed; not vendor-published)* | `templates/base.html:12-13` (currently `dt-1.11.3/b-2.0.1`) |
| `datatables/datatables.min.js` | DataTables 2.3.8 + Buttons 3.2.6 (bs5) | `https://cdn.datatables.net/v/bs5/dt-2.3.8/b-3.2.6/datatables.min.js` | `sha384-cZizn6ftjzg0dgcJA6fGRRE7qrZwMvYOiKPok5OaU2EXm3xF2y9sAl+/Q+zv0SpH` *(computed; not vendor-published)* | `templates/base.html:16-17` (currently `dt-1.11.3/b-2.0.1`) |
| `bootstrap-icons/bootstrap-icons.min.css` | 1.13.2 | `https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.2/font/bootstrap-icons.min.css` | `sha384-nWN3KqaaVcbEsCjLSV+2jMjh62Iny/+mN3srM8TZeM8N6aj7eDl5wwYggjAJ4/sJ` *(computed)* | New (replaces Font Awesome 4.7.0 at `templates/base.html:9`) |
| `bootstrap-icons/fonts/bootstrap-icons.woff2` | 1.13.2 | `https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.2/font/fonts/bootstrap-icons.woff2` | `sha384-3244+MXg/RYJtpyex6rHizzzKnMvpfOn/NclFlkM8AIgKtYHT8CLQEJx6xyDFEpr` *(computed)* | Loaded by `bootstrap-icons.min.css` `@font-face` |
| `bootstrap-icons/fonts/bootstrap-icons.woff` | 1.13.2 | `https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.2/font/fonts/bootstrap-icons.woff` | `sha384-djaUP7PFk2XOEMATfi4TSaFL2X2190OquAlsbym0RbgKyPKjHvXKFm72Jfno/5VC` *(computed)* | Fallback in `bootstrap-icons.min.css` `@font-face` |

Optional (sprite path — only if the sprite route is chosen later):

| Vendored file | Version | URL | SRI (sha384) | References |
|---|---|---|---|---|
| `bootstrap-icons/bootstrap-icons.svg` | 1.13.2 | `https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.2/bootstrap-icons.svg` | `sha384-HDv2crLaPKyghfZjB7DNlE8jDRt4s/wavUBYv9QrO+9zYO7PMkcgEOQkF3Pl8i5P` *(computed)* | none yet (would replace the font) |

Notes on sourcing:

- Bootstrap 5.3.8 and jQuery 3.7.1 bytes are **identical** on cdnjs and jsDelivr (verified with
  `cmp`); the SRI values above are valid for both CDNs. Bootstrap's own docs page publishes
  `sha384-sRIl4kx…` and `sha384-FKyoEF…`, matching the computed values.
- **DataTables publishes no SRI** for the download-builder/combined output (checked
  `https://datatables.net/download/` — no `integrity=` anywhere). The two DataTables hashes are
  our own computation over the served bytes; the bytes were confirmed stable across two downloads.
- **cdnjs has Bootstrap Icons only up to 1.13.1**; 1.13.2 is only on npm/jsDelivr/GitHub releases.
  Use jsDelivr for 1.13.2. (cdnjs 1.13.1 sha512 for `font/bootstrap-icons.min.css` is
  `sha512-t7Few9xlddEmgd3oKZQahkNI4dS6l80+eGEzFQiqtyVYdvcSG2D3Iub77R20BdotfRPA9caaRkg1tyaJiPmO0g==`
  if you prefer cdnjs, but then you are a patch behind.)

### Alternative: individual DataTables files instead of the combined build

If the combined (server-generated) bundle is unwanted, vendor the npm dist files individually.
All hashes below computed from jsDelivr/npm dist:

| File | Version | URL | SRI (sha384) |
|---|---|---|---|
| `dataTables.min.js` | 2.3.8 | `https://cdn.jsdelivr.net/npm/datatables.net@2.3.8/js/dataTables.min.js` | `sha384-vKSHfmUIK/B5LfOmzrP+424efQhNcgZm+sqxgq/DNCicqQRp/V6pVc4HCaRzeQZw` |
| `dataTables.bootstrap5.min.js` | 2.3.8 | `https://cdn.jsdelivr.net/npm/datatables.net-bs5@2.3.8/js/dataTables.bootstrap5.min.js` | `sha384-3BApNGXgbm9rg2kjIbaEVprAGb2B0n9QyLjBrH090WdkzZ3IiUv8RZoTh5uP8oWH` |
| `dataTables.bootstrap5.min.css` | 2.3.8 | `https://cdn.jsdelivr.net/npm/datatables.net-bs5@2.3.8/css/dataTables.bootstrap5.min.css` | `sha384-q6bAgUAsga3oT16XWJ1toXdKcHmBp45jM5roe3RCQ6dET9xGL89Qmpx4tJAI2pm2` |
| `dataTables.buttons.min.js` | 3.2.6 | `https://cdn.jsdelivr.net/npm/datatables.net-buttons@3.2.6/js/dataTables.buttons.min.js` | `sha384-ygalescEL33A7N+7n2CN65lzwzfLzQNVWNhHDnAUGLiE1RyuaOQ+kI2PhRsTzEGV` |
| `buttons.bootstrap5.min.js` | 3.2.6 | `https://cdn.jsdelivr.net/npm/datatables.net-buttons-bs5@3.2.6/js/buttons.bootstrap5.min.js` | `sha384-On2xzKFvlU9eQtoj28QB5HxGDlGu9UPIBH/YErXnCbrfRJ6KSyq7W2I7onXRvANY` |
| `buttons.bootstrap5.min.css` | 3.2.6 | `https://cdn.jsdelivr.net/npm/datatables.net-buttons-bs5@3.2.6/css/buttons.bootstrap5.min.css` | `sha384-HI7qMf1hznIZrIds5RatHHAOCn/7uGgsYQCanIyCeJDebKwCnoWnm4cB9SH+Z/ab` |

Download-builder equivalent URL: `https://datatables.net/download/#bs5/dt-2.3.8/b-3.2.6`
(the combined CDN URL header states `Included libraries: DataTables 2.3.8, Buttons 3.2.6`;
jQuery is deliberately not part of it).

## `static/vendor/` layout

Flask serves `static/` at `/static/` by default (`app = Flask(__name__)`, `app.py:40`), so the
existing `url_for('static', …)` pattern already resolves correctly. Proposed tree:

```
static/
  vendor/
    bootstrap/
      bootstrap.min.css
      bootstrap.bundle.min.js
    bootstrap-icons/
      bootstrap-icons.min.css
      fonts/
        bootstrap-icons.woff2
        bootstrap-icons.woff
    datatables/
      datatables.min.css
      datatables.min.js
    jquery/
      jquery.min.js
```

Reference pattern in templates (mirrors the existing `channel-filter.js` includes):

```html
<link rel="stylesheet" href="{{ url_for('static', filename='vendor/bootstrap/bootstrap.min.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='vendor/bootstrap-icons/bootstrap-icons.min.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='vendor/datatables/datatables.min.css') }}">

<script src="{{ url_for('static', filename='vendor/jquery/jquery.min.js') }}"></script>
<script src="{{ url_for('static', filename='vendor/bootstrap/bootstrap.bundle.min.js') }}"></script>
<script src="{{ url_for('static', filename='vendor/datatables/datatables.min.js') }}"></script>
```

(`base.html` currently uses relative `../static/tv.png` hrefs at lines 8 and 24; those are a
pre-existing wart, not part of this ticket.)

## Bootstrap Icons: font vs sprite

**Recommendation: icon font.** The repo has ~hundreds of Font Awesome `<i class="fa fa-…">`
tags; the font path changes only the class names, keeping the `<i>` element. The sprite path
requires rewriting every icon to `<svg><use/></svg>` — far more markup churn, and the map
freezes behaviour / favours presentation-only changes.

### Icon font reference pattern

```html
<link rel="stylesheet" href="{{ url_for('static', filename='vendor/bootstrap-icons/bootstrap-icons.min.css') }}">
...
<i class="bi bi-alarm" aria-hidden="true"></i>
```

### Vendoring the font without breaking `@font-face` `url()` paths

`bootstrap-icons.min.css` declares (verbatim, v1.13.2):

```css
@font-face{font-display:block;font-family:bootstrap-icons;
  src:url("fonts/bootstrap-icons.woff2?e34853135f9e39acf64315236852cd5a") format("woff2"),
      url("fonts/bootstrap-icons.woff?e34853135f9e39acf64315236852cd5a") format("woff")}
```

The `url()` values are **relative to the stylesheet's own location** and include a cache-busting
query string. Two rules keep them working:

1. Preserve the `fonts/` subdirectory **next to** the CSS file — i.e. keep the package's
   `font/bootstrap-icons.min.css` + `font/fonts/bootstrap-icons.woff2` relative shape. Placing
   the CSS in `vendor/bootstrap-icons/` therefore requires the fonts in
   `vendor/bootstrap-icons/fonts/` (exactly the tree above). Do **not** flatten them up one level.
2. Keep the filenames exactly `bootstrap-icons.woff2` / `bootstrap-icons.woff`. The `?e348531…`
   query string can stay as-is: Flask's static route matches on path and ignores the query, so the
   local file resolves.

If you must relocate the CSS away from its `fonts/` sibling, edit the two `url()` values; the
sprite route (below) is the alternative that avoids webfonts entirely.

### SVG sprite reference pattern (the no-webfont alternative, not recommended here)

Serve `bootstrap-icons.svg` from your own origin (cross-origin sprites are restricted by some
browsers; the upstream README says to serve it with your app):

```html
<svg class="bi" width="1em" height="1em" fill="currentColor" aria-hidden="true">
  <use href="{{ url_for('static', filename='vendor/bootstrap-icons/bootstrap-icons.svg') }}#alarm"></use>
</svg>
```

## DataTables 1.11 → 2.x migration (relevant to `templates/editor.html`)

Source: DataTables "Upgrading to DataTables 2 from 1.10+" (`https://datatables.net/upgrade/2`),
`layout` reference, `columns.orderDataType` reference, and the Search manual.

### `dom:` → `layout:` (`editor.html:443`)

- `dom` is **still supported** in DataTables 2 (kept for backwards compatibility; slated for
  removal "in v3"), so the existing string will not throw. **But** DataTables 2's default CSS was
  rewritten for `layout` and no longer styles `dom`-generated wrapper elements — the current
  editor toolbar would lose its layout/styling. Migrate to `layout`.
- `dom` and `layout` are mutually exclusive; use one.
- The current `dom` string is not just positioning: it injects three custom containers
  (`div.filter-bar`, `div.bulk-bar`, `div.dead-filter`) that `initComplete` then fills via
  `$('div.filter-bar').html(...)` etc. `layout` has no direct `<'class' …>` equivalent. Two options:
  - Use `layout` **function values** (supported: a function returning a DOM node, or a
    `DataTable.Dom`/jQuery/node instance) to create those three containers, e.g. place one at
    `top2Start`/`top`; keep the `initComplete` fills.
  - Or register the custom bars with `DataTable.feature.register(...)` (the v2 way to add
    features usable in `layout`).
  - `Buttons`, `search`, `pageLength`, `info`, `paging` map directly to `layout` features
    (`topStart`, `topEnd`, `bottomStart`, `bottomEnd`).
- `orderFixed`, `order`, `pageLength`, `columnDefs`, `language`, `buttons`, `ajax`, `columns`
  and `initComplete` remain valid.

### Custom plugins still work

- `$.fn.dataTable.ext.search.push(...)` (`editor.html:413-416`): **retained** in DataTables 2 for
  backwards compatibility (`DataTable.ext.search` still exists; `$.fn.dataTable` remains as the
  jQuery alias). The docs discourage it for new work and recommend `search.fixed()` /
  functional searches instead, but the existing hook is expected to keep functioning.
- `$.fn.dataTable.ext.order['dom-checkbox' | 'dom-text' | 'dom-text-numeric']`
  (`editor.html:419-439`): the `DataTable.ext.order` plug-in map still exists, and these are the
  canonical "Live DOM ordering" plug-ins from the DataTables docs. Unchanged.
- `orderDataType` column defs (`editor.html:503-513`): **still supported** — the option is
  documented as "Since: DataTables 1.10" with current v2 examples, and there are still no
  built-in `orderDataType` plugs (they remain separately registered, as here).
- Class-name caveat: DataTables 2 renamed its own generated element classes to a consistent
  `dt-` prefix. Any repo CSS/JS that targets old DataTables 1.x class names must be updated
  (needs an audit of the templates/`static/*.js`; none seen in `base.html`).

### Behaviour changes to watch (not just styling)

- **`deferRender` now defaults to `true`.** Code that assumes every row has a DOM node —
  `table.rows().nodes()` used in `showSelection()` (`editor.html:196`), `channelNodes()`
  (`editor.html:179-181`), and the `$(table.rows().nodes()).find(...)` calls at
  `editor.html:136,166,196,251,259` — may see only rendered rows. Options: set
  `deferRender: false` to preserve the v1 behaviour, or verify each site. This is a runtime
  behaviour risk, not a presentation one.
- **Order sequence** now includes a third "no order" state on header click. The editor pins
  ordering via `orderFixed`/`order`, so impact is likely nil, but check header-click UX.
- `striped` classes (`odd`/`even`) removed — the repo uses Bootstrap's `table-striped`, so fine.

## Bootstrap 5.0 → 5.3 notes for the classes this repo uses

Sources: Bootstrap 5.3 migration page and Navbar/Color-modes docs.

- **`navbar-light`** (`base.html:21`): deprecated since v5.2 (navbar theming moved to CSS
  variables; light is the default). It is **not removed** in 5.3 but it is redundant — drop it.
  Its dark counterpart `.navbar-dark` was deprecated in v5.3 in favour of `data-bs-theme="dark"`
  on the `.navbar`. Navbars still require a `.container*` child (unchanged here).
- **`form-switch`** (`editor.html:9`, `settings.html` many, and JS-generated switches): exists
  since 5.0; markup unchanged. In 5.3 it is driven by CSS variables (`--bs-form-switch-bg`).
  No change needed.
- **`nav-tabs`**: unchanged (5.3 adds an optional `.nav-underline` variant, not required).
- **`modal`**: component/API unchanged; dismiss still via `data-bs-dismiss` + `.btn-close`.
- **`navbar-expand` / `navbar-expand-lg`**: unchanged.
- **`alert` / `alert-dismissible` / `alert-{{category}}`** (`base.html:77-84`): still valid.
  `alert-variant()` Sass mixin deprecated (Sass-only; not used here). Dismiss markup
  (`alert-dismissible` + `.btn-close[data-bs-dismiss=alert]`) is correct for BS5.
- **`btn-close`** (`base.html:81`, `_record_modal.html`): valid (renamed from `.close` in v5.0).
  `.btn-close-white` was deprecated in v5.3 in favour of `data-bs-theme="dark"`; only relevant
  if used on dark backgrounds.
- **`btn-block` is a Bootstrap-4 no-op** — dropped in v5.0. Occurrences: `settings.html:7,37,52,
  177,191`; `_player.html:242`; `portals.html:63,181`. It currently does nothing (already broken
  visually). To restore full-width buttons, wrap in `.d-grid` or add `.w-100`; since presentation
  is frozen here, note it for the restyle rather than silently changing behaviour.
- **`.text-muted`** (`base.html:27`): deprecated in v5.3 → `.text-body-secondary`
  (`$text-muted` → `$body-secondary-color`). Still present in 5.3, removed in v6.
- Dark-first convergence: v5.3's `data-bs-theme="dark"` on `<html>` (or a wrapper) is the
  supported mechanism and pairs with the map's dark-first decision; `bg-dark`/`table-dark` still work.

## SRI ⇄ version-bump coupling, and why SRI ≠ offline

- An `integrity=` hash pins the **exact bytes**. Bumping any asset version (even a patch)
  invalidates the hash: the browser refuses to load the resource on mismatch. So the hash and
  the version must always be updated together, in lockstep, in whatever file records them.
- The Bootstrap/jQuery hashes are stable and vendor-published (cdnjs sha512, Bootstrap docs
  sha384). The DataTables and Bootstrap Icons hashes here are computed snapshots — re-derive
  them at upgrade time (and if using the server-generated DataTables combined build, treat the
  recorded hash as the hash of the *vendored copy*, not of a future re-download).
- **SRI does not help the offline case.** SRI only proves a fetched resource matches a known
  digest; if the CDN is unreachable, nothing loads regardless of SRI. What fixes offline is
  **vendoring** the files into `static/vendor/`, which this ticket's layout does. The map already
  places CSP/SRI adoption out of scope (pervasive inline `<script>`), so SRI is a "known bytes"
  record here, not a runtime control.

## Open questions / unverified

- DataTables combined-build and Bootstrap Icons SRI values are **computed, not vendor-published**
  (neither project publishes per-file SRI; DataTables' download page has no `integrity` output).
  They are correct for the current bytes, but must be regenerated on re-download/upgrade.
- Buttons 3.2.6 is the latest npm 3.x and the CDN combined build `b-3.2.6` resolves; no official
  DataTables "compatibility matrix" table was found beyond npm dependency ranges
  (`datatables.net-buttons-bs5@3.x → datatables.net-bs5@^2`). Confirm against release notes at
  upgrade time.
- Bootstrap Icons 1.13.2 is **not on cdnjs** (cdnjs has 1.13.1); jsDelivr/npm/GitHub release is
  the source. cdnjs may catch up; re-check if cdnjs parity is wanted.
- Whether DataTables 2 emits a console deprecation warning for `ext.search.push` was **not
  verified** (docs say it is "retained for backwards compatibility" and discourage new use, but do
  not state a warning). Low risk given behaviour is frozen.
- Exact Font Awesome → Bootstrap Icons name mapping is **ticket #04** (`map-font-awesome-icons`),
  deliberately not done here.
- Bootstrap 6.0 docs already exist on getbootstrap.com (v6 removes `.navbar-light`/`.navbar-dark`
  entirely and changes collapse state signalling). The map targets 5.3; v6 is out of scope and
  noted only so nobody "upgrades to latest" past 5.3 by mistake. Likewise DataTables' latest is
  now 3.x (npm `latest: 3.1.4`); this ticket deliberately pins 2.3.8.
- The repo's custom DataTables 1.x class-name usage (if any) was not exhaustively audited; a
  grep for `dataTables_` / `sorting_` / `paginate` selectors across `templates/` and `static/`
  is recommended before the DT2 swap.
