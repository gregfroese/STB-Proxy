# 12: Portals, Settings and Changelog composition

**What to build:** Portals' tiles become the shared card grid of token cards, with the whole-card click target kept and given a token hover/border affordance; both add/edit modals are restyled to the token modal (kept as two modals — merging is a refactor, out of scope); the `<br><br>`-spaced fields become token form groups; and the missing "no portals" empty state is added. Settings' nine `h4`+`hr` sections become card-per-section (one token card each, with a card header) keeping the single external form; stray `col-md-*` are wrapped in rows; the Save moves into a sticky action bar. Changelog becomes bare prose (not carded) in the standard container with a ~70ch reading cap and tokenised typography (section borders → `--line`, `code` → `--warn`).

**Blocked by:** 06.

**Status:** ready-for-agent

- [ ] Portals renders as the shared card grid; both modals are token-styled; the empty state appears.
- [ ] Settings' sections are cards; Save is reachable via a sticky bar; no stray `col-md-*`.
- [ ] Changelog prose is capped at ~70ch and token-styled.
- [ ] Behaviour is unchanged.
