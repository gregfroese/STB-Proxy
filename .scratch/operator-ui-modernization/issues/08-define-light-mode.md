# Define light mode

Type: wayfinder:prototype
Status: open
Blocked by: 01, 06

## Question

What is the light-mode token set and the mechanism that switches to it?

Decide:

- The light values for every colour token defined in ticket 01 (the Web Viewer is dark-only, so this is net-new design work; it must still read as the same product).
- The toggle mechanism: Bootstrap 5.3 `data-bs-theme`, `prefers-color-scheme` as the default, and where the manual override persists (localStorage?).
- Which components need light-specific adjustment (borders/glass overlays that assume dark, table striping, overlays).

**Prototype** the light token set (and, if useful, a side-by-side of one page), for the human to react to. HITL.

Consult `grilling` + `domain-modeling`. Output: the theming section of the spec.
