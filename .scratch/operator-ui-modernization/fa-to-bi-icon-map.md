# Font Awesome 4.7 → Bootstrap Icons map

Output of wayfinder ticket **Map Font Awesome 4 icons** (`.scratch/operator-ui-modernization/issues/04-map-font-awesome-icons.md`).

Source: every `fa-*` token in `templates/` (46 distinct, ~50 after the `-o`/solid split), mapped against the Bootstrap Icons **1.13.2** manifest (`bootstrap-icons.json`).

**Weight rule.** FA4 solid icons (no `-o`) map to the BI **`-fill`** glyph where one exists; FA4 `-o` (outline) icons map to the plain BI glyph. This preserves the original visual weight. The literal swap is `<i class="fa fa-x">` → `<i class="bi bi-y">` (drop the `fa` base class, add `bi`).

## Mapping

| FA4 (count) | → Bootstrap Icons | Note |
|---|---|---|
| `fa-play` (7) | `bi-play-fill` | |
| `fa-stop` (4) | `bi-stop-fill` | |
| `fa-step-backward` (3) | `bi-skip-backward-fill` | "watch from the start" |
| `fa-undo` (5) | `bi-arrow-counterclockwise` | |
| `fa-refresh` (4) | `bi-arrow-clockwise` | refresh / reload |
| `fa-spinner` + `fa-spin` (9) | `bi-arrow-repeat` + custom `.bi-spin` | **no BI spin class — see decision 1** |
| `fa-star` (8) | `bi-star-fill` | favourite on |
| `fa-star-o` (5) | `bi-star` | favourite off |
| `fa-bookmark` (5) | `bi-bookmark-fill` | block-favourite on |
| `fa-bookmark-o` (5) | `bi-bookmark` | block-favourite off |
| `fa-circle` (8) | `bi-circle-fill` | status/live dot |
| `fa-check` (1) | `bi-check-lg` | |
| `fa-times` (2) | `bi-x-lg` | |
| `fa-plus` (3) | `bi-plus-lg` | |
| `fa-ban` (2) | `bi-slash-circle-fill` | dead/mark-dead |
| `fa-exclamation-triangle` (1) | `bi-exclamation-triangle-fill` | |
| `fa-eye` (1) | `bi-eye-fill` | block visible |
| `fa-eye-slash` (1) | `bi-eye-slash-fill` | STB-Proxy-only |
| `fa-lock` (2) | `bi-lock-fill` | |
| `fa-key` (1) | `bi-key-fill` | API token |
| `fa-pencil` (1) | `bi-pencil-fill` | rename block |
| `fa-trash` (2) | `bi-trash-fill` | |
| `fa-save` (4) | `bi-save` | |
| `fa-download` (1) | `bi-download` | |
| `fa-exchange` (1) | `bi-arrow-left-right` | swap |
| `fa-user` (2) | `bi-person-fill` | |
| `fa-users` (1) | `bi-people-fill` | Accounts |
| `fa-sliders` (1) | `bi-sliders` | Settings |
| `fa-server` (4) | `bi-server` | Portals |
| `fa-dashboard` (1) | `bi-speedometer2` | Dashboard nav |
| `fa-signal` (1) | `bi-broadcast` | **BI `signal` is the Signal brand — see decision 2** |
| `fa-television` (2) | `bi-tv` | |
| `fa-film` (1) | `bi-film` | |
| `fa-list` (1) | `bi-list-ul` | |
| `fa-list-alt` (2) | `bi-card-list` | channel guide |
| `fa-th` (2) | `bi-grid-3x3-gap` | |
| `fa-th-large` (5) | `bi-grid` | 2×2; Blocks nav + picker |
| `fa-file-video-o` (1) | `bi-file-earmark-play` | Playlist nav |
| `fa-file-code-o` (1) | `bi-file-earmark-code` | XMLTV nav |
| `fa-clock-o` (2) | `bi-clock` | |
| `fa-chevron-up/down/left/right` (2/3/1/1) | `bi-chevron-up/down/left/right` | |
| `fa-arrow-up` / `fa-arrow-down` (1/1) | `bi-arrow-up` / `bi-arrow-down` | |
| `fa-expand` (3) / `fa-compress` (2) | `bi-fullscreen` / `bi-fullscreen-exit` | **overloaded — see decision 4** |
| `fa-arrows-alt` (2) | `bi-arrows-angle-expand` | "make big" tile |
| `fa-volume-off` (2) / `fa-volume-up` (1) | `bi-volume-mute-fill` / `bi-volume-up-fill` | |
| `fa-window-minimize` (2) / `fa-window-restore` (1) | `bi-dash-lg` / `bi-window` | **no exact BI window glyph — see decision 3** |

`fa-spin` is an animation modifier, not an icon: keep it as `fa-spin`→ a small `.bi-spin` utility in `theme.css`.

## Open decisions (for the component/shell tickets)

1. **Spinner.** Bootstrap Icons ships **no** spin animation class. Add a ~3-line `@keyframes spin` + a `.bi-spin { animation: spin 1s linear infinite }` utility to `static/theme.css`. (Cheap; recommend yes.)
2. **`fa-signal` → `bi-broadcast`, not `bi-signal`** — BI's `signal` is the Signal messenger logo. Cosmetic choice for the **Streams** nav; `bi-broadcast` or `bi-activity` both fit.
3. **Window controls.** No `bi-window-minimize`/`-restore`. Recommended stand-ins: `fa-window-minimize` → `bi-dash-lg`; `fa-window-restore` → `bi-window` (alternatives: `bi-arrows-angle-expand`/`-contract`). Visual judgement — decide in **Design shared shell** / **Decide heavy-page layouts**.
4. **`fa-expand`/`fa-compress` are overloaded.** In `_player.html` they mean fullscreen on/off (→ `bi-fullscreen`/`bi-fullscreen-exit`); in `multiview.html:374` `fa-compress` means "shrink the big tile" (→ `bi-arrows-angle-contract`), paired with `fa-arrows-alt`. One class cannot become two glyphs, so the Multiview tile JS should emit the `bi-arrows-angle-expand`/`-contract` pair while the player keeps `bi-fullscreen`/`-exit`. Presentation-only (glyph swap), no behaviour change.
