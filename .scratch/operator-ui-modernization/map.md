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
- [Design shared shell](issues/05-design-shared-shell.md): **Variant A — Grouped bar** wins. One top bar, 10 destinations grouped by role with separators; feeds → icon-only ghost buttons; changelog → version chip; active = accent pill + `aria-current`; global `:focus-visible`; skip link; flash as bottom-right toasts; <992px hamburger sheet. Prototype: [shared-shell.html](prototype/shared-shell.html).
- [Decide canonical component styles](issues/06-decide-canonical-component-styles.md): one token component contract in `static/theme.css`; **block sets as capped `.tag` pill stacks** (editor block cell stays a text input); flashes → bottom-right toasts, static notices → token notice/error surfaces; DataTables 2 `dom:`→`layout:`; token buttons + labelled icon buttons; one card / form+switch / modal / tab / empty-state treatment each; 24 hexes → tokens, duplicated CSS deduped.
- [Define responsive and mobile spec](issues/07-define-responsive-mobile-spec.md): Bootstrap 5.3 defaults are the scale (no `--bp-*` tokens — can't drive `@media`); Tier A = Dashboard/Streams/Blocks/Multiview at 360px, Tier B desktop-first; six-point "usable, not optimal" bar; only Multiview's `calc(100vh - 190px)` fixed (`dvh`+fallback); `dvh` + safe-area insets on fixed chrome; toasts go full-width-bottom stacked above the docked panel below 992px.
- [Define light mode](issues/08-define-light-mode.md): **Variant A "Daylight"** — light tokens invert the dark ladder (gray page / white cards / `--panel2` darker than `--panel`), accent darkened to `#0969da` for AA; switch via `data-bs-theme` + `color-scheme` on `<html>`, default `prefers-color-scheme`, manual override in `localStorage['theme']` (no `system` value), no-FOUC inline script; one sun/moon button in the shell top bar; a short light override block for `--hi`/`--scrim`/`--bg-glow`/channel-logo mat/`btn-close`. Prototype: [light-mode.html](prototype/light-mode.html).
- [Decide heavy-page layouts](issues/09-decide-heavy-page-layouts.md): one container (1280px + `--sp-4`, full-bleed variant for editor/multiview/dashboard/streams); **editor** toolbar = one panel over the DataTables rows, h-scroll accepted (Tier B); **multiview** keeps its grid/tile/fullscreen CSS page-local (tokenised, `dvh`); **dashboard** log = token log panel, cards reuse the grid; **guide** filter bar = shared toolbar, results = token table; **recordings** = shared tabs/table/notice; **streams** = the canonical card grid; survivors = only multiview CSS + editor's `layout` config.
- [Decide simple-page compositions](issues/11-decide-simple-page-compositions.md): simple pages use the centered container + token spacing; **blocks** keeps the row-accordion table (pill-stack block cell, icon actions); **portals** tiles → shared card grid, two token modals kept, empty state added; **settings** → card-per-section + sticky Save; **accounts** keeps its admin table; **changelog** = bare prose, ~70ch cap; shared empty state everywhere, `btn-block`→`.w-100`.
- [Audit focus/contrast against WCAG 2.1 AA](issues/12-audit-wcag-contrast.md): all text pairings pass both modes; three fixes — add **`--line-strong`** (dark `#5c6b80` / light `#7a8794`) for interactive boundaries (decorative `--line` stays); **badge text = `--ink`** (semantic colour via tint+border+dot); light **`--focus`/`--star` → `#b07800`**; filled buttons all use `--on-accent`; one global 2px focus-visible ring; media overlays best-effort.
- [Define release sequencing and convergence](issues/10-define-release-sequencing-and-convergence.md): **five minor releases** — (1) vendored/upgraded stack + FA→BI, (2) token theme + shell, (3) canonical components + CSS/hex dedup, (4) heavy + simple page compositions, (5) light mode; each bumps `version.py` + CHANGELOG. **Convergence = share values, not code** (dark palette copied literally; light is Operator-only). Verification light (packaging/token-presence + source-string tests + manual visual). Follow-on maps (not started): drop Bootstrap; drop DataTables/jQuery. **This closes the map — tickets 01–12 are the spec.**

## Not yet specified

- Focus/contrast audit specifics against WCAG 2.1 AA, beyond the shell baseline — **graduated** into [Audit focus/contrast against WCAG 2.1 AA](issues/12-audit-wcag-contrast.md) once light mode (08) settled.

## Out of scope

- Dropping Bootstrap for a full hand-rolled (Svelte-viewer-style) CSS/JS rewrite — a much larger effort; its own map if ever.
- Dropping DataTables / removing jQuery entirely — its own map; the repo already has a fetch-table pattern to build on later.
- CSP and SRI adoption — blocked by the pervasive inline `<script>`/`style`; a separate security effort.
- Any change to `android/` (Companion app) or `web/` (Web Viewer).
