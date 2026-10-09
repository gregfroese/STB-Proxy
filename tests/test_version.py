import os
import re
import unittest

import changelog
import version
from tests.support import PORTAL, loadApp, portalConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VersionTest(unittest.TestCase):
    def test_the_version_is_semver_and_the_changelog_starts_with_it(self):
        self.assertRegex(version.VERSION, r"^\d+\.\d+\.\d+$")
        with open(os.path.join(ROOT, "CHANGELOG.md")) as f:
            releases = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", f.read(), re.M)
        self.assertEqual(releases[0], version.VERSION)  # every version has its entry, newest first

    def test_the_docker_image_has_the_changelog(self):
        with open(os.path.join(ROOT, "Dockerfile")) as f:
            self.assertIn("COPY /CHANGELOG.md /app/CHANGELOG.md\n", f.read())


class ChangelogMarkdownTest(unittest.TestCase):
    def test_headings_lists_paragraphs_and_inline_marks(self):
        html = changelog.render("# Changelog\n\nIntro with `code`.\n\n## [1.0.0] - 2026-10-09\n\n### Added\n\n"
                                "- **Bold** and [a link](https://example.com/x?a=1&b=2)\n- Second\n\nAfter.\n")
        self.assertIn("<h3>Changelog</h3>", html)
        self.assertIn("<p>Intro with <code>code</code>.</p>", html)
        self.assertIn("<h4>[1.0.0] - 2026-10-09</h4>", html)
        self.assertIn("<h5>Added</h5>", html)
        self.assertIn('<ul><li><strong>Bold</strong> and <a href="https://example.com/x?a=1&amp;b=2" target="_blank" rel="noopener">a link</a></li><li>Second</li></ul>', html)
        self.assertIn("<p>After.</p>", html)

    def test_html_in_the_changelog_is_shown_not_run(self):
        html = changelog.render("- <script>alert(1)</script> [x](javascript:alert(1))\n")
        self.assertNotIn("<script>", html)
        self.assertNotIn('href="javascript', html)


class VersionShownTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.client = self.app.app.test_client()

    def test_menu_settings_api_and_changelog_page(self):
        tag = "v" + version.VERSION
        self.assertIn('href="/changelog"', self.client.get("/guide").get_data(as_text=True))
        self.assertIn(tag, self.client.get("/guide").get_data(as_text=True))
        self.assertIn(version.VERSION, self.client.get("/settings").get_data(as_text=True))
        status = self.client.get("/api/status", headers={"X-API-Key": self.app.getSettings()["api token"]}).get_json()
        self.assertEqual(status["version"], version.VERSION)
        page = self.client.get("/changelog").get_data(as_text=True)
        self.assertIn("<h4>[{}] - ".format(version.VERSION), page)


if __name__ == "__main__":
    unittest.main()
