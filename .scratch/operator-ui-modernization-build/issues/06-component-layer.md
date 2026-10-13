# 06: Component layer in the stylesheet

**What to build:** The canonical component contract, as overrides in `static/theme.css` (so pages inherit it without markup churn): cards (`--panel` + `--line` + header rule); data tables (header/stripes/`align-middle`); forms and switches (controls on `--panel2` with **`--line-strong`** borders, `--accent` switches); buttons incl. one icon-button component (square, min 24×24, `--dim`→`--ink` on hover); a single `.nav-tabs` override; modals; static notices/error surfaces; badges (**label text `--ink`**, semantic colour via tint + border + dot); one `.empty-state` (with busy and error variants); the log panel; and the shared card grid (`row-cols-1 / md-2 / xl-3`, `g-3`). Delete the duplicated per-template CSS (the dark `.nav-tabs` overrides, the `.text-muted !important` patches, `.channel-logo`, `.programme-desc`) and move all 24 hardcoded hexes behind tokens.

**Blocked by:** 05.

**Status:** ready-for-agent

- [ ] Every listed component renders from tokens; no page-local dark overrides or hardcoded hexes remain.
- [ ] Interactive boundaries use `--line-strong`; badge labels use `--ink`; the focus ring is AA-visible.
- [ ] The card grid is available as the shared treatment.
- [ ] The computed-contrast test passes.
