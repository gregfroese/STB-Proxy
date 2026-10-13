# Research: vendored asset recipe

Type: wayfinder:research
Status: resolved

## Question

What is the concrete recipe for vendoring and upgrading the Operator UI's front-end assets?

Gather, with pinned versions and exact figures:

- **Bootstrap 5.3.x** CSS + bundle JS: latest 5.3 patch, cdnjs/jsDelivr URL, SRI hash.
- **Bootstrap Icons**: latest version, whether to vendor the SVG sprite, the icon font, or both, and the reference pattern.
- **DataTables 2.3.x** with the Bootstrap-5 integration plus **jQuery 3.7.1**: the download-builder URL(s), the SRI hashes, and which files the bundle contains.
- The `static/vendor/` directory layout and the `{{ url_for('static', filename='vendor/...') }}` reference pattern.
- How to vendor Bootstrap Icons without breaking `@font-face` `url()` paths (or the sprite alternative that avoids webfonts).
- DataTables 1.11 → 2.x migration notes relevant to `editor.html`: the `dom:` → `layout:` change (`editor.html:443`), and the custom `$.fn.dataTable.ext.order[...]` / `$.fn.dataTable.ext.search` plugins (`editor.html:413-439`) and `orderDataType` column defs (`editor.html:501-513`).
- Any Bootstrap 5.0 → 5.3 notes for the classes this repo uses.

Resolve as a subagent calling the `research` skill; capture findings on a throwaway `research/vendored-asset-recipe` branch and link it from this ticket. This unblocks **Decide frontend migration plan**.

## Answer

Resolved by the `research` subagent. Findings: [research/vendored-asset-recipe.md](../research/vendored-asset-recipe.md).

Headline results:

- Pin **Bootstrap 5.3.8**, **Bootstrap Icons 1.13.2**, **jQuery 3.7.1**, **DataTables 2.3.8 + Buttons 3.2.6** (Bootstrap-5 integration). Full manifest with URLs and SRI hashes in the research doc.
- Vendor the **Bootstrap Icons icon font** (`bootstrap-icons.min.css` + `woff2`/`woff`), not the SVG sprite — keeps the existing `<i class="fa …">` → `<i class="bi …">` pattern instead of rewriting every icon to inline `<svg><use>`.
- **DataTables 2.x no longer bundles jQuery** — vendor jQuery as its own file (a change from today's `dt-1.11.3` build). Buttons must move to the v3 line with DT2.
- `dom:` still works in DT2 but its default CSS was rewritten for `layout:`, so `editor.html:443` must migrate; the custom `ext.search` / `ext.order` plugins and `orderDataType` defs survive. Watch DT2's new `deferRender: true` default against editor code that assumes row nodes exist.
- Bootstrap 5.3: `navbar-light` deprecated (navbar is light by default), `text-muted` → `text-body-secondary` (deprecated), `btn-block` already a BS4 no-op.
- Unverified (flagged): DataTables/Bootstrap-Icons SRI values are computed, not vendor-published; Bootstrap Icons 1.13.2 is on jsDelivr/npm but not cdnjs. The research doc records these explicitly.

Context: `.scratch/operator-ui-modernization/research/vendored-asset-recipe.md`.
