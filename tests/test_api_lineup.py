import base64
import unittest

from tests.support import PORTAL, loadApp, portalConfig

CHANNELS = [
    {"id": "1", "name": "One", "number": "101", "tv_genre_id": "9", "logo": ""},
    {"id": "2", "name": "Two", "number": "102", "tv_genre_id": "9", "logo": ""},
    {"id": "3", "name": "Three", "number": "103", "tv_genre_id": "9", "logo": ""},
    {"id": "4", "name": "Four", "number": "100", "tv_genre_id": "9", "logo": ""},
    {"id": "5", "name": "Five", "number": "105", "tv_genre_id": "9", "logo": ""},
    {"id": "6", "name": "Six", "number": "106", "tv_genre_id": "9", "logo": ""},
    {"id": "7", "name": "Seven", "number": "107", "tv_genre_id": "9", "logo": ""},
    {"id": "8", "name": "Eight", "number": "108", "tv_genre_id": "9", "logo": ""},
]

CHANNEL_FIELDS = {
    "portal",
    "portalName",
    "channelId",
    "name",
    "number",
    "logo",
    "genre",
    "epgId",
    "blocks",
    "favourite",
    "blockFavourites",
    "url",
}


def basic(username, password):
    token = base64.b64encode("{}:{}".format(username, password).encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + token}


def lineupConfig(**overrides):
    config = {
        "portals": {
            PORTAL: portalConfig(
                **{
                    "enabled channels": ["1"],
                    "channel blocks": {
                        "2": ["Kids"],
                        "3": ["Sports"],
                        "4": ["Kids", "Sports"],
                        "5": ["Movies"],
                        "6": ["Hidden"],
                        "7": ["Empty"],
                        "8": ["News"],
                    },
                    "dead channels": ["7"],
                }
            )
        },
        "blocks": {
            "Kids": "true",
            "Sports": "true",
            "Movies": "false",
            "Hidden": "true",
            "Empty": "true",
            "News": "true",
        },
        "hidden blocks": ["Hidden"],
    }
    config.update(overrides)
    return config


class ApiLineupTestCase(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, lineupConfig())
        self.app.stb.getAllChannels.return_value = CHANNELS
        self.client = self.app.app.test_client()
        self.addAccount("katie", "secret", ["Kids", "Sports"])

    def addAccount(self, username, password, blocks, enabled=True):
        self.app.getAccounts().append(
            {
                "username": username,
                "hash": self.app.accounts.hashPassword(password),
                "blocks": blocks,
                "enabled": enabled,
            }
        )

    def lineup(self, username=None, password="secret"):
        headers = basic(username, password) if username else {}
        return self.client.get("/api/lineup", headers=headers)

    def data(self, username=None, password="secret"):
        return self.lineup(username, password).get_json()

    def byId(self, data):
        return {c["channelId"]: c for c in data["channels"]}


class EnvelopeTest(ApiLineupTestCase):
    def test_envelope_fields(self):
        data = self.data("katie")
        self.assertEqual(set(data.keys()), {"account", "blocks", "channels", "failedPortals"})
        self.assertEqual(data["account"], "katie")
        self.assertIsInstance(data["blocks"], list)
        self.assertIsInstance(data["channels"], list)
        self.assertEqual(data["failedPortals"], [])

    def test_channel_fields_present_and_named(self):
        channel = self.byId(self.data("katie"))["1"]
        self.assertEqual(set(channel.keys()), CHANNEL_FIELDS)

    def test_channel_values(self):
        channel = self.byId(self.data("katie"))["1"]
        self.assertEqual(channel["portal"], PORTAL)
        self.assertEqual(channel["portalName"], "Test portal")
        self.assertEqual(channel["channelId"], "1")
        self.assertEqual(channel["name"], "One")
        self.assertEqual(channel["number"], "101")
        self.assertEqual(channel["genre"], "Sports")
        self.assertEqual(channel["epgId"], PORTAL[:6] + ".1")
        self.assertEqual(channel["blocks"], [])
        self.assertEqual(channel["url"], "/play/{}/1".format(PORTAL))

    def test_custom_values_resolve_first(self):
        portal = self.app.getPortals()[PORTAL]
        portal["custom channel names"] = {"1": "Custom One"}
        portal["custom channel numbers"] = {"1": "999"}
        portal["custom genres"] = {"1": "Films"}
        portal["custom epg ids"] = {"1": "custom.one"}
        portal["custom logos"] = {"1": "https://cdn/custom.png"}
        channel = self.byId(self.data("katie"))["1"]
        self.assertEqual(channel["name"], "Custom One")
        self.assertEqual(channel["number"], "999")
        self.assertEqual(channel["genre"], "Films")
        self.assertEqual(channel["epgId"], "custom.one")
        self.assertEqual(channel["logo"], "https://cdn/custom.png")


class VisibilityTest(ApiLineupTestCase):
    def test_blocks_follow_the_operator_order(self):
        self.app.config["block order"] = ["Sports", "Kids"]
        self.assertEqual(self.data("katie")["blocks"], ["Sports", "Kids"])

    def test_operator_gets_full_lineup(self):
        data = self.data("admin", "12345")
        self.assertIsNone(data["account"])
        self.assertEqual(set(self.byId(data)), {"1", "2", "3", "4", "8"})
        self.assertEqual(data["blocks"], ["Kids", "News", "Sports"])

    def test_account_is_scoped(self):
        data = self.data("katie")
        self.assertEqual(set(self.byId(data)), {"1", "2", "3", "4"})

    def test_hidden_block_not_assigned_never_appears(self):
        data = self.data("katie")
        self.assertNotIn("Hidden", data["blocks"])
        for channel in data["channels"]:
            self.assertNotIn("Hidden", channel["blocks"])

    def test_an_account_assigned_a_hidden_block_sees_it(self):
        self.addAccount("mike", "secret", ["Hidden"])
        data = self.data("mike")
        self.assertIn("Hidden", data["blocks"])
        self.assertIn("6", self.byId(data))
        self.assertEqual(self.byId(data)["6"]["blocks"], ["Hidden"])

    def test_off_block_never_appears(self):
        data = self.data("katie")
        self.assertNotIn("Movies", data["blocks"])
        self.assertNotIn("5", self.byId(data))

    def test_empty_block_is_omitted_everywhere(self):
        data = self.data("katie")
        self.assertNotIn("Empty", data["blocks"])
        for channel in data["channels"]:
            self.assertNotIn("Empty", channel["blocks"])

    def test_multi_block_membership_is_listed_in_full(self):
        self.assertEqual(self.byId(self.data("katie"))["4"]["blocks"], ["Kids", "Sports"])

    def test_public_channel_in_no_block_gets_empty_list(self):
        self.assertEqual(self.byId(self.data("katie"))["1"]["blocks"], [])

    def test_favourites_are_flagged_and_sorted_first(self):
        self.app.getPortals()[PORTAL]["favourite channels"] = ["4"]
        self.app.config["block favourites"] = {"Kids": {PORTAL: ["2"]}}
        data = self.data("katie")
        byId = self.byId(data)
        self.assertTrue(byId["4"]["favourite"])
        self.assertEqual(byId["2"]["blockFavourites"], ["Kids"])
        self.assertFalse(byId["2"]["favourite"])
        # The overall favourite is first, then the block favourite, then the rest.
        self.assertEqual([c["channelId"] for c in data["channels"]][:2], ["4", "2"])

    def test_envelope_blocks_only_those_with_visible_channels(self):
        self.assertEqual(self.data("katie")["blocks"], ["Kids", "Sports"])

    def test_security_off_still_scopes_a_presented_account(self):
        self.app.getSettings()["enable security"] = "false"
        data = self.data("katie")
        self.assertEqual(data["account"], "katie")
        self.assertEqual(set(self.byId(data)), {"1", "2", "3", "4"})


class OrderingTest(ApiLineupTestCase):
    def test_channels_sort_by_number_then_name(self):
        data = self.data("katie")
        self.assertEqual([c["number"] for c in data["channels"]], ["100", "101", "102", "103"])

    def test_blocks_sort_alphabetically(self):
        self.assertEqual(self.data("katie")["blocks"], ["Kids", "Sports"])

    def test_url_is_relative_with_no_web_query(self):
        for channel in self.data("katie")["channels"]:
            self.assertTrue(channel["url"].startswith("/play/{}/".format(PORTAL)))
            self.assertNotIn("?", channel["url"])


class FailureTest(ApiLineupTestCase):
    def test_failed_portal_is_best_effort_200(self):
        self.app.stb.getAllChannels.return_value = None
        response = self.lineup("katie")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["channels"], [])
        self.assertEqual(data["failedPortals"], ["Test portal"])

    def test_wrong_credentials_get_the_challenge(self):
        self.app.getSettings()["enable security"] = "true"
        response = self.lineup("katie", "wrong")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Could not verify your login!", response.get_data(as_text=True))
        self.assertEqual(response.headers.get("WWW-Authenticate"), 'Basic realm="Login Required"')

    def test_route_is_not_api_token_guarded(self):
        response = self.client.get("/api/lineup", headers=basic("admin", "12345"))
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
