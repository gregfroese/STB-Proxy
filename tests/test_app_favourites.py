import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class FavouriteChannelTest(unittest.TestCase):
    def setUp(self):
        cfg = {"portals": {PORTAL: portalConfig(**{"channel blocks": {"2": "NHL", "3": "NHL"}})}}
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def mark(self, channelId, favourite, portal=PORTAL):
        return self.client.post(
            "/channel/favourite",
            data={"portal": portal, "channelId": channelId, "favourite": "true" if favourite else "false"},
        )

    def favourites(self):
        return self.app.getPortals()[PORTAL]["favourite channels"]

    def test_mark_favourite(self):
        response = self.mark("2", True)
        self.assertEqual(response.get_json(), {"favourite": True})
        self.assertEqual(self.favourites(), ["2"])

    def test_unmark_favourite(self):
        self.mark("2", True)
        response = self.mark("2", False)
        self.assertEqual(response.get_json(), {"favourite": False})
        self.assertEqual(self.favourites(), [])

    def test_marking_twice_does_not_duplicate(self):
        self.mark("2", True)
        self.mark("2", True)
        self.assertEqual(self.favourites(), ["2"])

    def test_favourites_do_not_change_lineup_or_sync_plex(self):
        self.mark("3", True)
        lineup = [e["GuideNumber"] for e in self.client.get("/lineup.json").get_json()]
        self.assertEqual(lineup, ["101"])
        self.syncPlex.assert_not_called()

    def test_unknown_portal(self):
        response = self.mark("1", True, portal="nope")
        self.assertEqual(response.status_code, 404)

    def test_favourites_survive_reload(self):
        self.mark("2", True)
        self.app.config = self.app.loadConfig()
        self.assertEqual(self.favourites(), ["2"])

    def test_editor_data_reports_favourites_and_blocks(self):
        self.mark("2", True)
        rows = {r["channelId"]: r for r in self.client.get("/editor_data").get_json()["data"]}
        self.assertTrue(rows["2"]["favourite"])
        self.assertFalse(rows["1"]["favourite"])
        self.assertEqual(rows["3"]["block"], "NHL")

    def test_blocks_page_has_channel_viewer_and_favourites(self):
        self.mark("2", True)
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn('class="block-channels" data-block="NHL"', body)
        self.assertIn('id="favouritesTab"', body)
        self.assertIn('<span class="badge bg-secondary" id="favouriteCount">1</span>', body)
        self.assertIn('id="videoModal"', body)
        self.assertIn('id="favouriteButton"', body)

    def test_editor_page_has_favourite_controls(self):
        body = self.client.get("/editor").get_data(as_text=True)
        self.assertIn('id="favouriteButton"', body)
        self.assertIn("favouritesOnly", body)
        self.assertIn('id="deadButton"', body)


if __name__ == "__main__":
    unittest.main()
