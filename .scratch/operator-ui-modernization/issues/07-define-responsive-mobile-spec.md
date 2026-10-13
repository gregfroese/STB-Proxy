# Define responsive and mobile spec

Type: wayfinder:grilling
Status: resolved
Blocked by: 05

## Question

What are the responsive breakpoints and behaviours for the Operator UI?

The app has exactly one hand-written media query today (`multiview.html:103`) plus Bootstrap's grid utilities. Decide:

- How the shell collapses on phone width (ties to the shared shell, ticket 05).
- Which pages get real mobile attention, and which are desktop-only-in-practice. Concrete "usable, not optimal" criteria per page.
- Any layout that is actively broken on mobile today and must be fixed (Multiview's `calc(100vh - 190px)` grid, the docked preview player, the wide editor table).
- Whether to introduce a small, named breakpoint scale into the token contract.

Consult `grilling` + `domain-modeling`. Output: the responsive section of the spec.

## Answer

The responsive and mobile section of the spec. Six decisions, taken against Bootstrap 5.3 as the grid substrate.

**1. Breakpoint scale — ride Bootstrap, add no tokens.** Bootstrap 5.3's five defaults are *the* scale: `sm 576 · md 768 · lg 992 · xl 1200 · xxl 1400`. No `--bp-*` custom properties: CSS custom properties cannot appear in `@media` conditions, so a token scale could not drive a query. Pages keep using BS responsive grid classes (`col-md-*`); hand-written media queries are reserved for layouts Bootstrap cannot express. Exactly two breakpoints carry behaviour: **992px** (shell collapse, per ticket 05) and **576px** (Multiview tile stack). Recorded as a comment in `static/theme.css` and as this spec section.

**2. Shell collapse — unchanged from *Design shared shell* (05).** Below 992px the nav becomes a hamburger sheet keeping the same role-group headings; the two feed icon buttons hide and reappear as a "Feeds" group inside the sheet.

**3. Page tiers.** *Tier A — genuinely usable at 360px:* **Dashboard, Streams, Blocks, Multiview**. *Tier B — desktop-first, graceful only* (horizontal scroll inside `table-responsive` is the accepted behaviour): **Playlist Editor, Guide, Recordings, Portals, Accounts, Settings**. Changelog is trivially fine either way.

**4. "Usable, not optimal" bar (Tier A).** (1) at 360px, no horizontal page scroll except inside an explicit `table-responsive` wrapper; (2) every primary action reachable without pinch-zoom; (3) nav reachable via the hamburger; (4) no fixed-height viewport trap (no `100vh` maths that clips content); (5) best-effort 24×24 tap targets on shared controls — best-effort, as WCAG 2.1 AA has no target-size rule; (6) reduced-motion respected for transitions this effort introduces.

**5. Broken-layout fixes.** Only **Multiview** is genuinely broken: `height: calc(100vh - 190px)` (`multiview.html:9`) hard-codes a nav height the hamburger changes, so the grid overflows or leaves a gap. Replace with a shell-relative fill (`100dvh` with a `100vh` fallback, or a flex column consuming the post-nav space); keep the existing ≤576px tile stack (`multiview.html:103`), and `#mvDivider` is already hidden on phone. The **docked player** (`_player.html`, already `min()`-guarded) and the **Editor table** (`editor.html`, already inside `table-responsive`) are verified not broken / accepted scroll — explicitly not reworked.

**6. Viewport units, safe areas, and narrow fixed chrome.** Full-height surfaces use `height: 100dvh` with a `100vh` fallback (Multiview after the fix, the fullscreen player). Fixed-corner chrome (docked player panel, toasts) is padded with `env(safe-area-inset-bottom/right)` so it clears a phone's home indicator. Below 992px flash toasts become full-width bottom strips (safe-area padded) and stack **above** the docked player panel when one is open; above 992px the bottom-right toast treatment from ticket 05 is unchanged.

Unblocks **Define release sequencing and convergence** (10) once 08/09/11 land. Context: shell prototype `prototype/shared-shell.html` (ticket 05); Breakpoint scale documented against Bootstrap 5.3.8 (ticket 03).
