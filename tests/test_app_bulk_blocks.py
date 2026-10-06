import json
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class BulkBlocksTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{"enabled channels": [], "channel blocks": {"1": ["Movies"], "2": ["NHL"]}})},
            "blocks": {"NHL": "true", "Movies": "false"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def bulk(self, ids, block, action, portal=PORTAL):
        body = {"channels": [{"portal": portal, "channelId": i} for i in ids], "block": block, "action": action}
        return self.client.post("/channels/blocks", data=json.dumps(body), content_type="application/json")

    def blocks(self):
        return self.app.getPortals()[PORTAL]["channel blocks"]

    def test_add_many_keeps_their_other_blocks(self):
        res = self.bulk(["1", "2", "3"], "Sports", "add").get_json()
        self.assertEqual(self.blocks(), {"1": ["Movies", "Sports"], "2": ["NHL", "Sports"], "3": ["Sports"]})
        self.assertEqual([c["blocks"] for c in res["channels"]], [["Movies", "Sports"], ["NHL", "Sports"], ["Sports"]])
        self.assertEqual(res["allBlocks"], ["Movies", "NHL", "Sports"])
        self.syncPlex.assert_not_called()  # Sports is a new block, so off: nothing became available

    def test_adding_to_a_block_that_is_on_syncs_plex(self):
        self.bulk(["1", "3"], "NHL", "add")
        self.syncPlex.assert_called_once()

    def test_remove_many(self):
        self.bulk(["1", "2", "3"], "Sports", "add")
        self.bulk(["1", "2"], "Sports", "remove")
        self.assertEqual(self.blocks(), {"1": ["Movies"], "2": ["NHL"], "3": ["Sports"]})

    def test_removing_the_last_channel_drops_the_blocks_state(self):
        self.bulk(["1"], "Movies", "remove")
        self.assertNotIn("1", self.blocks())
        self.assertNotIn("Movies", self.app.getBlocks())

    def test_replaces_rather_than_mutates_channel_blocks(self):
        before = self.blocks()
        snapshot = dict(before)
        self.bulk(["3"], "Sports", "add")
        self.assertEqual(before, snapshot)

    def test_needs_a_block_and_an_action(self):
        self.assertEqual(self.bulk(["1"], " ", "add").status_code, 400)
        self.assertEqual(self.bulk(["1"], "Sports", "toggle").status_code, 400)

    def test_unknown_portals_are_skipped(self):
        res = self.bulk(["1"], "Sports", "add", portal="nope").get_json()
        self.assertEqual(res["channels"], [])

    def test_editor_has_the_selection_bar(self):
        body = self.client.get("/editor").get_data(as_text=True)
        self.assertIn("function bulkBlocks", body)
        self.assertIn("select-channel", body)


if __name__ == "__main__":
    unittest.main()
