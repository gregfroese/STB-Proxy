import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class ChannelBlocksTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{"enabled channels": [], "channel blocks": {"2": "NHL"}})},
            "blocks": {"NHL": "true", "Sports": "false"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def setBlocks(self, channelId, names, portal=PORTAL):
        return self.client.post(
            "/channel/blocks", data={"portal": portal, "channelId": channelId, "blocks": names}
        )

    def channelBlocks(self):
        return self.app.getPortals()[PORTAL]["channel blocks"]

    def test_add_channel_to_several_blocks(self):
        response = self.setBlocks("3", ["NHL", " Sports "])
        self.assertEqual(
            response.get_json(), {"blocks": ["NHL", "Sports"], "allBlocks": ["NHL", "Sports"], "plex": "Plex updated"}
        )
        self.assertEqual(self.channelBlocks()["3"], ["NHL", "Sports"])

    def test_new_block_starts_off(self):
        self.setBlocks("3", ["Movies"])
        self.assertNotEqual(self.app.getBlocks().get("Movies"), "true")
        self.syncPlex.assert_not_called()

    def test_clearing_blocks_removes_channel_and_prunes_unused_blocks(self):
        response = self.setBlocks("2", [])
        self.assertEqual(response.get_json()["blocks"], [])
        self.assertEqual(response.get_json()["allBlocks"], [])
        self.assertNotIn("2", self.channelBlocks())
        self.assertEqual(self.app.getBlocks(), {})
        self.syncPlex.assert_called_once()  # 2 was only available through NHL

    def test_replaces_rather_than_mutates_channel_blocks(self):
        # Other threads may be iterating the old dict (lineup/xmltv/playlist).
        before = self.channelBlocks()
        snapshot = dict(before)
        self.setBlocks("3", ["NHL"])
        self.assertEqual(before, snapshot)

    def test_syncs_plex_only_when_availability_changes(self):
        self.setBlocks("2", ["NHL", "Sports"])
        self.syncPlex.assert_not_called()
        self.setBlocks("2", ["Sports"])
        self.syncPlex.assert_called_once()
        lineup = [e["GuideNumber"] for e in self.client.get("/lineup.json").get_json()]
        self.assertEqual(lineup, [])

    def test_unknown_portal(self):
        self.assertEqual(self.setBlocks("1", ["NHL"], portal="nope").status_code, 404)

    def test_preview_offers_block_picker_on_both_pages(self):
        self.setBlocks("3", ["It's <new>"])
        for page in ("/editor", "/blocks"):
            body = self.client.get(page).get_data(as_text=True)
            self.assertIn('id="blockChoices"', body)
            self.assertIn("function saveChannelBlocks", body)
            self.assertIn("data-blocks='[\"It\\u0027s \\u003cnew\\u003e\", \"NHL\"]'", body)


if __name__ == "__main__":
    unittest.main()
