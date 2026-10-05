import json
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig

EMPTY_EDITS = {
    "enabledEdits": "[]",
    "numberEdits": "[]",
    "nameEdits": "[]",
    "genreEdits": "[]",
    "epgEdits": "[]",
    "fallbackEdits": "[]",
}


class EditorTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{"channel blocks": {"2": "NHL"}, "dead channels": ["3"]})},
            "blocks": {"NHL": "true", "Old": "false"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def save(self, blockEdits=None, enabledEdits=None):
        form = dict(EMPTY_EDITS)
        if blockEdits is not None:
            form["blockEdits"] = json.dumps(blockEdits)
        if enabledEdits is not None:
            form["enabledEdits"] = json.dumps(enabledEdits)
        return self.client.post("/editor/save", data=form)

    def blockEdit(self, channelId, block):
        return {"portal": PORTAL, "channel id": channelId, "block": block}

    def test_editor_page_renders_block_field(self):
        body = self.client.get("/editor").get_data(as_text=True)
        self.assertIn('id="blockEdits"', body)
        self.assertIn("function editBlock", body)

    def test_block_edits_replace_rather_than_mutate_channel_blocks(self):
        # Other threads may be iterating the old dict (lineup/xmltv/playlist).
        before = self.app.getPortals()[PORTAL]["channel blocks"]
        snapshot = dict(before)
        self.save([self.blockEdit("1", "NHL"), self.blockEdit("2", "")])
        self.assertEqual(before, snapshot)
        self.assertEqual(self.app.getPortals()[PORTAL]["channel blocks"], {"1": ["NHL"]})

    def test_editor_data_has_block_and_dead(self):
        rows = {r["channelId"]: r for r in self.client.get("/editor_data").get_json()["data"]}
        self.assertEqual(rows["2"]["blocks"], ["NHL"])
        self.assertEqual(rows["1"]["blocks"], [])
        self.assertTrue(rows["3"]["dead"])
        self.assertFalse(rows["1"]["dead"])

    def test_block_names_are_trimmed(self):
        self.save([self.blockEdit("1", "  NHL ")])
        self.assertEqual(self.app.getPortals()[PORTAL]["channel blocks"]["1"], ["NHL"])

    def test_comma_separated_blocks(self):
        self.save([self.blockEdit("1", "NHL, Sports,,NHL ")])
        self.assertEqual(self.app.getPortals()[PORTAL]["channel blocks"]["1"], ["NHL", "Sports"])

    def test_clearing_block_removes_membership(self):
        self.save([self.blockEdit("2", "")])
        self.assertNotIn("2", self.app.getPortals()[PORTAL]["channel blocks"])

    def test_clearing_block_never_set_is_harmless(self):
        response = self.save([self.blockEdit("1", "")])
        self.assertEqual(response.status_code, 302)

    def test_save_without_block_edits_field_still_works(self):
        response = self.save()
        self.assertEqual(response.status_code, 302)

    def test_unused_block_states_pruned(self):
        self.save([self.blockEdit("2", "")])
        self.assertEqual(self.app.getBlocks(), {})

    def test_adding_channel_to_block_that_is_on_syncs_plex(self):
        self.save([self.blockEdit("1", "NHL"), self.blockEdit("3", "NHL")])
        self.syncPlex.assert_not_called()  # 1 already enabled, 3 is dead: nothing changed
        self.save([self.blockEdit("1", "")])
        self.syncPlex.assert_not_called()  # 1 is still enabled on its own
        self.app.getPortals()[PORTAL]["enabled channels"] = []
        self.save([self.blockEdit("1", "NHL")])
        self.syncPlex.assert_called_once()

    def test_enabling_channel_syncs_plex(self):
        self.save(enabledEdits=[{"portal": PORTAL, "channel id": "3", "enabled": False}])
        self.syncPlex.assert_not_called()
        self.save(enabledEdits=[{"portal": PORTAL, "channel id": "1", "enabled": False}])
        self.syncPlex.assert_called_once()


if __name__ == "__main__":
    unittest.main()
