# Design shared shell

Type: wayfinder:prototype
Status: open
Blocked by: 01

## Question

How does the shared shell (the frame every page inherits from `base.html`) look and behave?

Decide and prototype:

- **Navigation grouping**: today the navbar crams 11 items (`base.html:34-72`), including meta/external links (Playlist, XMLTV, Changelog). Decide the grouping — which are primary, which fold into a menu or the version link.
- **Active-page indication**: add `aria-current`/active styling (absent today).
- **Containers and spacing**: reconcile the per-page `p-lg-5`, cards, and the `bg-dark` hyper-dark shell with the new tokens.
- **Focus treatment**: `focus-visible` styling across nav and controls (absent today).
- **Skip link** to the content.
- **Flash/toast placement**: where `get_flashed_messages` renders and how it looks against the new style.
- **Responsive collapse**: how the nav behaves at phone width.

**Prototype** an HTML mock of the shell (nav + container + a placeholder content block + a flash message) using the token contract from ticket 01, for the human to react to. HITL.

Deliberately note (do not decide here): whether the shell eventually becomes a left rail.
