# Define release sequencing and convergence

Type: wayfinder:grilling
Status: open
Blocked by: 05, 06, 07, 08, 09

## Question

How does the resulting spec slice into shippable releases, and what exactly is the "shared product look" boundary with the Web Viewer?

Decide:

- The release order (likely: vendored/upgraded stack → tokens + shell → components → heavy pages → light mode), sized so each release is independently shippable under the repo's per-change version bump + CHANGELOG rule.
- For each release: what moves, what is left untouched, and the manual verification pass.
- The convergence boundary: which values the Operator UI and the Web Viewer share (the token palette) and the explicit rule that they share *values, not code*.
- What, if anything, becomes a follow-on map (candidate: dropping Bootstrap; candidate: dropping DataTables/jQuery).

This closes the map: its answer plus the preceding tickets are the spec. Consult `grilling` + `domain-modeling`.
