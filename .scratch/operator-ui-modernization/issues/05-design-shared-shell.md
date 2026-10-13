# Design shared shell

Type: wayfinder:prototype
Status: resolved
Blocked by: 01

## Question

How does the shared shell (the frame every page inherits from `base.html`) look and behave?

Decide and prototype:

- **Navigation grouping**: today the navbar crams 11 items (`base.html:34-72`), including meta/external links (Playlist, XMLTV, Changelog). Decide the grouping — which are primary, which fold into a menu or the version link.
- **Active-page indication**: add `aria-current`/active styling (absent today).
- **Containers and spacing**: reconcile the per-page `p-lg-5`, cards, and the `bg-dark` hyper-dark shell with the new tokens.
- **Focus treatment**: `focus-visible` styling across nav and controls (absent today).
- **Skip link** to the content.
- **Flash/toast placement**: where `get_flashed_messages` renders and how it looks against the new style.
- **Responsive collapse**: how the nav behaves at phone width.

**Prototype** an HTML mock of the shell (nav + container + a placeholder content block + a flash message) using the token contract from ticket 01, for the human to react to. HITL.

Deliberately note (do not decide here): whether the shell eventually becomes a left rail.

## Answer

**Variant A — "Grouped bar" wins.** One top bar; destinations grouped by role; meta/feed links demoted to icons; active page as a filled accent pill. Prototype (all three directions retained as the primary source): [`prototype/shared-shell.html`](../prototype/shared-shell.html) — A is the winner, B/C kept as the record of what was weighed and rejected. Prototype served for review at `http://100.91.119.113:8099/shared-shell.html`.

Per sub-question:

- **Navigation grouping.** One bar. The ten internal destinations stay inline, ordered and visually grouped by role with faint 1px separators: **Monitor** (Dashboard, Streams, Recordings, Multiview) · **Programme** (Playlist Editor, Guide, Blocks) · **Configuration** (Portals, Accounts, Settings). The **feeds** (`/playlist`, `/xmltv`) are demoted out of the nav to icon-only ghost buttons at the right end (title + `target="_blank"`); **Changelog** is no longer a nav item — it is the version chip beside the brand. So 11 text links become 10 grouped links + 2 icon buttons + 1 version chip.
- **Active-page indication.** `aria-current="page"` (absent today) plus a filled treatment: `color-mix(--accent 16%)` background pill with an inset `0 -2px` accent bar.
- **Containers and spacing.** Centered `max-width: 1280px` container with `--sp-4` gutters; the shell is a full-width bar with a bottom border (not the old rounded, floated `mx-lg-5 mt-lg-5` navbar); the `bg-dark` hyper-dark body is replaced by the token background + top radial glow. Page content sits in the same container.
- **Focus treatment.** One global `:focus-visible` rule — `2px solid var(--focus)` at `2px` offset, small radius. Applied to every focusable control, not per-component.
- **Skip link.** A "Skip to content" link, off-screen until focused, landing on `#main`.
- **Flash / toast placement.** Flash messages render as **toasts pinned bottom-right**, stacked, `role="status" aria-live="polite"`, dismissible, with a category-coloured left border (`ok`/`warn`/`bad`). This replaces today's inline top alert. (Toast-vs-alert content styling itself is ticket 06.)
- **Responsive collapse.** Below `992px` the nav collapses behind a hamburger that toggles a full-width sheet, whose items keep the same group headings; the two feed icon buttons hide and reappear as a "Feeds" group inside the sheet.
- **Left rail.** Still noted, still not committed — no rail in this shell.

Unblocks **Define responsive and mobile spec** (07) and **Decide heavy-page layouts** (09).

Context: `.scratch/operator-ui-modernization/prototype/shared-shell.html`; tokens from `static/theme.css` contract (ticket 01); icon names per `fa-to-bi-icon-map.md`.
