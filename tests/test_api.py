import json
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class ApiTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{
                "enabled channels": ["1"],
                "channel blocks": {"2": ["NHL"], "3": ["Late Night/Movies"]},
                "dead channels": ["3"],
            })},
            "blocks": {"NHL": "false"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        self.token = self.app.getSettings()["api token"]
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, method, path, body=None, token=True):
        headers = {"Authorization": "Bearer " + self.token} if token else {}
        return self.client.open(path, method=method, headers=headers,
                                data=json.dumps(body) if body is not None else None, content_type="application/json")

    def test_a_token_is_made_and_required(self):
        self.assertTrue(len(self.token) > 20)
        self.assertEqual(self.call("GET", "/api/blocks", token=False).status_code, 401)
        self.assertEqual(self.client.get("/api/blocks", headers={"Authorization": "Bearer nope"}).status_code, 401)
        self.assertEqual(self.client.get("/api/blocks", headers={"X-API-Key": self.token}).status_code, 200)

    def test_saving_settings_keeps_the_token_and_new_token_replaces_it(self):
        form = {k: v for k, v in self.app.getSettings().items() if k != "api token"}
        self.client.post("/settings/save", data=form)
        self.assertEqual(self.app.getSettings()["api token"], self.token)
        self.client.post("/settings/api-token")
        self.assertNotEqual(self.app.getSettings()["api token"], self.token)
        self.assertEqual(self.call("GET", "/api/blocks").status_code, 401)

    def test_list_and_get_blocks(self):
        blocks = {b["name"]: b for b in self.call("GET", "/api/blocks").get_json()}
        self.assertEqual(blocks["NHL"], {"name": "NHL", "enabled": False, "channels": 1, "dead": 0})
        self.assertEqual(blocks["Late Night/Movies"]["dead"], 1)
        self.assertEqual(self.call("GET", "/api/blocks/nhl").get_json()["name"], "NHL")  # any case
        self.assertEqual(self.call("GET", "/api/blocks/Late%20Night/Movies").get_json()["channels"], 1)
        self.assertEqual(self.call("GET", "/api/blocks/Nope").status_code, 404)

    def test_switch_with_json_like_a_home_assistant_rest_switch(self):
        res = self.call("POST", "/api/blocks/NHL", {"enabled": True}).get_json()
        self.assertEqual((res["enabled"], res["changed"]), (True, True))
        self.assertEqual(self.app.getBlocks()["NHL"], "true")
        self.syncPlex.assert_called_once()
        lineup = sorted(e["GuideNumber"] for e in self.client.get("/lineup.json").get_json())
        self.assertEqual(lineup, ["101", "102"])
        res = self.call("POST", "/api/blocks/NHL", {"enabled": True}).get_json()
        self.assertFalse(res["changed"])
        self.syncPlex.assert_called_once()  # nothing changed, no sync
        self.assertEqual(self.call("POST", "/api/blocks/NHL", {"enabled": "yes"}).status_code, 400)

    def test_on_off_toggle(self):
        self.assertTrue(self.call("POST", "/api/blocks/NHL/on").get_json()["enabled"])
        self.assertFalse(self.call("POST", "/api/blocks/NHL/toggle").get_json()["enabled"])
        self.assertTrue(self.call("POST", "/api/blocks/NHL/toggle").get_json()["enabled"])
        self.assertFalse(self.call("POST", "/api/blocks/Late%20Night/Movies/off").get_json()["changed"])
        self.assertEqual(self.call("POST", "/api/blocks/NHL/maybe").status_code, 404)

    def test_status(self):
        status = self.call("GET", "/api/status").get_json()
        self.assertEqual((status["lineup"], status["streams"], status["otherLogins"], status["boxOn"]), (1, 0, 0, False))
        self.assertEqual(len(status["blocks"]), 2)
        self.assertIn("plex", status)

    def test_plex_sync_now(self):
        self.call("POST", "/api/plex/sync")
        self.syncPlex.assert_called_once()


class PlexRetryTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()},
                                  "settings": {"plex url": "http://plex.test:32400", "plex token": "tok"}})
        self.app.PLEX_RETRY_DELAYS = [60, 120]
        timer = mock.patch.object(self.app.threading, "Timer")
        self.Timer = timer.start()
        self.addCleanup(timer.stop)
        sync = mock.patch.object(self.app.plex, "sync", side_effect=self.app.plex.PlexSyncError("couldn't reach Plex"))
        self.plexSync = sync.start()
        self.addCleanup(sync.stop)

    def test_failure_is_retried_later_then_given_up(self):
        self.app.syncPlex()
        self.assertEqual(self.Timer.call_args.args[0], 60)
        self.assertIsNotNone(self.app.lastPlexSync["retryAt"])
        self.app.syncPlex(retry=True)
        self.assertEqual(self.Timer.call_args.args[0], 120)
        self.app.syncPlex(retry=True)  # out of retries
        self.assertEqual(self.Timer.call_count, 2)
        self.assertIsNone(self.app.lastPlexSync["retryAt"])

    def test_a_new_change_starts_the_retries_again(self):
        self.app.syncPlex()
        self.app.syncPlex(retry=True)
        self.app.syncPlex()  # a new change, not a retry
        self.assertEqual(self.Timer.call_args.args[0], 60)

    def test_success_stops_retrying(self):
        self.app.syncPlex()
        self.plexSync.side_effect = None
        self.plexSync.return_value = "Plex updated: 1 channels enabled"
        self.app.syncPlex(retry=True)
        self.Timer.return_value.cancel.assert_called()
        self.assertIsNone(self.app.lastPlexSync["retryAt"])
        self.assertTrue(self.app.lastPlexSync["ok"])


if __name__ == "__main__":
    unittest.main()
