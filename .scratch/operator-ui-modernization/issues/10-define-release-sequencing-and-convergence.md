# Define release sequencing and convergence

Type: wayfinder:grilling
Status: resolved
Blocked by: 05, 06, 07, 08, 09, 11, 12

## Question

How does the resulting spec slice into shippable releases, and what exactly is the "shared product look" boundary with the Web Viewer?

Decide:

- The release order (likely: vendored/upgraded stack → tokens + shell → components → heavy pages → light mode), sized so each release is independently shippable under the repo's per-change version bump + CHANGELOG rule.
- For each release: what moves, what is left untouched, and the manual verification pass.
- The convergence boundary: which values the Operator UI and the Web Viewer share (the token palette) and the explicit rule that they share *values, not code*.
- What, if anything, becomes a follow-on map (candidate: dropping Bootstrap; candidate: dropping DataTables/jQuery).

This closes the map: its answer plus the preceding tickets are the spec. Consult `grilling` + `domain-modeling`.

## Answer

The map closes here. This answer plus tickets 01–09, 11 and 12 **are** the modernisation spec — no separate `spec.md` (the decision set is the spec).

### Release sequencing — five independently-shippable releases

Each release is a `version.py` bump + a dated top-of-file `CHANGELOG.md` entry (or `tests/test_version.py` fails). Each is **minor** (new capability); fixes within a release are patches. Deploy is `git pull && docker compose up -d`.

| # | Release | Moves | Untouched | Verify |
|---|---------|-------|-----------|--------|
| 1 | **Vendored, upgraded stack** | vendor BS 5.3.8 / Bootstrap Icons 1.13.2 (font) / jQuery 3.7.1 / DataTables 2.3.8 + Buttons 3.2.6 into `static/vendor/`; `base.html` refs; `data-bs-theme="dark"`; FA→Bootstrap Icons swap; drop `navbar-light`/`text-muted`/`btn-block`; editor `dom:`→`layout:`; vendored-asset-presence test | layout, tokens | packaging + source-string tests, `node --check`, offline visual |
| 2 | **Token theme + shell** | `static/theme.css` dark tokens (incl. `--line-strong`, `#ffd34d` focus) + grouped shell (active pill, skip link, focus-visible, bottom-right toasts, hamburger, one container) | page bodies | token-presence test, source-string tests, visual |
| 3 | **Canonical components** | component overrides in `theme.css` (cards / tables / forms / switches / modals / tabs / badges (**text `--ink`**) / empty-states / buttons / notices); delete duplicated `.nav-tabs` overrides, `.text-muted !important` patches, `.channel-logo`, `.programme-desc`, and the 24 hardcoded hexes | page layout | source-string tests, visual |
| 4 | **Page compositions** | the heavy (09) **and** simple (11) page layouts | — | visual pass, all pages, both widths |
| 5 | **Light mode** | light token block (`--focus`/`--star` `#b07800`), `data-bs-theme` switch, sun/moon toggle, no-FOUC script | — | light/dark visual |

The contrast-audit changes (12) ride along: `--line-strong` in release 2, the badge-ink rule in release 3. Release 1 is deliberately kept separate from 2 — a small, safe substrate swap that delivers the offline fix; the brief "new stack, old theme" look is acceptable.

### Convergence boundary

The Operator UI and the Web Viewer **share values, not code**:

- The **dark token values are copied literally** from `web/app/src/app.css` into `static/theme.css` — no shared package, no import, no build coupling — plus the shared shape language (border-led, the radius ladder, system fonts).
- The **light token set is Operator-UI-only** (the Viewer is dark-only).
- Divergence is allowed but deliberate; re-converging means copying new values in a later change. Nothing syncs automatically, and convergence is a design commitment checked by hand, not tooling.

### Verification

Light, per the map's quality bar: a vendored-asset-presence test (R1), a token-presence test (R2), updated `tests/test_templates.py` source-string assertions, `node --check` on inline scripts, and a **manual visual pass** per release (both widths; light+dark from R5). No Playwright harness. Every release keeps the root `unittest` suite green.

### Follow-on maps (noted, not started)

- **Drop Bootstrap** for a hand-rolled CSS/JS system.
- **Drop DataTables / jQuery** for the repo's fetch-table pattern.

CSP/SRI remains a separate security effort (out of scope). No other fog remains; the map is complete.

Context: `version.py`, `CHANGELOG.md`, `tests/test_version.py`, `tests/test_templates.py`, `tests/test_packaging.py`, `Dockerfile`, `docker-compose.yml`, `README.md:313`; the settled tickets 01–09, 11, 12.
