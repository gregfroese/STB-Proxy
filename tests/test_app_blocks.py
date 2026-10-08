import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class BlocksPageTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {
                PORTAL: portalConfig(
                    **{"channel blocks": {"2": "NHL", "3": "NHL", "1": "<b>Bold</b>"}, "dead channels": ["3"]}
                )
            },
            "blocks": {"NHL": "false"},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "tok"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated: 2 channels enabled"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def test_page_lists_blocks_with_counts(self):
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("NHL", body)
        self.assertIn('data-block="NHL">2</span> channels', body)
        self.assertIn('class="block-dead-count">1</span> dead', body)
        self.assertIn("Sync now", body)

    def test_block_names_are_escaped(self):
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("&lt;b&gt;Bold&lt;/b&gt;", body)
        self.assertNotIn("<b>Bold</b>", body)

    def test_empty_state(self):
        self.app.getPortals()[PORTAL]["channel blocks"] = {}
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("No blocks yet", body)

    def test_toggle_on_saves_and_syncs(self):
        response = self.client.post("/blocks/toggle", data={"name": "NHL", "enabled": "true"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.app.getBlocks()["NHL"], "true")
        self.syncPlex.assert_called_once()
        lineup = [e["GuideNumber"] for e in self.client.get("/lineup.json").get_json()]
        self.assertEqual(sorted(lineup), ["101", "102"])

    def test_toggle_off(self):
        self.app.getBlocks()["NHL"] = "true"
        self.client.post("/blocks/toggle", data={"name": "NHL", "enabled": "false"})
        self.assertEqual(self.app.getBlocks()["NHL"], "false")

    def test_toggle_saves_even_when_plex_fails(self):
        self.syncPlex.return_value = ("danger", "Plex not updated: couldn't reach Plex at http://plex.test:32400 (ConnectionError)")
        self.client.post("/blocks/toggle", data={"name": "NHL", "enabled": "true"})
        self.assertEqual(self.app.getBlocks()["NHL"], "true")
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("couldn&#39;t reach Plex", body)

    def test_toggle_unknown_block(self):
        self.client.post("/blocks/toggle", data={"name": "Nope", "enabled": "true"})
        self.assertNotIn("Nope", self.app.getBlocks())
        self.syncPlex.assert_not_called()

    def test_rename_moves_channels_state_hidden_and_saved_filters(self):
        self.app.getBlocks()["NHL"] = "true"
        self.app.config["hidden blocks"] = ["NHL"]
        self.app.getSavedFilters()["editor"] = {"Hockey": {"block": "NHL"}}
        response = self.client.post("/blocks/rename", data={"name": "NHL", "newName": " Hockey "})
        self.assertEqual(response.status_code, 302)
        channelBlocks = self.app.getPortals()[PORTAL]["channel blocks"]
        self.assertEqual((channelBlocks["2"], channelBlocks["3"]), (["Hockey"], ["Hockey"]))
        self.assertEqual(self.app.getBlocks(), {"Hockey": "true"})
        self.assertEqual(self.app.getHiddenBlocks(), ["Hockey"])
        self.assertEqual(self.app.getSavedFilters()["editor"]["Hockey"]["block"], "Hockey")
        self.syncPlex.assert_not_called()  # same lineup

    def test_rename_refuses_clashes_commas_and_unknown_blocks(self):
        for form in ({"name": "NHL", "newName": "<b>Bold</b>"}, {"name": "NHL", "newName": "A, B"},
                     {"name": "NHL", "newName": " "}, {"name": "Nope", "newName": "Other"}):
            self.client.post("/blocks/rename", data=form)
            self.assertEqual(self.app.getPortals()[PORTAL]["channel blocks"]["2"], ["NHL"])
            self.assertNotIn("Other", self.app.getBlocks())

    def test_hide_and_show(self):
        self.client.post("/blocks/hide", data={"name": "NHL", "hidden": "true"})
        self.assertEqual(self.app.getHiddenBlocks(), ["NHL"])
        self.assertIn("Hidden from API", self.client.get("/blocks").get_data(as_text=True))
        self.client.post("/blocks/hide", data={"name": "NHL", "hidden": "false"})
        self.assertEqual(self.app.getHiddenBlocks(), [])
        self.client.post("/blocks/hide", data={"name": "Nope", "hidden": "true"})
        self.assertEqual(self.app.getHiddenBlocks(), [])

    def test_an_emptied_block_is_no_longer_hidden(self):
        self.app.config["hidden blocks"] = ["NHL"]
        self.client.post("/channels/blocks", json={
            "channels": [{"portal": PORTAL, "channelId": "2"}, {"portal": PORTAL, "channelId": "3"}],
            "block": "NHL", "action": "remove"})
        self.assertEqual(self.app.getHiddenBlocks(), [])

    def test_sync_now(self):
        response = self.client.post("/blocks/sync")
        self.assertEqual(response.status_code, 302)
        self.syncPlex.assert_called_once()


if __name__ == "__main__":
    unittest.main()
