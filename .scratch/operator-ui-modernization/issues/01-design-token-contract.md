# Design-token contract

Type: wayfinder:prototype
Status: open

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
