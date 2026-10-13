# Decide canonical component styles

Type: wayfinder:grilling
Status: resolved
Blocked by: 01

## Question

For each shared component, what is the canonical Operator UI treatment — expressed as Bootstrap 5.3 classes plus token overrides in the shared stylesheet?

Cover at least: cards, data tables, form controls and switches, modals, tabs, alerts vs toasts, buttons (incl. icon buttons), badges/pills, empty states.

Also resolve the styles currently duplicated per template into one place:

- The `.nav-tabs` dark override, copy-pasted in `blocks.html:4-13` and `recordings.html:4-13`.
- The `.text-muted` override (`#adb5bd !important`) in `_player.html:28-30,70-72` and `dashboard.html:5-7`.
- `.channel-logo` sizing in `_player.html:37-42` and `multiview.html:79-87`.
- The 17 hardcoded hex values across `_player.html`, `blocks.html`, `recordings.html`, `dashboard.html`, `changelog.html`.

Decide the toast-vs-alert question (there is no success toast today).

**Domain constraint (from the token contract):** a **Channel can be in several Blocks**, so the Block badge/pill component must represent a *set* — a stack of badges, a count + expand, or similar — not a single value. The chosen pattern also has to hold in the Playlist Editor's block column and in the channel lists.

Consult `grilling` + `domain-modeling`. Output: the component section of the spec.

## Answer

The canonical component contract: **Bootstrap 5.3 markup + token overrides in one `static/theme.css`** (per ticket 01's file layout), converging on the Web Viewer's values and component shapes. Ten decisions.

**1. Block-set component.** A Channel can be in several Blocks. Adopt the Viewer's wrapping pill stack (`app.css:395-425`): small `.tag` pills (10px, `--panel2` bg, `--line` border, `--r-pill`), plus `.tag.extra` (accent-tinted) for the primary block. Cap the stack at **3 shown + a `+M` overflow pill** (title lists the rest); a count pill may replace the stack where width is tight. Applies to *read-only* surfaces: the Blocks channel list (`blocks.html:238`), player block choices (`_player.html:934-965`), Multiview picker rows. The **Playlist Editor block column stays a single editable text input** (`editor.html:611-630`) — behaviour frozen; restyled to the token input (decision 6), **not** converted to a chip editor (chip editor out of scope; noted on **Decide heavy-page layouts**).

**2. Alerts vs toasts.** Flash messages render as **bottom-right toasts** (per the shell, ticket 05): `--panel` surface, `--line` border, `--r-md`, category-coloured 3px left border (`--ok` success / `--warn` warning / `--bad` danger / `--accent` info), `role="status" aria-live="polite"`, dismissible. Hand-rolled markup matching `prototype/shared-shell.html`; **no toast library**. Static page-level notices stay inline but drop Bootstrap `.alert-*` colours for token surfaces: neutral → the Viewer's `.notice` (`app.css:152-159`), error → `.error-banner` (`app.css:143-150`); covering `recordings.html:22,25` and `multiview.html:127`. Native `alert()/confirm()/prompt()` untouched (behaviour frozen).

**3. Data table (DataTables 2).** `editor.html`'s `dom:` grid (443-447) is re-expressed as a **`layout:` config**, preserving the visual order (Buttons + dead-filter, then search + length; filter bar; bulk bar; table; info + pager), with the three custom bars (`dead-filter`, `filter-bar`, `bulk-bar`) placed as named `div` features; `initComplete` continues to fill them. `language.lengthMenu: "_MENU_"` (517) replaced by `layout`/`lengthMenu` markup. Keep `buttons`, the `ext.search`/`ext.order` plugins and `orderDataType` defs; `deferRender:false` per ticket 03. The table (header, stripes, `nowrap`, `align-middle`) is styled from tokens; the DT1 class-name audit (ticket 03) precedes. Plain HTML tables (`blocks.html:55,226`, `accounts.html:50`, `guide.html:228`, `recordings.html:119`) share one token table treatment.

**4. Buttons (incl. icon buttons).** One token button system: `primary` → `--accent` bg / `--on-accent` text; `success` → `--ok`; `danger` → `--bad`; `warning` → `--warn`; default and `outline-light` → `--panel2` bg + `--line` border, `--ink` text; `--r-sm`. **Icon-only buttons** become one component: square (`2rem`), min **24×24** hit target, `--r-sm`, `--dim` icon brightening to `--ink` on hover, and a **required `aria-label`** (many lack one today: player bar `_player.html:159-180`, blocks row controls, recordings row controls). `btn-block` (BS4 no-op) → `.w-100` for single buttons / `.d-grid` for stacks, per ticket 03. `btn-close-white` retained. WCAG 2.1 AA on shared controls.

**5. Cards.** One canonical card: `--panel` bg, `1px --line` border, `--r-md`, `--sp-3` padding, header separated by a bottom `--line` border (mirrors the Viewer's `.settings .card`, `app.css:1012-1025`). All `bg-light`/`bg-secondary`/`bg-dark border-secondary`/`text-dark`/`text-light` variants dropped — the tile/card distinction is content, not colour. Applies to `portals.html:77`, `accounts.html:16`, `blocks.html:130`, and the JS-built cards in `streams.html`/`dashboard.html`.

**6. Forms and switches.** One token treatment: `form-control`/`form-select` on `--panel2` with `--line` border, `--r-sm`, `--ink` text, placeholder `--dim`; labels `--dim`; `form-check-input`/`form-switch` filled with `--accent` (off-state `--panel2`/`--line`); `--focus` focus ring; unified `input-group` and `multiple size="1"` selects. Covers every page and the editor's inline cell inputs (`editor.html:584-681`).

**7. Modals.** One token modal: `.modal-content` = `--panel` bg + `--line` border + `--r-lg`, the Viewer's `0 24px 60px rgba(0,0,0,.66)` shadow, backdrop `#000a`, `btn-close-white`. Per-modal size/`modal-dialog-centered`/`modal-dialog-scrollable` classes kept; the portals modals' default-light content dropped. Covers `_record_modal.html`, `recordings.html:44`, `portals.html:120,192`, `_player.html:206`, `multiview.html:133`.

**8. Tabs and duplicated overrides.** A **single canonical `.nav-tabs` token override in `static/theme.css`** (accent-tinted active tab, `--line` bottom border); the byte-identical `<style>` blocks in `blocks.html:4-13` and `recordings.html:4-13` are **deleted**. Multiview's picker pills (`multiview.html:141-145`) are restyled as the Viewer's segmented control (`app.css:741-759`), behaviour unchanged.

**9. Empty states.** One `.empty-state` component: centred `--dim` body text, `--sp-4` padding, optional icon and optional action (`app.css:439-447`); an error variant using `--bad`. The two loader spinners fold into the same component's busy state. Replaces the ~20 ad-hoc empty states (`blocks.html:249,268-294`, `multiview.html:735-753`, `streams.html:81`, `recordings.html:104,115`, `dashboard.html:96`, `_player.html:945,1085`, editor placeholders).

**10. Colour dedup and the shared stylesheet.** All **24** hardcoded hexes (five named files + `multiview.html`) move behind tokens: `#2c3034`→`--panel2`, `#495057`→`--line`, `#adb5bd`→`--dim`, `#f8f9fa`→`--ink`, `#ffc107`→`--focus`/`--star`, `#0d6efd`→`--accent`, `#f8c291`→`--warn`, `#000`/`#111` stay literal (video/fullscreen). `.channel-logo` unifies into one rule (48×28, `object-fit:contain`, `--r-sm`, light mat `--ink`) used by `_player.html` and `multiview.html`. The `.text-muted !important` overrides (`_player.html:28-30,70-72`, `dashboard.html:5-7`) are deleted in favour of `--dim`/`.text-body-secondary`. **`static/theme.css` is the single stylesheet**; per-page `<style>` blocks shrink to genuine page-local layout only (`_player.html`, `multiview.html`, `guide.html`, `changelog.html`).

Unblocks **Define light mode** (08) and **Decide heavy-page layouts** (09). Graduates the "simpler pages" fog into **Decide simple-page compositions** (11).

Context: token contract (ticket 01), shell prototype (ticket 05), convergence target `web/app/src/app.css`; component survey performed in this ticket's session.
