import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig

SETTINGS_FORM = {
    "stream method": "ffmpeg",
    "ffmpeg command": "ffmpeg",
    "ffmpeg timeout": "5",
    "username": "admin",
    "password": "12345",
    "hdhr name": "STB-Proxy",
    "hdhr id": "abc",
    "hdhr tuners": "1",
}


class SettingsTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig()},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "tok-s3cret-123"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def post(self, **fields):
        form = dict(SETTINGS_FORM, **fields)
        return self.client.post("/settings/save", data=form)

    def test_blank_token_field_keeps_saved_token(self):
        self.post(**{"plex url": "http://plex.test:32400", "plex token": ""})
        self.assertEqual(self.app.getSettings()["plex token"], "tok-s3cret-123")

    def test_new_token_replaces_saved_one(self):
        self.post(**{"plex url": "http://plex.test:32400", "plex token": "new"})
        self.assertEqual(self.app.getSettings()["plex token"], "new")

    def test_clear_token(self):
        self.post(**{"plex url": "http://plex.test:32400", "plex token": "", "clear plex token": "true"})
        self.assertEqual(self.app.getSettings()["plex token"], "")

    def test_plex_url_trimmed(self):
        self.post(**{"plex url": " http://plex.test:32400/ ", "plex token": ""})
        self.assertEqual(self.app.getSettings()["plex url"], "http://plex.test:32400")

    def test_settings_page_never_shows_token(self):
        body = self.client.get("/settings").get_data(as_text=True)
        self.assertIn("http://plex.test:32400", body)
        self.assertNotIn("tok-s3cret-123", body)


class SyncPlexTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig()},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "tok"},
        }
        self.app = loadApp(self, cfg)
        patcher = mock.patch.object(self.app.plex, "sync", return_value="Plex updated: 1 channels enabled")
        self.sync = patcher.start()
        self.addCleanup(patcher.stop)

    def test_success(self):
        self.assertEqual(self.app.syncPlex(), ("success", "Plex updated: 1 channels enabled"))
        args = self.sync.call_args.args
        self.assertEqual(args[:3], ("http://plex.test:32400", "tok", "http://proxy.test:8001"))
        self.assertEqual([e["GuideNumber"] for e in args[3]], ["101"])
        self.assertTrue(self.app.lastPlexSync["ok"])
        self.assertIsNotNone(self.app.lastPlexSync["time"])

    def test_plex_error_reported(self):
        self.sync.side_effect = self.app.plex.PlexSyncError("Plex rejected the token (HTTP 401)")
        category, message = self.app.syncPlex()
        self.assertEqual(category, "danger")
        self.assertEqual(message, "Plex not updated: Plex rejected the token (HTTP 401)")
        self.assertFalse(self.app.lastPlexSync["ok"])

    def test_sync_aborts_when_a_portal_fails(self):
        self.app.stb.getAllChannels.return_value = None
        category, message = self.app.syncPlex()
        self.assertEqual(category, "danger")
        self.assertIn("couldn't load channels from Test portal", message)
        self.sync.assert_not_called()

    def test_not_configured(self):
        self.app.getSettings()["plex token"] = ""
        category, message = self.app.syncPlex()
        self.assertEqual(category, "info")
        self.assertIn("Plex sync is off", message)
        self.sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
