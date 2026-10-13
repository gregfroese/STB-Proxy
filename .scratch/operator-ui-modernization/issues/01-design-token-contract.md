# Design-token contract

Type: wayfinder:prototype
Status: resolved

## Question

What is the canonical design-token contract the Operator UI adopts?

Express it as CSS custom properties covering the semantic roles the UI needs:

- **Colour**: background, surface, raised surface, border/line, primary text, muted text, accent, on-accent, focus, plus `ok`/`warn`/`bad` and their tint fills/borders. Map these from the Web Viewer's palette (`web/app/src/app.css:1-15`) and extend where the Operator UI needs more than the Viewer has — the Viewer declares `--warn` but never uses it, and has no success/`ok` toast component.
- **Type**: font stacks (system-ui body, mono), size scale, weights, line-heights.
- **Spacing**: a rhythm (the Viewer repeats 8/10/12/14px literals — decide whether to tokenise or keep literals).
- **Radius**: the Viewer's 6–20px ladder.
- **Shadow / elevation**: the Viewer is border-led with one modal shadow; decide what the Operator UI needs.

Decide the naming convention and file layout (`static/theme.css`? one file or tokens+components?).

**Prototype** this as a draft `theme.css` plus a demo page showing the tokens applied to a representative set of Operator UI elements (a card, a data table, form controls/switches, a modal, an alert, a badge), so the human can react to the look before it is applied anywhere.

HITL: iterate the prototype with the operator.

## Answer

**Variant A — "Converged" wins.** The Operator UI adopts the Web Viewer's palette literally; convergence is exact, not approximate. Prototype (all three directions, retained as the primary source): [`prototype/theme-tokens.html`](../prototype/theme-tokens.html) — A is the winner, B/C kept only as the record of what was weighed and rejected.

### File layout

- One stylesheet, `static/theme.css`, mirrors the Web Viewer's single-file approach (`web/app/src/app.css`). Tokens live in a `:root` block at the top; component overrides (ticket 06) layer beneath in the same file. **Values are copied from the Web Viewer, not the file — the two codebases stay separate.**

### Colour tokens (`:root`)

```
--bg:      #0d1117;    /* page */
--bg-glow: 24,34,51;   /* top radial glow (kept as RGB triple for rgb()) */
--panel:   #161b22;    /* surface: cards, bars */
--panel2:  #1c2330;    /* raised: inputs, buttons, chips */
--line:    #2b3542;    /* borders */
--ink:     #e6edf3;    /* text */
--dim:     #8b98a7;    /* muted text */
--accent:  #3ba6ff;    /* primary */
--on-accent:#04121f;   /* text on accent */
--focus:   #ffd34d;    /* focus ring */
--star:    #ffd34d;    /* favourites (alias of focus) */
--ok:      #3fb950;    /* success — NEW use vs the Viewer */
--warn:    #e3b341;    /* warning — the Viewer declares this but never uses it */
--bad:     #f85149;    /* danger */
```

**Semantic tints** are derived with `color-mix(in srgb, <token> N%, transparent)` rather than the Viewer's hand-baked tint hexes (`#3ba6ff1a`…): ~12–16% for fills, ~40% for borders. This keeps tints in step with the base token automatically.

The semantic set is **extended beyond the Web Viewer**, which is dark-only, leaves `--warn` unused and has no `ok`/success surfaces — required because the Operator UI surfaces `ok` (saved, Plex in sync), `warn` (partial recordings) and `bad` (dead channels, Plex unreachable).

### Type, spacing, radius, elevation

- Fonts: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`; mono `ui-monospace, SFMono-Regular, Menlo, monospace`. System fonts — no webfont, no CDN.
- Sizes: `11/12/13/14/15/16/18/20`px, body **13px**. Weights `400/600/700/800`. `-webkit-font-smoothing: antialiased`. No letter-spacing except uppercase section headers.
- Spacing rhythm: `--sp-1..4 = 6/10/14/20`px (the Viewer repeats 8/10/12/14px literals; slight change, tokenised).
- Radius: `--r-sm/md/lg/pill = 8/10/14/999`px. Border-led; shadows kept minimal (`0 1px 0 rgba(0,0,0,.25)` ambient, `0 24px 60px rgba(0,0,0,.66)` for modals).

### Domain constraint carried forward

A **Channel can be in several Blocks** (`GLOSSARY.md`). The gallery's single "Block" badge is illustrative only — the component contract must represent a *set* of blocks per channel (a stack of badges, or a count + list), not one. Flagged on **Decide canonical component styles** and **Decide heavy-page layouts**.

Context: `.scratch/operator-ui-modernization/prototype/theme-tokens.html`; tokens lifted from `web/app/src/app.css:1-15`.
