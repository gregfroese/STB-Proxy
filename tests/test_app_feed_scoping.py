import base64
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
    }
    config.update(overrides)
    return config


class ScopingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, feedConfig())
        self.client = self.app.app.test_client()

    def addAccount(self, username, password, blocks, enabled=True):
        self.app.getAccounts().append(
            {
                "username": username,
                "hash": self.app.accounts.hashPassword(password),
                "blocks": blocks,
                "enabled": enabled,
            }
        )

    def playlist(self, username=None, password="secret"):
        headers = basic(username, password) if username else {}
        body = self.client.get("/playlist", headers=headers).get_data(as_text=True)
        return {cid for cid in ("1", "2", "3") if "/play/{}/{}".format(PORTAL, cid) in body}

    def lineupNumbers(self, username=None, password="secret"):
        headers = basic(username, password) if username else {}
        response = self.client.get("/lineup.json", headers=headers)
        return response, sorted(e["GuideNumber"] for e in response.get_json())


class AccountScopingTest(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.addAccount("katie", "secret", ["Kids"])

    def test_playlist_scoped_to_account(self):
        self.assertEqual(self.playlist("katie"), {"1", "2"})

    def test_lineup_json_scoped_to_account(self):
        _, numbers = self.lineupNumbers("katie")
        self.assertEqual(numbers, ["101", "102"])

    def test_xmltv_scoped_to_account(self):
        body = self.client.get("/xmltv", headers=basic("katie", "secret")).get_data(as_text=True)
        self.assertIn('id="p1.1"', body)
        self.assertIn('id="p1.2"', body)
        self.assertNotIn('id="p1.3"', body)

    def test_zero_block_account_sees_only_public_channels(self):
        self.addAccount("newbie", "secret", [])
        self.assertEqual(self.playlist("newbie"), {"1"})
        _, numbers = self.lineupNumbers("newbie")
        self.assertEqual(numbers, ["101"])

    def test_operator_is_unchanged(self):
        self.assertEqual(self.playlist("admin", "12345"), {"1", "2", "3"})
        _, numbers = self.lineupNumbers("admin", "12345")
        self.assertEqual(numbers, ["101", "102", "103"])

    def test_anonymous_is_unchanged(self):
        self.assertEqual(self.playlist(), {"1", "2", "3"})
        _, numbers = self.lineupNumbers()
        self.assertEqual(numbers, ["101", "102", "103"])

    def test_disabled_account_does_not_scope(self):
        self.addAccount("revoked", "secret", ["Kids"], enabled=False)
        self.assertEqual(self.playlist("revoked"), {"1", "2", "3"})


class HiddenBlockScopingTest(ScopingTestCase):
    def setUp(self):
        self.app = loadApp(self, feedConfig(**{"hidden blocks": ["Sports"]}))
        self.client = self.app.app.test_client()
        self.addAccount("katie", "secret", ["Kids", "Sports"])

    def test_hidden_block_never_leaks_to_an_account(self):
        self.assertEqual(self.playlist("katie"), {"1", "2"})

    def test_hidden_block_stays_out_of_the_full_lineup(self):
        self.assertEqual(self.playlist(), {"1", "2"})


class DeadChannelScopingTest(ScopingTestCase):
    def setUp(self):
        self.app = loadApp(self, feedConfig(**{
            "portals": {PORTAL: portalConfig(**{
                "enabled channels": ["1"],
                "channel blocks": {"2": "Kids", "3": "Kids"},
                "dead channels": ["2"],
            })},
        }))
        self.client = self.app.app.test_client()
        self.addAccount("katie", "secret", ["Kids"])

    def test_dead_channels_are_removed_from_an_account(self):
        self.assertEqual(self.playlist("katie"), {"1", "3"})


class RejectionTest(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.addAccount("katie", "secret", ["Kids"])
        self.app.getSettings()["enable security"] = "true"

    def test_wrong_credentials_get_the_challenge_on_feeds(self):
        for username, password in (("katie", "wrong"), ("nobody", "secret")):
            response = self.client.get("/playlist", headers=basic(username, password))
            self.assertEqual(response.status_code, 401)
            self.assertIn("Could not verify your login!", response.get_data(as_text=True))
            self.assertEqual(
                response.headers.get("WWW-Authenticate"), 'Basic realm="Login Required"'
            )

    def test_wrong_credentials_get_404_under_hdhr(self):
        response = self.client.get("/lineup.json", headers=basic("katie", "wrong"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_data(as_text=True), "Error")

    def test_valid_account_is_not_rejected(self):
        self.assertEqual(self.client.get("/playlist", headers=basic("katie", "secret")).status_code, 200)

    def test_anonymous_with_security_on_is_rejected(self):
        self.assertEqual(self.client.get("/playlist").status_code, 401)
        self.assertEqual(self.client.get("/lineup.json").status_code, 404)


class SecurityOffTest(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.addAccount("katie", "secret", ["Kids"])
        self.app.getSettings()["enable security"] = "false"

    def test_valid_account_still_scopes_when_security_is_off(self):
        self.assertEqual(self.playlist("katie"), {"1", "2"})

    def test_anonymous_gets_the_full_lineup_when_security_is_off(self):
        self.assertEqual(self.playlist(), {"1", "2", "3"})

    def test_lineup_json_still_scopes_a_presented_account(self):
        _, numbers = self.lineupNumbers("katie")
        self.assertEqual(numbers, ["101", "102"])


class PlayScopingTest(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.addAccount("katie", "secret", ["Kids"])
        patcher = mock.patch.object(self.app, "playChannel", return_value="OK")
        self.playChannel = patcher.start()
        self.addCleanup(patcher.stop)

    def play(self, channelId, username=None, password="secret", query=""):
        headers = basic(username, password) if username else {}
        return self.client.get("/play/{}/{}{}".format(PORTAL, channelId, query), headers=headers)

    def test_account_channel_not_in_lineup_is_404(self):
        self.assertEqual(self.play("3", "katie").status_code, 404)
        self.playChannel.assert_not_called()

    def test_account_channel_in_lineup_is_allowed(self):
        self.assertEqual(self.play("2", "katie").status_code, 200)
        self.playChannel.assert_called_once()

    def test_operator_is_unchanged(self):
        self.assertEqual(self.play("3", "admin", "12345").status_code, 200)

    def test_anonymous_is_unchanged(self):
        self.assertEqual(self.play("3").status_code, 200)

    def test_web_preview_bypasses_scoping(self):
        self.assertEqual(self.play("3", "katie", query="?web=true").status_code, 200)

    def test_unknown_portal_is_left_as_before(self):
        response = self.client.get("/play/nope/1", headers=basic("katie", "secret"))
        self.assertNotEqual(response.status_code, 404)


class AdminGateTest(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.addAccount("katie", "secret", ["Kids"])
        self.app.getSettings()["enable security"] = "true"

    def test_an_account_cannot_reach_the_web_ui(self):
        for path in ("/blocks", "/accounts", "/settings"):
            response = self.client.get(path, headers=basic("katie", "secret"))
            self.assertEqual(response.status_code, 401, path)

    def test_the_operator_still_reaches_the_web_ui(self):
        self.assertEqual(self.client.get("/blocks", headers=basic("admin", "12345")).status_code, 200)


if __name__ == "__main__":
    unittest.main()
