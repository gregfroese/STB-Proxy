# Decide frontend migration plan

Type: wayfinder:grilling
Status: resolved
Blocked by: 02

## Question

Given the vendored asset recipe (ticket 02), what is the spec's front-end migration plan?

Decide:

- The exact versions adopted (Bootstrap 5.3.x, Bootstrap Icons, DataTables 2.3.x, jQuery 3.7.1) and the vendored file set.
- The `static/vendor/` layout and how `base.html` references it.
- The DataTables upgrade approach for `editor.html`: keep the bundled jQuery, migrate `dom:` → `layout:`, and confirm the custom order/search plugins and `orderDataType` defs still work.
- Which deprecated classes to fix in the same pass: `navbar-light` (deprecated in 5.3), the Bootstrap-4 `btn-block` no-ops (`settings.html:7,37,52,177,191`; `_player.html:242`; `portals.html:63,181`).
- The packaging test to add (assert vendored files exist / are referenced), since none exists today.
- Whether SRI tags are added now (cheap once assets are pinned) or left out.

Produces the migration section of the spec. Consult `grilling` + `domain-modeling`.

## Answer

The spec's front-end migration plan. Full manifest, URLs and SRI in [research/vendored-asset-recipe.md](../research/vendored-asset-recipe.md).

**Versions & vendoring.** Pin **Bootstrap 5.3.8, Bootstrap Icons 1.13.2, jQuery 3.7.1, DataTables 2.3.8 + Buttons 3.2.6** (Bootstrap-5 integration). Vendor into the research's `static/vendor/` tree (`bootstrap/`, `bootstrap-icons/` + `fonts/`, `datatables/`, `jquery/`), referenced with `{{ url_for('static', filename='vendor/…') }}` from `base.html`. Deliberately **not** Bootstrap 6 or DataTables 3.

**Icons.** Vendor the Bootstrap Icons **icon font**, keeping `fonts/` as a sibling of the CSS so the `@font-face` `url()`s resolve; not the SVG sprite. Keeps the `<i class="fa…">` → `<i class="bi…">` swap (name mapping is **Map Font Awesome 4 icons**).

**DataTables upgrade (editor only).** Keep the bundled jQuery model but vendor jQuery as its own file (DT2 no longer bundles it). Migrate `dom:` → `layout:` (`editor.html:443`), recreating the three custom bars (`filter-bar`, `bulk-bar`, `dead-filter`) with **`layout` function values**, keeping the existing `initComplete` fills. Set **`deferRender: false`** to preserve v1's always-present row nodes. The custom `ext.search` / `ext.order` plugins and `orderDataType` defs survive; note re-enabling `deferRender` as a later optimisation.

**Pre-swap audits.** Grep `templates/` + `static/` for DT1 class names (`dataTables_`, `sorting_`, `paginate`) — DT2 renamed them to a `dt-` prefix. (Recon: `base.html` has none.)

**Deprecated-class cleanup.** Drop `navbar-light`; `text-muted` → `text-body-secondary`; replace the 8 Bootstrap-4 `btn-block` no-ops (`settings.html:7,37,52,177,191`; `_player.html:242`; `portals.html:63,181`) with real full-width (`.w-100` single buttons, `.d-grid` for stacks).

**Colour mode.** Adopt `data-bs-theme="dark"` on `<html>` at migration time (the supported 5.3 mechanism), replacing the `bg-dark`/`table-dark` hacks — making **Define light mode** a later one-attribute flip. **Design shared shell** builds on this.

**SRI.** No `integrity=` tags: assets are same-origin once vendored and SRI is out of scope (pervasive inline scripts); it would only add lockstep maintenance.

**Packaging test.** Add a test asserting every `vendor/…` reference in `base.html` resolves to a file on disk (none exists today).

Context: `research/vendored-asset-recipe.md` (294 lines), `templates/base.html`, `templates/editor.html`.
