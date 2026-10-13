# Decide simple-page compositions

Type: wayfinder:grilling
Status: resolved
Blocked by: 05, 06

## Question

Now that the shell (05) and the canonical components (06) are settled, how does each *simpler* page compose within the token/component system — without touching behaviour?

Cover:

- **Blocks** (`blocks.html`): the tab strip, block table, "Default blocks" card, and the per-block channel list.
- **Portals** (`portals.html`): the responsive grid of portal cards, the device-lock switch, and the add/edit modals.
- **Settings** (`settings.html`): the long single form — sectioning, the switch groups, the `input-group` rows, and the save/reset placement.
- **Accounts** (`accounts.html`): the add-account form and the accounts table.
- **Changelog** (`changelog.html`): the versioned-entry list.

For each: the target look, which components it reuses, and any page-local CSS that survives. This is the sibling of **Decide heavy-page layouts** (09), for the pages that fall out of the component decisions.

Consult `grilling` + `domain-modeling`. Output: the simple-page section of the spec.

## Answer

Presentation-only composition for the five simple pages, within the settled components (06) and the container contract (09). Behaviour frozen.

### Cross-cutting

- Simple pages use the shell's **centered container** (not the full-bleed variant).
- Every `<br>`/`<br><br>` spacer and bare `p.text-muted` gives way to token spacing and the muted token.
- Shared **empty state** on every page (blocks, accounts; portals gains one); `btn-block` → `.w-100`; inline pixel widths → token/utility classes.
- The blocks `.nav-tabs` `<style>` block is deleted into `static/theme.css` (already decided in 06; shared with recordings).

### Blocks (`blocks.html`)

- Keep the table with its **table-row expandable channel sub-row** (the `d-none` accordion — behaviour frozen), restyled as the token table.
- Block column → the capped **`.tag` pill stack** (06).
- The five-button per-row cluster → the icon-button component.
- "Default blocks" → a token card; the ad-hoc empty state → the shared component.

### Portals (`portals.html`)

- The `row-cols-auto` tiles → the **shared card grid** (09 §7) of `--panel` token cards.
- The whole-card `stretched-link` click target is kept, with a token hover/border affordance.
- Both add/edit modals restyled to the token modal — **kept as two modals** (merging them is a markup refactor, beyond this presentation-only pass). Their `<br><br>`-spaced fields become canonical token form groups.
- Add the missing **empty state** for "no portals".

### Settings (`settings.html`)

- The nine `h4`+`hr` sections become **card-per-section** — one token card per section with a card header — keeping the single external `form#save`.
- Stray `col-md-*` wrapped in proper rows; overspaced switch groups and `input-group` rows tokenised.
- The lone top-right Save moves into a **sticky action bar** so it stays reachable down the long form.

### Accounts (`accounts.html`)

- Keep the compact admin **table** (tokenised), including the editable Blocks-select and password-reset cells.
- The "Add an account" form → a token card; empty state → the shared component; actions → icon buttons.

### Changelog (`changelog.html`)

- **Bare prose, not carded** (it is a document) in the standard container with a **reading-width cap (~70ch)** and tokenised typography: section borders → `--line`, `code` → `--warn`, heading spacing from tokens.

Context: template survey of the five simple pages (blocks / portals / settings / accounts / changelog) performed in this ticket's session.
