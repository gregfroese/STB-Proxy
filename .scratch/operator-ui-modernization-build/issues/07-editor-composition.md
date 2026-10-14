# 07: Playlist Editor composition

**What to build:** The Playlist Editor's layout within the component system. Its filter bar, bulk bar and dead-filter switches become one bordered toolbar panel above the table (filter row always visible; bulk row only when rows are selected; dead-filter switches as a third row), restyled from the injected DataTables rows. The grid adopts the token table. Every icon button gets a required `aria-label`. The Block column stays a single editable text input (no chip editor). Horizontal scroll is accepted (Tier B, desktop-first). Behaviour is unchanged.

**Blocked by:** 02, 06.

**Status:** resolved

- [x] The toolbar is one panel; the filter, bulk and dead-filter rows render as specified.
- [x] The grid is token-styled; the Block cell is a token text input.
- [x] Icon buttons carry `aria-label`s.
- [x] Editing, filtering and bulk actions behave exactly as before.
