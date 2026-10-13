# 11: Blocks and Accounts composition

**What to build:** Blocks keeps its table with the expandable per-block channel sub-row (the `d-none` accordion), restyled as the token table; the Block column becomes the capped `.tag` pill stack (3 shown + a `+M` overflow pill, title lists the rest) so a Channel in several Blocks is represented honestly; the five-button per-row cluster becomes icon buttons with `aria-label`s; "Default blocks" is a token card; the ad-hoc empty state becomes the shared component. Accounts keeps its compact admin table (tokenised), including the editable Blocks-select and password-reset cells; the add-account form becomes a token card; actions are icon buttons; the empty state is the shared component.

**Blocked by:** 06.

**Status:** ready-for-agent

- [ ] Block membership renders as a capped pill stack with a `+M` overflow whose title lists the rest.
- [ ] The row accordion still expands and collapses.
- [ ] The Accounts admin table is tokenised; add-account is a token card.
- [ ] Both pages use the shared empty state; icon actions carry `aria-label`s.
- [ ] Behaviour is unchanged.
