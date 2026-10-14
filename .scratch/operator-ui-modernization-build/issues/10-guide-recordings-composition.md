# 10: Guide and Recordings composition

**What to build:** Guide's search-first filter bar becomes the shared toolbar pattern; its JS-built results table adopts the token table; the `.programme-desc` 2-line clamp moves into `theme.css`; the status line uses the shared notice/empty-state. Recordings adopts the single shared `.nav-tabs` override, token tables for both lists, token notice/error surfaces for the "recording off" and list-error messages, and a token `modal-xl` for playback. Behaviour is unchanged.

**Blocked by:** 06.

**Status:** resolved

- [x] Guide's filter bar matches the shared toolbar; results are token-styled; the status line uses the shared component.
- [x] Recordings' tabs use the shared override; both lists are token tables; the two messages are token surfaces.
- [x] The `.programme-desc` clamp lives in `theme.css`.
- [x] Filtering, polling and playback behave exactly as before.
