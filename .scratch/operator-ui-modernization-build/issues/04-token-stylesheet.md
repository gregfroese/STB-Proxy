# 04: Add the token stylesheet

**What to build:** One `static/theme.css` holding the dark design-token contract, referenced from the shared shell. Tokens cover colour (`--bg`, `--bg-glow`, `--panel`, `--panel2`, `--line`, `--line-strong`, `--ink`, `--dim`, `--accent`, `--on-accent`, `--focus`, `--star`, `--ok`, `--warn`, `--bad`), type (system fonts, the size scale, body 13px), spacing (`--sp-1..4`), radius (`--r-sm/md/lg/pill`) and elevation. Semantic tints derive with `color-mix(...)` off the base tokens. Add a token-presence test.

**Blocked by:** 01.

**Status:** resolved

- [x] `static/theme.css` exists, is referenced by the shell, and defines the full token set.
- [x] A test asserts the token set is present.
- [x] The page background, text and fonts adopt the tokens; the top radial glow renders.
- [x] Semantic tints are `color-mix`-derived (no hand-baked tint hexes).
