# Decide heavy-page layouts

Type: wayfinder:grilling
Status: open
Blocked by: 05, 06

## Question

What are the layout decisions for the complex pages, restyled within the token/component system (and without touching behaviour)?

Cover:

- **Playlist Editor** (`editor.html`, 691 lines): the DataTables grid plus the filter bar and bulk-action bar built as HTML strings in JS (`editor.html:452-498`). How it presents in the new style.
- **Multiview** (`multiview.html`, 893 lines): the custom CSS-grid layouts and tiles; whether its bespoke CSS is absorbed into tokens or kept page-local.
- **Dashboard** (`dashboard.html`): the account cards, streaming grid, and auto-refreshing log.
- **Guide** (`guide.html`): search bar, mode select, filter switches, results table.
- **Recordings** and **Streams**: tabs/cards and the live-polling lists.

For each: the target look, which components it reuses, and any page-local CSS that survives.

**Domain constraint (from the token contract):** a **Channel can be in several Blocks**. The Block column in the Playlist Editor and the block display in Blocks/Multiview must show a set of blocks per channel, not one — see **Decide canonical component styles** for the badge pattern this reuses.

Consult `grilling` + `domain-modeling`. Output: the per-page section of the spec.
