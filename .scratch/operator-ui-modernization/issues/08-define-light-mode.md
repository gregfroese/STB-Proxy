# Define light mode

Type: wayfinder:prototype
Status: resolved
Blocked by: 01, 06

## Question

What is the light-mode token set and the mechanism that switches to it?

Decide:

- The light values for every colour token defined in ticket 01 (the Web Viewer is dark-only, so this is net-new design work; it must still read as the same product).
- The toggle mechanism: Bootstrap 5.3 `data-bs-theme`, `prefers-color-scheme` as the default, and where the manual override persists (localStorage?).
- Which components need light-specific adjustment (borders/glass overlays that assume dark, table striping, overlays).

**Prototype** the light token set (and, if useful, a side-by-side of one page), for the human to react to. HITL.

Consult `grilling` + `domain-modeling`. Output: the theming section of the spec.

## Answer

**Light mode = Variant A "Daylight"** — the flat inversion of the dark ladder — plus a `data-bs-theme`-driven switch. Prototype (all four directions retained as the primary source): [`prototype/light-mode.html`](../prototype/light-mode.html). A wins; B (Slate) and C (Warm paper) kept only as the record of what was weighed and rejected.

### Light colour tokens (the light half of `:root`)

```css
[data-bs-theme="light"] {
  --bg:      #f6f8fa;   /* page (cool gray) */
  --bg-glow: 214,222,232;
  --panel:   #ffffff;   /* surface: cards, bars */
  --panel2:  #eef1f4;   /* raised: inputs, buttons, chips — darker than --panel */
  --line:    #d0d7de;
  --ink:     #1f2328;
  --dim:     #59636e;
  --accent:  #0969da;   /* darkened from #3ba6ff: the dark accent fails AA as text on white */
  --on-accent:#ffffff;
  --focus:   #bf8700;
  --star:    #bf8700;
  --ok:      #1a7f37;
  --warn:    #9a6700;
  --bad:     #cf222e;
  --hi:      #00000014; /* glass hairline: dark now, not white */
  --shadow:  0 1px 2px rgba(31,35,40,.06);
  --shadow-lg:0 24px 60px rgba(31,35,40,.22);
  --scrim:   rgba(31,35,40,.35);
  --logo-mat:#ffffff;   /* channel-logo mat */
  color-scheme: light;
}
```

Key inversion detail: the dark ladder darkens with depth (`--bg` < `--panel` < `--panel2`); light inverts it so the page is the tinted surface and cards are white, but `--panel2` (raised inputs/buttons) is *darker* than `--panel` — there is nothing lighter than white. Semantic tints stay `color-mix(...)` off the base tokens, so no light-specific tint hexes. The dark token set is unchanged. `--focus`/`--star` are the only tokens whose light value is a different hue family from dark's `#ffd34d` (amber darkened to `#bf8700` so the ring reads on light).

### Mechanism

- **`data-bs-theme` on `<html>`** (`"dark"` default / `"light"`), Bootstrap 5.3's own mechanism, so BS components follow for free.
- **`color-scheme`** is set alongside it (`light`/`dark`) so native scrollbars, form controls and autofill render correctly.
- **Default = `prefers-color-scheme`**; a manual choice overrides and persists in `localStorage['theme']` (`'light'`/`'dark'`). There is no `'system'` value — clearing the key returns to following the OS. Dark is the fallback when the OS expresses no preference.
- A **tiny inline `<head>` script** applies the stored/`prefers` theme before first paint, avoiding a flash of the wrong theme.
- **Toggle**: one sun/moon icon button in the shared shell's top bar, right cluster next to the version chip (`aria-label`, tooltip, 34×34 matching the icon-button contract). Two-state; present on every page via the shell.
- Applied as one `[data-bs-theme="light"]` block in `static/theme.css` layered with the dark `:root`; no second stylesheet.

### Component-level light adjustments

The handful of things that assume dark get a light override:

- `--hi` glass hairline → `#00000014` (a dark hairline).
- Modal `--scrim` → `rgba(31,35,40,.35)` (lighter than dark's `#000a`).
- Radial `--bg-glow` dimmed (light tint).
- `.channel-logo` mat → `--panel` white (dark mat was `--ink`).
- `.btn-close-white` → `.btn-close` in light.
- Table striping and row-hover are already `color-mix` off tokens — no change.
- The `#000`/`#111` video/fullscreen literals stay literal in both modes.
- Bootstrap's own components follow `data-bs-theme` automatically.

### Deferred

The precise contrast-ratio audit against WCAG 2.1 AA (beyond the shell baseline) is now specifiable, and graduates to **Audit focus/contrast against WCAG 2.1 AA**.

Context: `.scratch/operator-ui-modernization/prototype/light-mode.html`; served at `http://100.91.119.113:8099/light-mode.html`.
