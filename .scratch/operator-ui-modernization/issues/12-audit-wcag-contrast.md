# Audit focus/contrast against WCAG 2.1 AA

Type: wayfinder:grilling
Status: resolved
Blocked by: 09, 11

## Question

Now that both token sets are settled — dark (ticket 01) and light (ticket 08) — what are the focus/contrast specifics beyond the shell baseline?

Decide:

- The contrast ratios of every foreground/background token pairing the UI actually uses, computed for **both** modes: body/muted text on `--bg`/`--panel`/`--panel2`; `--on-accent` on `--accent`; each semantic colour (`--ok`/`--warn`/`--bad`) on its tinted fill and border; the `--focus` ring against every surface it lands on; badge/pill text on its tint.
- Which pairings fail AA (4.5:1 body text, 3:1 large text and UI/graphic boundaries) and the **token adjustments** that fix them (per mode), without breaking convergence with the Web Viewer where the Viewer shares the value.
- The focus-visible treatment across components — buttons, links, inputs, switches, table rows, Multiview tiles, the editor grid — in both modes.

This is the last decision before **Define release sequencing and convergence** can close the map. Consult `grilling` + `domain-modeling`. Output: the accessibility section of the spec.

## Answer

Contrast ratios computed for every token pairing the UI uses, both modes (WCAG 2.1; 4.5:1 body text, 3:1 large text / UI boundaries / focus).

### Passing baseline (no change)

- Body/muted text on surfaces: `--ink` on bg/panel/panel2 = **13.3–16.0** (dark) / **13.9–15.8** (light); `--dim` = **5.4–6.4** / **5.4–6.1**.
- `--on-accent` on `--accent` = **7.27** / **5.19**; accent as link text on bg/panel = **6.7–7.3** / **4.9–5.2**.
- Semantic text on `--panel`: `--ok`/`--warn`/`--bad` = **5.2–8.9** / **4.9–5.4**.
- Filled buttons: with `--on-accent` text, dark (near-black) passes on every fill and light (white) passes on every fill — see §5.
- Dark `--focus` `#ffd34d` = **11.0–13.2** against surfaces.

### 1. `--line-strong` for interactive boundaries (amends the token contract, 01)

`--line` fails 3:1 everywhere (dark **1.27–1.52**, light **1.28–1.45**), but it is only ever a *decorative* separator (cards, dividers, row rules), which WCAG 1.4.11 exempts. The real gap is form-control / switch / button boundaries, where the `--panel2`-on-`--panel` fill is only ~**1.1:1**, so nothing identifies the control.

Add one token, used **only for interactive component boundaries**:

```
--line-strong: #5c6b80;   /* dark  — panel 3.19, bg 3.49 */
--line-strong: #7a8794;   /* light — panel 3.67, bg 3.45, panel2 3.24 */
```

`--line` stays decorative (cards, dividers, table row rules).

### 2. Badge label text = `--ink` (amends the component contract, 06)

Coloured text on its own 16% tint fails: light **all four** (`ok` 4.09, `warn` 3.96, `bad` 4.14, `accent` 4.13) and dark **`bad`** (4.28). Lowering the tint does not fix it (light `warn` is still 4.40 at 8%). **Badge/pill label text is `--ink`**; the semantic colour is carried by the **tint fill, the border and the dot**. Ink-on-tint = **10.7–12.8** in both modes. (Matches the `.tag` block pills.)

### 3. Light `--focus` darkened (amends light mode, 08)

Light `--focus` `#bf8700` narrowly fails 3:1 (**2.95** vs bg, **2.77** vs panel2). Darken the light value to **`#b07800`** (**3.57 / 3.80 / 3.35**). Dark stays `#ffd34d`.

### 4. Focus-visible treatment

Keep the single global rule (05): `2px solid var(--focus)`, `2px` offset, applied to **every** focusable control — buttons, links, inputs, selects, switches, table rows, Multiview tiles, editor cells. No per-component rings. (`--focus` = `--star`.)

### 5. Filled button text + media surfaces

All filled button variants (**primary / success / danger / warning**) use **`--on-accent`** text — the AA-passing choice in both modes (dark `--on-accent` `#04121f` passes on every fill; light `--on-accent` `#ffffff` passes on every fill). Video / Multiview tile overlays and the playing ring are **best-effort** — AA is not asserted over uncontrolled media; the `#ffc107` ring maps to `--focus`/`--star` (06).

### Net token changes

Three: add `--line-strong` (both modes), set light `--focus`/`--star` to `#b07800`, and the badge-text rule (no new token). Everything else in the token and component contracts passes as-is.

Context: contrast computation over the settled dark (01) and light (08) token sets; component treatments (06) and shell focus rule (05).
