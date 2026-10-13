# Decide canonical component styles

Type: wayfinder:grilling
Status: open
Blocked by: 01

## Question

For each shared component, what is the canonical Operator UI treatment — expressed as Bootstrap 5.3 classes plus token overrides in the shared stylesheet?

Cover at least: cards, data tables, form controls and switches, modals, tabs, alerts vs toasts, buttons (incl. icon buttons), badges/pills, empty states.

Also resolve the styles currently duplicated per template into one place:

- The `.nav-tabs` dark override, copy-pasted in `blocks.html:4-13` and `recordings.html:4-13`.
- The `.text-muted` override (`#adb5bd !important`) in `_player.html:28-30,70-72` and `dashboard.html:5-7`.
- `.channel-logo` sizing in `_player.html:37-42` and `multiview.html:79-87`.
- The 17 hardcoded hex values across `_player.html`, `blocks.html`, `recordings.html`, `dashboard.html`, `changelog.html`.

Decide the toast-vs-alert question (there is no success toast today).

**Domain constraint (from the token contract):** a **Channel can be in several Blocks**, so the Block badge/pill component must represent a *set* — a stack of badges, a count + expand, or similar — not a single value. The chosen pattern also has to hold in the Playlist Editor's block column and in the channel lists.

Consult `grilling` + `domain-modeling`. Output: the component section of the spec.
