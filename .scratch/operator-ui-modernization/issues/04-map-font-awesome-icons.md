# Map Font Awesome 4 icons

Type: wayfinder:task
Status: resolved

## Question

What is the icon-for-icon replacement table from Font Awesome 4.7 to Bootstrap Icons?

Enumerate every Font Awesome class used across `templates/` (~50 distinct icons over 13 templates; `_player.html` 18, `multiview.html` 19, `blocks.html` 16, `base.html` 12, `recordings.html` 11, `dashboard.html` 10, the rest fewer) and give each its Bootstrap Icons name.

Pay attention to the FA4-only and renamed icons that render blank on any modern set:

- `-o` outline variants: `fa-bookmark-o`, `fa-star-o`, `fa-file-video-o`, `fa-file-code-o`, `fa-clock-o`.
- Renamed: `fa-dashboard` (→ gauge), `fa-refresh`, `fa-arrows-alt`, `fa-exclamation-triangle`, `fa-list-alt`.

Flag any icon with no clean Bootstrap Icons equivalent as an **open decision** (alternate icon, or a small inline SVG) rather than guessing.

Output: a mapping table (old class → new class → file:line), plus the list of open decisions. AFK-able; no human input needed unless an icon is genuinely unmappable.

## Answer

Done. Full table (46 distinct icons, grouped with counts and notes): [`fa-to-bi-icon-map.md`](../fa-to-bi-icon-map.md).

Convention: `<i class="fa fa-x">` → `<i class="bi bi-y">`; FA4 solid → BI `-fill`, FA4 `-o` → BI outline, preserving weight. Verified every target exists in the Bootstrap Icons 1.13.2 manifest.

Four open decisions surfaced (each belongs to a later, already-charted ticket):

1. **Spinner** — BI has no spin class; add a small `@keyframes spin` + `.bi-spin` to `theme.css`.
2. **`fa-signal`** — BI's `signal` is the Signal brand; use `bi-broadcast` for the Streams nav.
3. **Window minimize/restore** — no exact glyph; stand-ins `bi-dash-lg` / `bi-window`.
4. **`fa-expand`/`fa-compress` overloaded** (fullscreen in the player vs shrink-tile in Multiview) — split the glyphs; presentation-only.

Context: `fa-to-bi-icon-map.md`; source manifest `bootstrap-icons@1.13.2`.
