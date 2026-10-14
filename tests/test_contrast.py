"""Computed WCAG 2.1 AA contrast for the theme tokens.

This is a presentation-only change, so the test locks down the accessibility
contract by reading the token values straight out of static/theme.css and
computing the contrast ratios. Both the dark and the light token blocks are
required (the light block arrived with ticket 13); every pairing below is
asserted in both modes.
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tokens the contrast pairings below rely on.
REQUIRED = [
    "--bg", "--panel", "--panel2", "--line", "--line-strong",
    "--ink", "--dim", "--accent", "--on-accent", "--focus",
    "--ok", "--warn", "--bad",
]

SEMANTIC = ["--ok", "--warn", "--bad", "--accent"]

AA_TEXT = 4.5
AA_NON_TEXT = 3.0
TINT = 0.16


def read(name):
    with open(os.path.join(ROOT, name)) as f:
        return f.read()


def parse_block(css, selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css, re.S)
    if not match:
        return None
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(1)))


def hex_rgb(value):
    value = value.strip()
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
    if match:
        raw = match.group(1)
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
    match = re.fullmatch(r"#([0-9a-fA-F]{3})", value)
    if match:
        raw = match.group(1)
        return tuple(int(c * 2, 16) for c in raw)
    raise AssertionError("not a hex colour: %r" % value)


def _channel(component):
    c = component / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix_over(overlay, base, alpha=TINT):
    """color-mix(in srgb, overlay alpha%, transparent) composited on base."""
    return tuple(round(base[i] * (1 - alpha) + overlay[i] * alpha) for i in range(3))


class TokenContrastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = read(os.path.join("static", "theme.css"))
        cls.modes = {
            "dark": parse_block(cls.css, '[data-bs-theme="dark"]'),
            "light": parse_block(cls.css, '[data-bs-theme="light"]'),
        }

    def tokens(self, mode):
        block = self.modes[mode]
        self.assertIsNotNone(block, "theme.css must define the %s token block" % mode)
        for token in REQUIRED:
            self.assertIn(token, block, "%s block must define %s" % (mode, token))
        return {k: v for k, v in block.items() if v.strip().startswith("#")}

    def test_text_meets_aa_on_every_surface(self):
        for mode in self.modes:
            t = self.tokens(mode)
            ink = hex_rgb(t["--ink"])
            for surface in ("--bg", "--panel", "--panel2"):
                ratio = contrast(ink, hex_rgb(t[surface]))
                self.assertGreaterEqual(
                    ratio, AA_TEXT,
                    "%s: --ink on %s is %.2f:1 (need %.1f)" % (mode, surface, ratio, AA_TEXT),
                )

    def test_dim_text_meets_aa_on_every_surface(self):
        for mode in self.modes:
            t = self.tokens(mode)
            dim = hex_rgb(t["--dim"])
            for surface in ("--bg", "--panel", "--panel2"):
                ratio = contrast(dim, hex_rgb(t[surface]))
                self.assertGreaterEqual(
                    ratio, AA_TEXT,
                    "%s: --dim on %s is %.2f:1 (need %.1f)" % (mode, surface, ratio, AA_TEXT),
                )

    def test_on_accent_text_meets_aa(self):
        for mode in self.modes:
            t = self.tokens(mode)
            ratio = contrast(hex_rgb(t["--on-accent"]), hex_rgb(t["--accent"]))
            self.assertGreaterEqual(
                ratio, AA_TEXT,
                "%s: --on-accent on --accent is %.2f:1 (need %.1f)" % (mode, ratio, AA_TEXT),
            )

    def test_focus_ring_meets_non_text_contrast(self):
        for mode in self.modes:
            t = self.tokens(mode)
            focus = hex_rgb(t["--focus"])
            for surface in ("--bg", "--panel", "--panel2"):
                ratio = contrast(focus, hex_rgb(t[surface]))
                self.assertGreaterEqual(
                    ratio, AA_NON_TEXT,
                    "%s: --focus on %s is %.2f:1 (need %.1f)" % (mode, surface, ratio, AA_NON_TEXT),
                )

    def test_line_strong_meets_non_text_contrast_on_panel_and_bg(self):
        for mode in self.modes:
            t = self.tokens(mode)
            line = hex_rgb(t["--line-strong"])
            for surface in ("--panel", "--bg"):
                ratio = contrast(line, hex_rgb(t[surface]))
                self.assertGreaterEqual(
                    ratio, AA_NON_TEXT,
                    "%s: --line-strong on %s is %.2f:1 (need %.1f)" % (mode, surface, ratio, AA_NON_TEXT),
                )

    def test_badge_label_meets_aa_on_the_semantic_tints(self):
        for mode in self.modes:
            t = self.tokens(mode)
            ink = hex_rgb(t["--ink"])
            panel = hex_rgb(t["--panel"])
            for token in SEMANTIC:
                tint = mix_over(hex_rgb(t[token]), panel)
                ratio = contrast(ink, tint)
                self.assertGreaterEqual(
                    ratio, AA_TEXT,
                    "%s: --ink on the %s tint over --panel is %.2f:1 (need %.1f)"
                    % (mode, token, ratio, AA_TEXT),
                )


if __name__ == "__main__":
    unittest.main()
