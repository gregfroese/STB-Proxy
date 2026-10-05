import json
import unittest

from tests.support import PORTAL, loadApp, portalConfig


def numbers(entries):
    return sorted(e["GuideNumber"] for e in entries)


class ConfigTest(unittest.TestCase):
    def test_new_keys_survive_load(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{"channel blocks": {"2": "NHL"}, "dead channels": ["3"]})},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "secret"},
            "blocks": {"NHL": "true"},
        }
        app = loadApp(self, cfg)
        portal = app.getPortals()[PORTAL]
        self.assertEqual(portal["channel blocks"], {"2": ["NHL"]})  # single names become lists
        self.assertEqual(portal["dead channels"], ["3"])
        self.assertEqual(app.getBlocks(), {"NHL": "true"})
        self.assertEqual(app.getSettings()["plex url"], "http://plex.test:32400")
        self.assertEqual(app.getSettings()["plex token"], "secret")

    def test_blocks_default_to_empty(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.assertEqual(app.getBlocks(), {})

    def test_save_blocks_persists(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        app.saveBlocks({"NHL": "true"})
        with open(app.configFile) as f:
            self.assertEqual(json.load(f)["blocks"], {"NHL": "true"})


class LineupTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {
                PORTAL: portalConfig(
                    **{
                        "enabled channels": ["1", "3"],
                        "channel blocks": {"2": "NHL"},
                        "dead channels": ["3"],
                        "custom epg ids": {"2": "custom.two"},
                    }
                )
            },
            "blocks": {"NHL": "true"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def test_build_lineup_applies_availability_and_epg_ids(self):
        entries, failed = self.app.buildLineup()
        self.assertEqual(failed, [])
        self.assertEqual(numbers(entries), ["101", "102"])
        byNumber = {e["GuideNumber"]: e for e in entries}
        self.assertEqual(byNumber["101"]["epgId"], PORTAL + "1")
        self.assertEqual(byNumber["102"]["epgId"], "custom.two")
        self.assertEqual(byNumber["101"]["URL"], "http://proxy.test:8001/play/p1/1")

    def test_build_lineup_reports_failed_portal(self):
        self.app.stb.getAllChannels.return_value = None
        entries, failed = self.app.buildLineup()
        self.assertEqual(entries, [])
        self.assertEqual(failed, ["Test portal"])

    def test_lineup_json_has_no_epg_id(self):
        data = self.client.get("/lineup.json").get_json()
        self.assertEqual(numbers(data), ["101", "102"])
        self.assertNotIn("epgId", data[0])

    def test_xmltv_uses_availability(self):
        body = self.client.get("/xmltv").get_data(as_text=True)
        self.assertIn('id="p11"', body)
        self.assertIn('id="custom.two"', body)
        self.assertNotIn('id="p13"', body)

    def test_playlist_uses_availability(self):
        body = self.client.get("/playlist").get_data(as_text=True)
        self.assertIn("/play/p1/1", body)
        self.assertIn("/play/p1/2", body)
        self.assertNotIn("/play/p1/3", body)


if __name__ == "__main__":
    unittest.main()
