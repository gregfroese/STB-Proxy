# 08: Multiview composition

**What to build:** Multiview keeps its page-local CSS — the five `[data-layout]` grid templates, the absolutely-positioned tile chrome, the drag divider, fullscreen and the mobile stack — but every colour and radius comes from tokens, and the `calc(100vh − 190px)` height coupling becomes `dvh` with a fallback. The picker modal's tabs/pills/list adopt the shared tab and list components; the record modal is the shared modal. The `#ffc107` playing ring maps to `--focus`/`--star`. Behaviour is unchanged.

**Blocked by:** 06.

**Status:** resolved

- [x] All five layouts, the drag divider, fullscreen and the ≤576px mobile stack still work.
- [x] Tile chrome, progress bar and messages render from tokens; the playing ring uses `--focus`/`--star`.
- [x] The grid height uses `dvh` (with a fallback) and sizes correctly on mobile browsers.
- [x] The picker and record modals are token-styled.
