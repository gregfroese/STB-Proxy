# Map: Operator UI modernisation

Label: wayfinder:map

## Destination

A decision set (a modernisation spec) for STB-Proxy's own web UI — the **Operator UI** rendered by Flask from `templates/` + `static/`. The spec is done when every design decision needed to restyle that UI is settled and sequenced into shippable releases; it does **not** itself restyle the code. Android (`android/`) and the Web Viewer (`web/`) are out of scope.

## Notes

Domain: STB-Proxy's server-rendered **Operator UI** (Flask + Jinja). Vocabulary is in `GLOSSARY.md`.

Skills every session should consult: `grilling` and `domain-modeling` (call both for any undecided ticket); `prototype` for the prototype tickets.

Settled framing (from charting — do not re-litigate):

- **Style substrate**: keep Bootstrap, upgrade to 5.3, and lay a shared token theme over it so the look converges on the Web Viewer's palette. Dropping Bootstrap entirely is out of scope.
- **Theme modes**: dark-first (matching the Web Viewer); light mode is a token override added later, still inside this map.
- **Icons**: move Font Awesome 4.7 → **Bootstrap Icons**.
- **Asset delivery**: vendor all CSS/JS/fonts into `static/vendor/` (the UI is CDN-only today and breaks offline — the product is meant to run on a LAN). CSP/SRI is out of scope (blocked by pervasive inline `<script>`).
- **Editor table**: upgrade DataTables 2.3.x + jQuery 3.7 in place. Dropping DataTables / going jQuery-free is out of scope.
- **Shell**: regrouped, restyled top nav now; a Svelte-style left rail is noted, not committed.
- **Behaviour is frozen**: presentation only — CSS, markup, class names, tokens. The ~1,700 lines of inline JS that build UI as HTML strings are not refactored.
- **Quality bar**: WCAG 2.1 AA on the shared shell/forms/nav, best-effort elsewhere; mobile is "usable, not optimal".
- **Verification**: keep it light (vendored-asset presence test, updated source-string assertions, manual visual pass). No Playwright harness.

Convergence target: `web/app/src/app.css` (the Web Viewer's single plain-CSS design system, ~1,074 lines, dark-only, system fonts, token-based, Unicode-glyph icons).

Facts gathered while charting are in the child tickets that needed them.

## Decisions so far

<!-- the index: one line per closed ticket, enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [Research: vendored asset recipe](issues/02-research-vendored-asset-recipe.md): vendor **Bootstrap 5.3.8, Bootstrap Icons 1.13.2 (font), jQuery 3.7.1, DataTables 2.3.8 + Buttons 3.2.6**; DataTables 2 drops the bundled jQuery and needs `dom:`→`layout:`. Full manifest + SRI in [the research doc](research/vendored-asset-recipe.md).
- [Design-token contract](issues/01-design-token-contract.md): adopt the Web Viewer palette **verbatim** (prototype **Variant A**); one `static/theme.css` with a `:root` token block; tints via `color-mix`; semantic set extended with used `ok`/`warn`/success. Prototype: [theme-tokens.html](prototype/theme-tokens.html).
- [Decide frontend migration plan](issues/03-decide-frontend-migration-plan.md): vendor **BS 5.3.8 / Bootstrap Icons 1.13.2 (font) / jQuery 3.7.1 / DataTables 2.3.8 + Buttons 3.2.6** into `static/vendor/`; `data-bs-theme="dark"`; migrate editor `dom:`→`layout:` (`deferRender:false`); drop `navbar-light`/`text-muted`/`btn-block`; packaging test for vendored refs; no SRI.
- [Map Font Awesome 4 icons](issues/04-map-font-awesome-icons.md): full FA4→Bootstrap Icons table (solid→`-fill`, `-o`→outline) at [fa-to-bi-icon-map.md](fa-to-bi-icon-map.md); 4 open decisions (spin keyframe, `fa-signal`→`bi-broadcast`, window glyphs, `fa-expand`/`-compress` overload).

## Not yet specified

- Page-level detail for the simpler pages (Blocks, Portals, Settings, Accounts) once the canonical component styles exist — they should fall out of the component decisions.
- Focus/contrast audit specifics against WCAG 2.1 AA, beyond the shell baseline.
- Whether Multiview's bespoke grid CSS (`multiview.html:4-109`) is absorbed into tokens or kept as a page-local exception.
- The exact shape of the vendored-asset packaging test.

## Out of scope

- Dropping Bootstrap for a full hand-rolled (Svelte-viewer-style) CSS/JS rewrite — a much larger effort; its own map if ever.
- Dropping DataTables / removing jQuery entirely — its own map; the repo already has a fetch-table pattern to build on later.
- CSP and SRI adoption — blocked by the pervasive inline `<script>`/`style`; a separate security effort.
- Any change to `android/` (Companion app) or `web/` (Web Viewer).
