# 05: Rebuild the shared shell

**What to build:** The frame every page inherits. One grouped top bar: the ten internal destinations ordered and separated by role — **Monitor** (Dashboard, Streams, Recordings, Multiview) · **Programme** (Playlist Editor, Guide, Blocks) · **Configuration** (Portals, Accounts, Settings) — with the two feeds (`/playlist`, `/xmltv`) demoted to icon-only ghost buttons at the right end (title + `target="_blank"`) and the Changelog as the version chip beside the brand. The active page gets `aria-current="page"` plus a filled accent pill. Add a skip link to `#main`, one global `:focus-visible` ring (`2px solid var(--focus)` at `2px` offset), flash messages as stacked bottom-right toasts (`role="status" aria-live="polite"`, dismissible, category-coloured left border), a centered `max-width:1280px` container with a full-bleed variant for edge-to-edge pages, and a hamburger collapse below `992px` (items keep the group headings; feeds reappear as a "Feeds" group).

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] The nav is grouped as specified, with feed icon buttons and the changelog version chip.
- [ ] The active page carries `aria-current="page"` and a filled pill.
- [ ] A skip link lands on `#main`; one global focus ring shows on every focusable control.
- [ ] Flash messages render as dismissible bottom-right toasts.
- [ ] One container (plus full-bleed variant) replaces the old per-page padding; the floated navbar is gone.
- [ ] Below 992px the nav collapses behind a hamburger sheet.
- [ ] Source-string tests are updated and green.
