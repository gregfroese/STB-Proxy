# Decide frontend migration plan

Type: wayfinder:grilling
Status: open
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
