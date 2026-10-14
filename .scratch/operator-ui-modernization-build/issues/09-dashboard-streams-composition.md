# 09: Dashboard and Streams composition

**What to build:** Dashboard's account cards and streaming cards become token cards, with the streaming grid reusing the shared card grid. Its live log becomes the token log panel (monospace, `--panel2` surface, `--line` border, a fixed-height scroll region, the autoscroll switch unchanged). Streams becomes the reference application of the shared card grid and keeps zero page-local CSS. The three Dashboard poll cadences and Streams' polling are untouched.

**Blocked by:** 06.

**Status:** resolved

- [x] Dashboard's account and streaming cards use the shared card grid and token cards.
- [x] The log renders as the token log panel; autoscroll still works.
- [x] Streams renders as the shared card grid with no page-local CSS.
- [x] All polling intervals are unchanged.
