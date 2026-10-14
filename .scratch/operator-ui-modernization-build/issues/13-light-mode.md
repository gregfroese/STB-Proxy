# 13: Light mode

**What to build:** A light theme the operator can switch to. Add the light token block (`[data-bs-theme="light"]`, per the spec's values — including `--focus`/`--star` `#b07800`) plus the light-only component overrides (`--hi` hairline, lighter `--scrim`, dimmed `--bg-glow`, the channel-logo mat, `.btn-close`). Add the switching mechanism: `data-bs-theme` on `<html>` with `color-scheme` set alongside it, defaulting to `prefers-color-scheme`, a manual choice persisted in `localStorage['theme']` (no `'system'` value), and a tiny inline `<head>` script that applies the theme before first paint. Add one sun/moon toggle button in the shell's top bar.

**Blocked by:** 05.

**Status:** resolved

- [x] First load follows the OS preference, falling back to dark.
- [x] The sun/moon toggle switches theme and persists across reloads; clearing storage returns to the OS preference.
- [x] No flash of the wrong theme on load; native scrollbars/controls follow `color-scheme`.
- [x] The light token set meets WCAG AA; the computed-contrast test covers both modes.
