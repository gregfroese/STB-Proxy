# Operator UI modernisation — spec

Status: ready-for-agent

Collapses the wayfinder map [`.scratch/operator-ui-modernization/map.md`](map.md) (tickets 01–12) into one buildable plan.

**Hard constraint carried throughout: behaviour is frozen.** This is presentation only — CSS, markup, class names, tokens. The ~1,700 lines of inline JS that build UI as HTML strings are not refactored. The UI keeps working exactly as it does today; only its look changes.

## Problem Statement

The operator runs STB-Proxy's web console daily, and it has aged badly. It loads Bootstrap 5.0.1, Font Awesome 4.7, DataTables 1.11 and jQuery 3.6 **from a CDN**, so on the LAN — where the product is actually meant to run — it renders unstyled or not at all when the internet is down. The dark theme is a pile of hacks (`bg-dark`, `table-dark`, `#adb5bd !important` patches, 24 hardcoded hexes) with the same dark-tab override copy-pasted into two templates. There is no light mode, focus styling is absent, and several control boundaries and badge labels fail WCAG contrast. The look has also drifted away from the Web Viewer, which already has a clean, modern, token-based design system — so the same product presents two different faces.

## Solution

Restyle the Operator UI onto a modern, **vendored** front-end stack (Bootstrap 5.3.8, Bootstrap Icons, jQuery 3.7.1, DataTables 2.3.8), with a single token stylesheet (`static/theme.css`) whose dark palette converges on the Web Viewer's, a regrouped shared shell, a light mode, and WCAG 2.1 AA on the shared shell, forms and navigation. It ships as **five independently-releasable slices**, each a version bump + changelog entry, and the app works offline from the first slice.

## User Stories

1. As an operator on an isolated LAN, I want the console's styles, scripts, fonts and icons served from the app itself, so that the UI renders fully with no internet connection.
2. As an operator, I want the console to look like a modern product, so that using it feels current rather than decade-old.
3. As an operator, I want the console to share the Web Viewer's visual language, so that STB-Proxy feels like one product across its surfaces.
4. As an operator, I want a dark theme by default, so that the console matches the Web Viewer and is easy on the eyes at night.
5. As an operator, I want a light mode, so that I can use the console comfortably in a bright room.
6. As an operator, I want the theme to follow my operating system by default, so that I don't have to set it.
7. As an operator, I want a single sun/moon toggle in the top bar that remembers my choice, so that I can switch and have it stick.
8. As an operator, I want no flash of the wrong theme when a page loads, so that the switch feels instant and clean.
9. As an operator, I want modern, consistent icons throughout, so that the UI reads clearly and doesn't look dated.
10. As an operator, I want the top navigation grouped by role (Monitor / Programme / Configuration), so that I can find a page without scanning eleven links.
11. As an operator, I want the current page clearly marked, so that I always know where I am.
12. As an operator, I want a skip-to-content link, so that I can bypass the nav with a keyboard.
13. As an operator, I want one consistent focus ring on every control, so that keyboard navigation is always visible.
14. As an operator, I want flash messages as unobtrusive bottom-right toasts, so that feedback doesn't shove the page content around.
15. As a phone user, I want the nav to collapse behind a hamburger, so that the console is usable on a small screen.
16. As a phone user, I want the Dashboard, Streams, Blocks and Multiview pages usable at 360px, so that I can check status and control streams from my phone.
17. As an operator, I want every page to sit in one consistent container with consistent gutters, so that pages stop looking slightly different from each other.
18. As an operator, I want cards, tables, forms, switches, modals, tabs, buttons, badges and empty states to look identical everywhere, so that I can rely on one visual language.
19. As an operator, I want a Channel's Block membership shown as a set of pills (capped, with a `+N` overflow), so that channels in several Blocks are represented honestly.
20. As an operator, I want the Playlist Editor's filter bar, bulk-action bar and dead-filter switches laid out as one clean toolbar, so that the dense editing surface stays legible.
21. As an operator, I want the Playlist Editor's grid to keep working with the upgraded DataTables, so that editing is unaffected by the restyle.
22. As an operator, I want Multiview's grid layouts, tiles, fullscreen and drag divider to keep working while adopting the new colours, so that my wall of streams is unchanged in behaviour but modern in look.
23. As an operator, I want Multiview's grid to size correctly on mobile browsers with dynamic toolbars, so that tiles aren't clipped.
24. As an operator, I want the Dashboard's live log in a proper bordered panel that still auto-scrolls, so that monitoring stays readable.
25. As an operator, I want the Dashboard's account and streaming cards to use the shared card grid, so that they match Streams.
26. As an operator, I want the Guide's filters and results table restyled consistently, so that browsing the EPG is easier on the eyes.
27. As an operator, I want Recordings' tabs, lists and playback modal restyled consistently, so that managing recordings is easier.
28. As an operator, I want Streams' card grid to be the reference treatment, so that live streams are presented cleanly.
29. As an operator, I want the Blocks page to keep its expandable per-block channel list while adopting pill-stack block badges and icon actions, so that managing Blocks stays efficient.
30. As an operator, I want the Portals page's tiles to use the shared card grid and its add/edit modals restyled, so that managing portals is consistent.
31. As an operator, I want the Settings page broken into clear sectioned cards, so that I can find a setting without scrolling a wall of controls.
32. As an operator, I want Settings' Save always reachable, so that I don't have to scroll back to the top to save.
33. As an operator, I want the Accounts page to keep its compact admin table restyled, so that managing logins stays quick.
34. As an operator, I want the Changelog readable as a document with sensible line length, so that I can actually read release notes.
35. As an operator with low vision, I want all text to meet WCAG 2.1 AA contrast, so that I can read the console.
36. As an operator with low vision, I want form controls, switches and buttons to have boundaries that meet non-text contrast, so that I can tell where they are.
37. As an operator with low vision, I want badge labels to be readable, so that status is clear.
38. As a keyboard user, I want a visible focus indicator on every focusable element including table rows and tiles, so that I can navigate without a mouse.
39. As the maintainer, I want the duplicated dark-tab overrides, `.text-muted` patches and 24 hardcoded hexes consolidated into one stylesheet, so that the theme is one thing to change.
40. As the maintainer, I want a test that the vendored assets exist and are referenced, so that the offline guarantee can't silently regress.
41. As the maintainer, I want a test that the token set is present for both modes, so that the theme can't silently regress.
42. As the maintainer, I want a test that the key contrast pairings meet AA, so that accessibility can't silently regress.
43. As the maintainer, I want each slice to ship as its own version bump and changelog entry, so that the change is reviewable and reversible in steps.
44. As the maintainer, I want the existing source-string template assertions kept green, so that the restyle doesn't break documented markup contracts.
45. As the maintainer, I want the Web Viewer and Operator UI to share colour values but not code, so that each can evolve without coupling.
46. As the maintainer, I want a clear list of what remains out of scope and what becomes a future effort, so that scope doesn't creep.

## Implementation Decisions

### A. Front-end substrate (release 1)

- **Vendor everything** into `static/vendor/` and reference it via `url_for('static', …)` from the shared shell, replacing all CDN tags: **Bootstrap 5.3.8**, **Bootstrap Icons 1.13.2** (the icon **font**, with `fonts/` a sibling of the CSS so `@font-face` resolves), **jQuery 3.7.1** (its own file — DataTables 2 no longer bundles it), **DataTables 2.3.8 + Buttons 3.2.6** (Bootstrap-5 integration). Deliberately not Bootstrap 6 or DataTables 3. The full file manifest, URLs and hashes are in [`research/vendored-asset-recipe.md`](research/vendored-asset-recipe.md).
- **Adopt `data-bs-theme` on `<html>`** (`"dark"` at migration time), replacing the `bg-dark`/`table-dark` hacks. This makes light mode (release 5) a one-attribute flip.
- **Icons:** swap Font Awesome 4.7 for Bootstrap Icons across every template, per the full mapping table in [`fa-to-bi-icon-map.md`](fa-to-bi-icon-map.md) (solid → `-fill`, `-o` → outline).
- **DataTables upgrade (editor only):** migrate the `dom:` string to a `layout:` config, recreating the three custom bars (`dead-filter`, `filter-bar`, `bulk-bar`) as named `div` features that `initComplete` continues to fill. Set `deferRender: false` to preserve v1's always-present row nodes. The custom `ext.search`/`ext.order` plugins and `orderDataType` defs survive. Keep the bundled-jQuery model (jQuery vendored separately). Re-enabling `deferRender` is noted as a later optimisation.
- **Pre-swap audit:** grep templates + static for DataTables-1 class names (`dataTables_`, `sorting_`, `paginate`); DT2 renamed them to a `dt-` prefix. Recon shows the shared shell has none.
- **Deprecated-class cleanup:** drop `navbar-light`; `text-muted` → `text-body-secondary`; replace the eight Bootstrap-4 `btn-block` no-ops with real full-width (`.w-100` for single buttons, `.d-grid` for stacks).
- **No SRI:** assets are same-origin once vendored and SRI is out of scope (pervasive inline scripts).

### B. Design tokens (release 2)

- **One stylesheet, `static/theme.css`**, mirroring the Web Viewer's single-file approach. A `:root`/theme token block at the top; component overrides (section C) layer beneath in the same file. **Values are copied from the Web Viewer, not the file — the two codebases stay separate.**
- **Dark tokens** (copied verbatim from the Web Viewer's palette; the Web Viewer is the convergence target):

```css
:root, [data-bs-theme="dark"] {
  --bg: #0d1117; --bg-glow: 24,34,51;
  --panel: #161b22; --panel2: #1c2330;
  --line: #2b3542; --line-strong: #5c6b80;
  --ink: #e6edf3; --dim: #8b98a7;
  --accent: #3ba6ff; --on-accent: #04121f;
  --focus: #ffd34d; --star: #ffd34d;
  --ok: #3fb950; --warn: #e3b341; --bad: #f85149;
}
```

- **Light tokens** (net-new; the Web Viewer is dark-only). Light inverts the dark ladder so the page is the tinted surface and cards are white; note `--panel2` (raised inputs/buttons) is *darker* than `--panel` — there is nothing lighter than white:

```css
[data-bs-theme="light"] {
  --bg: #f6f8fa; --bg-glow: 214,222,232;
  --panel: #ffffff; --panel2: #eef1f4;
  --line: #d0d7de; --line-strong: #7a8794;
  --ink: #1f2328; --dim: #59636e;
  --accent: #0969da; --on-accent: #ffffff;
  --focus: #b07800; --star: #b07800;
  --ok: #1a7f37; --warn: #9a6700; --bad: #cf222e;
  --shadow: 0 1px 2px rgba(31,35,40,.06);
  --shadow-lg: 0 24px 60px rgba(31,35,40,.22);
  --scrim: rgba(31,35,40,.35); --logo-mat: #ffffff;
  color-scheme: light;
}
```

- **Semantic tints** are derived with `color-mix(in srgb, <token> N%, transparent)` (≈12–16% fills, ≈40% borders) rather than hand-baked tint hexes, so tints track the base token.
- **Type:** system fonts (`system-ui, …`; mono `ui-monospace, …`) — no webfont, no CDN. Size scale `11/12/13/14/15/16/18/20px`, body **13px**; weights `400/600/700/800`; antialiased.
- **Spacing:** `--sp-1..4 = 6/10/14/20px`. **Radius:** `--r-sm/md/lg/pill = 8/10/14/999px`. **Elevation:** border-led; minimal ambient shadow; one modal shadow.
- **`--line-strong`** exists **only for interactive component boundaries** (form controls, switches, buttons); decorative separators (cards, dividers, row rules) keep `--line`.

### C. Shared shell (release 2)

- **Grouped top bar.** The ten internal destinations stay inline, ordered and grouped by role with faint separators: **Monitor** (Dashboard, Streams, Recordings, Multiview) · **Programme** (Playlist Editor, Guide, Blocks) · **Configuration** (Portals, Accounts, Settings). The **feeds** (`/playlist`, `/xmltv`) are demoted to icon-only ghost buttons at the right end (title + `target="_blank"`); **Changelog** is the version chip beside the brand.
- **Active page** gets `aria-current="page"` plus a filled treatment (accent-tinted pill with an inset accent bar).
- **Container:** centered `max-width: 1280px` with `--sp-4` gutters; a **full-bleed variant sharing the same gutters** for edge-to-edge pages (editor, multiview, dashboard, streams). The `.container`/`.container-fluid` and `p-lg-5`/`px-lg-5` divergence, and the floated `mx-lg-5` navbar, go away.
- **Focus:** one global `:focus-visible` rule — `2px solid var(--focus)` at `2px` offset — on every focusable control.
- **Skip link** to `#main`.
- **Flash messages → bottom-right toasts**, stacked, `role="status" aria-live="polite"`, dismissible, category-coloured left border. Hand-rolled; no toast library.
- **Responsive collapse:** below `992px` the nav collapses behind a hamburger into a full-width sheet whose items keep the group headings; the feed buttons reappear as a "Feeds" group in the sheet. Toasts go full-width-bottom, stacked above the docked player panel.
- A **left rail** is noted but **not committed** — no rail in this shell.

### D. Canonical components (release 3)

- **Block-set component:** a Channel can be in several Blocks, so Block membership is a wrapping stack of small `.tag` pills (`--panel2` bg, `--line` border, `--r-pill`), capped at **3 shown + a `+M` overflow pill** (title lists the rest). Applies to read-only surfaces (Blocks channel list, player block choices, Multiview picker rows). The **Playlist Editor's block column stays a single editable text input** — not a chip editor.
- **Badges/pills:** label text is **`--ink`**; the semantic colour is carried by the tint fill, the border and the dot. (Fixes WCAG.)
- **Alerts vs toasts:** flash → bottom-right toasts (above); static page-level notices stay inline but drop Bootstrap `.alert-*` colours for token notice/error surfaces.
- **Data table (DataTables 2):** the editor grid is the token table; plain HTML tables share one token treatment. Header, stripes, `nowrap`, `align-middle`.
- **Buttons:** one token system — `primary`→`--accent`, `success`→`--ok`, `danger`→`--bad`, `warning`→`--warn`, default/`outline-light`→`--panel2`+`--line`; **all filled variants use `--on-accent` text**. **Icon-only buttons** are one component: square `2rem`, min 24×24 hit target, `--dim` brightening to `--ink` on hover, **required `aria-label`**. `btn-close-white` retained in dark, `.btn-close` in light.
- **Cards:** one canonical card — `--panel` bg, `1px --line` border, `--r-md`, header separated by a bottom border. All `bg-light`/`bg-secondary`/`bg-dark`/`text-dark`/`text-light` variants dropped.
- **Forms & switches:** one token treatment — controls on `--panel2` with **`--line-strong`** borders, `--r-sm`, `--ink` text, `--dim` placeholder/labels; switches filled with `--accent`; unified `input-group`.
- **Modals:** one token modal — `--panel` + `--line` + `--r-lg`, the modal shadow, scrim `#000a` dark / lighter in light, `btn-close-white`.
- **Tabs:** a **single canonical `.nav-tabs` token override** in `theme.css`; the byte-identical dark overrides in the Blocks and Recordings templates are deleted. Multiview's picker pills become the token segmented control.
- **Empty states:** one `.empty-state` component (centred `--dim`, optional icon/action, error variant via `--bad`); loader spinners fold into its busy state. Replaces the ~20 ad-hoc empty states.
- **Log panel:** a token panel (monospace, `--panel2`, `--line` border, fixed-height scroll region) for the Dashboard log.
- **Card grid:** the Streams grid (`row-cols-1 / md-2 / xl-3`, `g-3`) is the shared card-grid treatment.
- **Colour dedup:** all 24 hardcoded hexes move behind tokens; the `.text-muted !important` patches and the duplicated `.channel-logo` / `.programme-desc` rules consolidate into `theme.css`.

### E. Page compositions (release 4)

- **Playlist Editor:** toolbar = one bordered panel above the table (filter row always; bulk row when rows are selected; dead-filter switches as a third row), restyled from the injected DataTables rows; horizontal scroll accepted (Tier B / desktop-first).
- **Multiview:** keeps its **page-local CSS** — the five `[data-layout]` grid templates, absolutely-positioned tile chrome, drag divider, fullscreen, and mobile stack — but every colour/radius comes from tokens and the `calc(100vh − 190px)` height coupling becomes `dvh` + fallback.
- **Dashboard:** account + streaming cards are token cards (streaming reuses the card grid); the log is the token log panel; the three poll cadences are untouched.
- **Guide:** filter bar = the shared toolbar; JS-built results table = the token table; the `.programme-desc` clamp moves to `theme.css`; the status line uses the shared notice/empty-state.
- **Recordings:** shared tab override, token tables, token notice/error surfaces, token `modal-xl`.
- **Streams:** the canonical card grid; zero page-local CSS.
- **Blocks:** keep the table with its expandable per-block channel sub-row; block column = pill stack; per-row cluster = icon buttons; "Default blocks" = token card; shared empty state.
- **Portals:** tiles → shared card grid; whole-card click target kept with a token hover affordance; both add/edit modals restyled (kept separate — merging is a refactor); `<br><br>` fields → token form groups; add the missing empty state.
- **Settings:** the nine `h4`+`hr` sections become **card-per-section**, keeping the single external form; stray `col-md-*` wrapped in rows; Save moves into a **sticky action bar**.
- **Accounts:** keep the compact admin table (tokenised), including editable Blocks/password cells; add-account form → token card; shared empty state; icon-button actions.
- **Changelog:** bare prose (not carded) with a **~70ch reading cap** and tokenised typography.
- **Surviving page-local CSS:** only Multiview's grid/tiles/fullscreen and the editor's DataTables `layout` config (no CSS). Everything else lives in `theme.css`.

### F. Responsive & mobile (release 4)

- **Bootstrap 5.3 defaults are the scale** (no `--bp-*` tokens — custom properties can't drive `@media`).
- **Tier A** (fully usable at 360px): Dashboard, Streams, Blocks, Multiview. **Tier B** (desktop-first, "usable, not optimal"): the rest.
- Fixed chrome uses `dvh` + safe-area insets; only Multiview's fixed height needs the `dvh`+fallback fix.

### G. Accessibility (release 2/3, verified 5)

- **WCAG 2.1 AA** on the shared shell, forms and navigation; best-effort elsewhere. All text pairings pass both modes; three fixes are baked in: **`--line-strong`** for interactive boundaries, **badge text `--ink`**, **light `--focus`/`--star` `#b07800`**. Filled buttons use `--on-accent` (AA-passing in both modes). Video/Multiview overlays are best-effort (AA not asserted over uncontrolled media); the playing ring maps to `--focus`/`--star`.

### H. Convergence

- The Operator UI and the Web Viewer **share values, not code**: the dark token values are copied literally into `theme.css`; the light set is Operator-UI-only; the shared shape language (border-led, radius ladder, system fonts) is matched by hand. No shared package, import, or build coupling. Re-converging means copying new values in a later change.

### I. Release sequencing

Five independently-shippable releases, each a `version.py` bump (minor; patches for fixes within) + a dated top-of-file `CHANGELOG.md` entry:

1. **Vendored, upgraded stack** — section A.
2. **Token theme + shell** — sections B, C (incl. `--line-strong`, dark focus).
3. **Canonical components** — section D (incl. the badge-ink rule; CSS/hex dedup).
4. **Page compositions** — sections E, F.
5. **Light mode** — the light token block, the `data-bs-theme` switch, the sun/moon toggle, and a no-FOUC inline script.

## Testing Decisions

**What makes a good test here:** this is a presentation-only change, so there is no logic to assert — tests lock down *external, observable* contracts only: which assets exist and are referenced, that the token set is present for both modes, that rendered markup no longer carries the deprecated classes and does carry the new ones, and that the accessibility-critical contrast pairings hold. No test asserts internal structure or styling minutiae.

**Seams (two existing, one new):**

- **Rendered-HTML seam** — extends the existing `tests/test_templates.py` style: drive each route through Flask's test client and assert on the rendered markup. Covers: Bootstrap Icons `bi-*` present and no stale `fa-*`; no `navbar-light`/`btn-block`; `data-bs-theme` set; vendored `url_for` references present; `aria-current` on the active nav item; the shared component classes. Also keeps the existing `node --check` on extracted inline scripts.
- **On-disk asset seam** — extends the existing `tests/test_packaging.py` style: every `vendor/…` reference in the shared shell resolves to a file on disk, and `static/theme.css` exists and defines the token set for both modes.
- **Computed contrast seam (new)** — reads the token values out of `theme.css` and asserts the WCAG AA pairings from **Audit focus/contrast** (the three fixed pairings plus the passing baseline). Deterministic, no browser.

**Prior art:** `tests/test_templates.py` (source-string assertions + `node --check`), `tests/test_packaging.py` (file/asset presence), `tests/test_version.py` (changelog/version agreement). All run under the root `unittest` suite: `python3 -m unittest discover -s tests -t .`.

**Per-release verification:** the packaging/asset-presence test (R1), the token-presence test (R2), updated source-string assertions throughout, and a **manual visual pass** per release (both widths; light + dark from R5). No Playwright harness.

## Out of Scope

- **Dropping Bootstrap** for a hand-rolled CSS/JS system — a follow-on map.
- **Dropping DataTables / removing jQuery** — a follow-on map (the repo has a fetch-table pattern to build on later).
- **CSP and SRI adoption** — blocked by the pervasive inline `<script>`/`style`; a separate security effort.
- **Refactoring the inline JS** that builds UI as HTML strings — behaviour is frozen.
- **A left rail** shell — noted, not committed.
- **Converting the editor's block cell to a chip editor** — stays a text input.
- **Merging the Portals add/edit modals** — a markup refactor.
- **Any change to `android/` (Companion app) or `web/` (Web Viewer).**

## Further Notes

- **Prototypes** (primary sources, served for review): [`prototype/theme-tokens.html`](prototype/theme-tokens.html), [`prototype/shared-shell.html`](prototype/shared-shell.html), [`prototype/light-mode.html`](prototype/light-mode.html).
- **Research:** [`research/vendored-asset-recipe.md`](research/vendored-asset-recipe.md) (versions, URLs, hashes, vendoring layout); the icon map is [`fa-to-bi-icon-map.md`](fa-to-bi-icon-map.md).
- **Domain vocabulary:** `GLOSSARY.md` (Operator UI, Portal, Lineup, Block, Channel, Multiview, Tile…). A Channel's membership in several Blocks is the load-bearing domain constraint behind the pill-stack component.
- **The map** that produced these decisions: [`.scratch/operator-ui-modernization/map.md`](map.md) — its Decisions-so-far index links each ticket's full detail.
