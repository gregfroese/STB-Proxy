import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class DeadChannelTest(unittest.TestCase):
    def setUp(self):
        cfg = {"portals": {PORTAL: portalConfig(**{"enabled channels": ["1", "2"]})}}
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated: 1 channels enabled"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def mark(self, channelId, dead, portal=PORTAL):
        return self.client.post(
            "/channel/dead", data={"portal": portal, "channelId": channelId, "dead": "true" if dead else "false"}
        )

    def lineupNumbers(self):
        return sorted(e["GuideNumber"] for e in self.client.get("/lineup.json").get_json())

    def test_mark_available_channel_dead(self):
        response = self.mark("2", True)
        self.assertEqual(response.get_json(), {"dead": True, "plex": "Plex updated: 1 channels enabled"})
        self.assertEqual(self.app.getPortals()[PORTAL]["dead channels"], ["2"])
        self.assertEqual(self.lineupNumbers(), ["101"])
        self.syncPlex.assert_called_once()

    def test_unmark_restores(self):
        self.mark("2", True)
        self.mark("2", False)
        self.assertEqual(self.app.getPortals()[PORTAL]["dead channels"], [])
        self.assertEqual(self.lineupNumbers(), ["101", "102"])
        self.assertEqual(self.syncPlex.call_count, 2)
        self.assertEqual(self.app.getPortals()[PORTAL]["enabled channels"], ["1", "2"])

    def test_marking_unavailable_channel_does_not_sync(self):
        response = self.mark("3", True)
        self.assertEqual(response.get_json(), {"dead": True, "plex": ""})
        self.syncPlex.assert_not_called()

    def test_marking_twice_does_not_duplicate(self):
        self.mark("2", True)
        self.mark("2", True)
        self.assertEqual(self.app.getPortals()[PORTAL]["dead channels"], ["2"])
        self.syncPlex.assert_called_once()

    def test_unknown_portal(self):
        response = self.mark("1", True, portal="nope")
        self.assertEqual(response.status_code, 404)

    def test_editor_page_has_dead_controls(self):
        body = self.client.get("/editor").get_data(as_text=True)
        self.assertIn('id="deadButton"', body)
        self.assertIn("function toggleDead", body)
        self.assertIn("dead-filter", body)


if __name__ == "__main__":
    unittest.main()
