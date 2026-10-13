# Decide heavy-page layouts

Type: wayfinder:grilling
Status: resolved
Blocked by: 05, 06

## Question

What are the layout decisions for the complex pages, restyled within the token/component system (and without touching behaviour)?

Cover:

- **Playlist Editor** (`editor.html`, 691 lines): the DataTables grid plus the filter bar and bulk-action bar built as HTML strings in JS (`editor.html:452-498`). How it presents in the new style.
- **Multiview** (`multiview.html`, 893 lines): the custom CSS-grid layouts and tiles; whether its bespoke CSS is absorbed into tokens or kept page-local.
- **Dashboard** (`dashboard.html`): the account cards, streaming grid, and auto-refreshing log.
- **Guide** (`guide.html`): search bar, mode select, filter switches, results table.
- **Recordings** and **Streams**: tabs/cards and the live-polling lists.

For each: the target look, which components it reuses, and any page-local CSS that survives.

**Domain constraint (from the token contract):** a **Channel can be in several Blocks**. The Block column in the Playlist Editor and the block display in Blocks/Multiview must show a set of blocks per channel, not one — see **Decide canonical component styles** for the badge pattern this reuses.

Consult `grilling` + `domain-modeling`. Output: the per-page section of the spec.

## Answer

Presentation-only composition for the six heavy pages, within the settled token/component system (06), shell (05) and responsive tiers (07). Behaviour is frozen; the surviving page-local CSS is minimal.

### 1. Container & spacing contract

One container: the shell's centered `max-width:1280px` with `--sp-4` gutters, plus a **full-bleed variant sharing the same gutters** for the edge-to-edge pages (editor, multiview, dashboard, streams). The `.container`/`.container-fluid` and `p-lg-5`/`px-lg-5` lottery, and the floated `mx-lg-5` navbar, go away.

### 2. Playlist Editor (`editor.html`)

- Toolbar = **one bordered toolbar panel above the table**, composed from the DataTables-injected `layout` rows (mechanism per 06): filter row always visible; bulk row only when rows are selected; dead-filter switches as a third row. No authored-markup change — restyle the generated wrappers.
- Table keeps its inline `min-width`s; **horizontal scroll is accepted** (Tier B / desktop-first, per 07).
- Block column stays the single editable text input (06); no chip editor.

### 3. Multiview (`multiview.html`)

- **Bespoke CSS stays page-local** (a `multiview.html` `<style>` block): the five `[data-layout]` grid templates, the absolutely-positioned tile chrome (header/progress/message), the drag divider, fullscreen, and the ≤575.98px mobile stack.
- All colours/radii come from tokens; `calc(100vh − 190px)` → `dvh` + fallback (07).
- The picker modal's tabs/pills/list adopt the shared tab + list components; the record modal is the shared modal.

### 4. Dashboard (`dashboard.html`)

- Account cards + streaming cards → token cards; the streaming grid reuses the shared card grid (§7).
- Log → token **log panel**: monospace, `--panel2` surface, `--line` border, a fixed-height scroll region (kept — a log needs one), autoscroll switch unchanged.
- The three poll cadences are untouched.

### 5. Guide (`guide.html`)

- Filter bar → the shared toolbar pattern (same as the editor's, §2).
- JS-built results table → the shared token table.
- `.programme-desc` 2-line clamp → `static/theme.css`.
- `#guideStatus` → the shared notice/empty-state.

### 6. Recordings (`recordings.html`)

- Tabs → the single shared `.nav-tabs` override (06).
- Both JS-built lists → the shared token table.
- "recording off" / `#listError` → token notice/error surfaces (06).
- Playback stays a token `modal-xl`.

### 7. Streams (`streams.html`) — canonical card grid

`row-cols-1 / md-2 / xl-3`, `g-3` is the **shared card-grid treatment**; dashboard's streaming cards (and any future card list) reuse it. Streams keeps zero page-local CSS.

### 8. Surviving page-local CSS

Only **Multiview's grid/tiles/fullscreen** (§3) and the **editor's DataTables `layout` config** (no CSS). Everything else — the duplicated dark `.nav-tabs` override, the `.text-muted !important` patches, `.channel-logo`, `.programme-desc`, and the `#2c3034`/`#495057`/`#f8f9fa` hexes — moves into `static/theme.css`.

Context: template survey of the six heavy pages (editor / multiview / dashboard / guide / recordings / streams) performed in this ticket's session.
