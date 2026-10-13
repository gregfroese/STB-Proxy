# Map Font Awesome 4 icons

Type: wayfinder:task
Status: open

## Question

What is the icon-for-icon replacement table from Font Awesome 4.7 to Bootstrap Icons?

Enumerate every Font Awesome class used across `templates/` (~50 distinct icons over 13 templates; `_player.html` 18, `multiview.html` 19, `blocks.html` 16, `base.html` 12, `recordings.html` 11, `dashboard.html` 10, the rest fewer) and give each its Bootstrap Icons name.

Pay attention to the FA4-only and renamed icons that render blank on any modern set:

- `-o` outline variants: `fa-bookmark-o`, `fa-star-o`, `fa-file-video-o`, `fa-file-code-o`, `fa-clock-o`.
- Renamed: `fa-dashboard` (→ gauge), `fa-refresh`, `fa-arrows-alt`, `fa-exclamation-triangle`, `fa-list-alt`.

Flag any icon with no clean Bootstrap Icons equivalent as an **open decision** (alternate icon, or a small inline SVG) rather than guessing.

Output: a mapping table (old class → new class → file:line), plus the list of open decisions. AFK-able; no human input needed unless an icon is genuinely unmappable.
