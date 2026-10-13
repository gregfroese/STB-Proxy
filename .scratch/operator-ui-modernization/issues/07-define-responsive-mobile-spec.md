# Define responsive and mobile spec

Type: wayfinder:grilling
Status: open
Blocked by: 05

## Question

What are the responsive breakpoints and behaviours for the Operator UI?

The app has exactly one hand-written media query today (`multiview.html:103`) plus Bootstrap's grid utilities. Decide:

- How the shell collapses on phone width (ties to the shared shell, ticket 05).
- Which pages get real mobile attention, and which are desktop-only-in-practice. Concrete "usable, not optimal" criteria per page.
- Any layout that is actively broken on mobile today and must be fixed (Multiview's `calc(100vh - 190px)` grid, the docked preview player, the wide editor table).
- Whether to introduce a small, named breakpoint scale into the token contract.

Consult `grilling` + `domain-modeling`. Output: the responsive section of the spec.
