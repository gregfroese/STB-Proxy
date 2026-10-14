# 03: Swap Font Awesome 4 → Bootstrap Icons; drop deprecated classes

**What to build:** Every icon in the Operator UI comes from Bootstrap Icons. Replace every Font Awesome 4 `<i class="fa…">` with its Bootstrap Icons equivalent per `fa-to-bi-icon-map.md` (solid → `-fill`, `-o` → outline). In the same pass, drop the Bootstrap-4/5.0 relics: remove `navbar-light`; replace `text-muted` with `text-body-secondary`; replace the eight `btn-block` no-ops with real full-width (`.w-100` for a single button, `.d-grid` for a stack).

**Blocked by:** 01 (vendored Bootstrap Icons).

**Status:** resolved

- [x] No `fa-*` classes remain anywhere in `templates/` or `static/`; icons render as `bi-*`.
- [x] No `navbar-light` or `btn-block` remains; `text-muted` is gone.
- [x] Full-width buttons still span their container.
- [x] The source-string template tests are updated and green.
