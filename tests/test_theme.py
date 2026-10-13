import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_TOKENS = [
    "--bg",
    "--panel",
    "--panel2",
    "--line",
    "--line-strong",
    "--ink",
    "--dim",
    "--accent",
    "--focus",
    "--ok",
    "--warn",
    "--bad",
]


def read(name):
    with open(os.path.join(ROOT, name)) as f:
        return f.read()


class TokenStylesheetTest(unittest.TestCase):
    def setUp(self):
        self.css = read(os.path.join("static", "theme.css"))

    def test_stylesheet_exists_and_is_referenced_by_the_shell(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, "static", "theme.css")))
        self.assertIn("theme.css", read(os.path.join("templates", "base.html")))

    def test_defines_the_dark_token_set(self):
        for token in REQUIRED_TOKENS:
            self.assertRegex(self.css, r"%s\s*:" % re.escape(token),
                             "theme.css must define %s" % token)

    def test_semantic_tints_derive_with_color_mix(self):
        self.assertIn("color-mix(", self.css)


class SharedShellTest(unittest.TestCase):
    def setUp(self):
        self.shell = read(os.path.join("templates", "base.html"))
        self.css = read(os.path.join("static", "theme.css"))

    def test_skip_link_lands_on_main(self):
        self.assertIn('href="#main"', self.shell)
        self.assertIn('id="main"', self.shell)

    def test_has_one_global_focus_ring(self):
        self.assertRegex(self.css, r":focus-visible\s*\{[^}]*outline:\s*2px solid var\(--focus\)")

    def test_active_nav_item_is_marked_from_the_request_path(self):
        self.assertIn('aria-current="page"', self.shell)
        self.assertIn("request.path", self.shell)

    def test_flash_messages_render_as_live_toasts(self):
        self.assertIn('role="status"', self.shell)
        self.assertIn('aria-live="polite"', self.shell)
        self.assertIn('class="toast', self.shell)

    def test_nav_is_grouped_with_feeds_and_changelog_chip(self):
        for group in ("Monitor", "Programme", "Configuration", "Feeds"):
            self.assertIn(group, self.shell)
        self.assertIn("verchip", self.shell)
        self.assertIn("/changelog", self.shell)

    def test_container_variants_are_defined(self):
        self.assertRegex(self.css, r"\.page\s*\{")
        self.assertRegex(self.css, r"\.page--full\s*\{")


class PageContainerTest(unittest.TestCase):
    FULL_BLEED = ("editor.html", "multiview.html", "dashboard.html", "streams.html")
    NORMAL = ("guide.html", "recordings.html", "portals.html", "settings.html",
              "blocks.html", "accounts.html", "changelog.html")

    def test_full_bleed_pages_use_the_full_bleed_container(self):
        for name in self.FULL_BLEED:
            html = read(os.path.join("templates", name))
            self.assertRegex(html, r'class="page--full', name)

    def test_normal_pages_use_the_centered_container(self):
        for name in self.NORMAL:
            html = read(os.path.join("templates", name))
            self.assertRegex(html, r'class="page[\s"]', name)

    def test_no_page_keeps_the_old_outer_padding(self):
        for name in self.FULL_BLEED + self.NORMAL:
            html = read(os.path.join("templates", name))
            self.assertNotIn("p-lg-5", html, name)
            self.assertNotIn("px-lg-5", html, name)


if __name__ == "__main__":
    unittest.main()
