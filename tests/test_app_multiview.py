import unittest

from tests.support import PORTAL, loadApp, portalConfig


class MultiviewPageTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{
                "enabled channels": ["1"],
                "channel blocks": {"2": ["NHL"], "3": ["Movies"]},
            })},
            "blocks": {"NHL": "true", "Movies": "false"},
            "settings": {"hdhr tuners": "2"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def test_page_renders_with_layouts_and_the_tuner_count(self):
        body = self.client.get("/multiview").get_data(as_text=True)
        self.assertIn('id="multiviewGrid"', body)
        for layout in ("1", "2", "4", "9", "big"):
            self.assertIn('data-layout="{}"'.format(layout), body)
        self.assertIn("2 tuners", body)
        self.assertIn("multiview.js", body)

    def test_only_blocks_that_are_on_go_to_the_picker(self):
        body = self.client.get("/multiview").get_data(as_text=True)
        self.assertIn("data-blocks='[\"NHL\"]'", body)

    def test_menu_links_to_it(self):
        self.assertIn('href="/multiview"', self.client.get("/guide").get_data(as_text=True))

    def test_editor_data_says_which_channels_are_in_the_lineup(self):
        rows = {r["channelId"]: r for r in self.client.get("/editor_data").get_json()["data"]}
        self.assertEqual({c: rows[c]["available"] for c in rows}, {"1": True, "2": True, "3": False})


if __name__ == "__main__":
    unittest.main()
