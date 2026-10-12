import base64
import json
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


def basic(username, password):
    token = base64.b64encode("{}:{}".format(username, password).encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + token}


def feedConfig(**overrides):
    config = {
        "portals": {
            PORTAL: portalConfig(
                **{
                    "enabled channels": ["1"],
                    "channel blocks": {"2": "Kids", "3": "Sports"},
                    "dead channels": [],
                }
            )
        },
        "blocks": {"Kids": "true", "Sports": "true"},
        "default blocks": ["Kids"],
    }
    config.update(overrides)
    return config


class DefaultBlocksConfigTest(unittest.TestCase):
    def test_defaults_to_empty_when_absent(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.assertEqual(app.getDefaultBlocks(), [])
        with open(app.configFile) as f:
            self.assertEqual(json.load(f)["default blocks"], [])

    def test_saves_and_round_trips(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        app.saveDefaultBlocks(["Kids", "Sports"])
        self.assertEqual(app.getDefaultBlocks(), ["Kids", "Sports"])
        with open(app.configFile) as f:
            self.assertEqual(json.load(f)["default blocks"], ["Kids", "Sports"])

    def test_keeps_only_strings(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}, "default blocks": ["Kids", 5, None]})
        self.assertEqual(app.getDefaultBlocks(), ["Kids"])


class DefaultBlocksScopingTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, feedConfig())
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "playChannel", return_value="OK")
        self.playChannel = patcher.start()
        self.addCleanup(patcher.stop)

    def playlist(self, username=None, password="12345"):
        headers = basic(username, password) if username else {}
        body = self.client.get("/playlist", headers=headers).get_data(as_text=True)
        return {cid for cid in ("1", "2", "3") if "/play/{}/{}".format(PORTAL, cid) in body}

    def lineupNumbers(self, username=None, password="12345"):
        headers = basic(username, password) if username else {}
        response = self.client.get("/lineup.json", headers=headers)
        return sorted(e["GuideNumber"] for e in response.get_json())

    def test_anonymous_playlist_is_default_scoped(self):
        self.assertEqual(self.playlist(), {"1", "2"})

    def test_anonymous_lineup_json_is_default_scoped(self):
        self.assertEqual(self.lineupNumbers(), ["101", "102"])

    def test_public_channel_with_no_default_block_stays_visible(self):
        self.assertIn("1", self.playlist())

    def test_operator_still_gets_the_full_lineup(self):
        self.assertEqual(self.playlist("admin"), {"1", "2", "3"})
        self.assertEqual(self.lineupNumbers("admin"), ["101", "102", "103"])

    def test_off_default_block_contributes_nothing(self):
        self.app.getBlocks()["Kids"] = "false"
        self.assertEqual(self.playlist(), {"1"})

    def test_empty_default_set_is_off(self):
        self.app.config["default blocks"] = []
        self.assertEqual(self.playlist(), {"1", "2", "3"})

    def test_applies_when_security_is_off(self):
        self.app.getSettings()["enable security"] = "false"
        self.assertEqual(self.playlist(), {"1", "2"})

    def test_no_credential_play_is_unchanged(self):
        response = self.client.get("/play/{}/3".format(PORTAL))
        self.assertNotEqual(response.status_code, 404)
        self.playChannel.assert_called_once()


class DefaultBlocksHiddenTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, feedConfig(**{"hidden blocks": ["Sports"], "default blocks": ["Kids", "Sports"]}))
        self.client = self.app.app.test_client()

    def test_hidden_block_never_leaks_to_anonymous(self):
        body = self.client.get("/playlist").get_data(as_text=True)
        self.assertIn("/play/{}/1".format(PORTAL), body)
        self.assertIn("/play/{}/2".format(PORTAL), body)
        self.assertNotIn("/play/{}/3".format(PORTAL), body)


class DefaultBlocksAdminTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, feedConfig(**{"hidden blocks": ["Sports"]}))
        self.client = self.app.app.test_client()

    def test_page_shows_the_selector_preselecting_the_set(self):
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("Default blocks (unauthenticated clients)", body)
        self.assertIn('<option value="Kids" selected>Kids</option>', body)
        self.assertNotIn('<option value="Sports"', body)

    def test_saves_only_known_non_hidden_names(self):
        response = self.client.post(
            "/blocks/defaults", data={"default blocks": ["Kids", "Sports", "Nope"]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.app.getDefaultBlocks(), ["Kids"])

    def test_clearing_saves_an_empty_set(self):
        self.client.post("/blocks/defaults", data={})
        self.assertEqual(self.app.getDefaultBlocks(), [])


if __name__ == "__main__":
    unittest.main()
