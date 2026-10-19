import base64
import time
import unittest
from unittest import mock

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

HIT_FIELDS = {
    "portal",
    "channelId",
    "start",
    "stop",
    "title",
    "desc",
    "channelName",
    "channelNumber",
    "logo",
    "epgId",
}


def basic(username, password):
    token = base64.b64encode("{}:{}".format(username, password).encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + token}


def entry(start, stop, name, descr=""):
    return {
        "start_timestamp": str(int(start)),
        "stop_timestamp": str(int(stop)),
        "name": name,
        "descr": descr,
    }


def viewerConfig(**overrides):
    config = {
        "portals": {
            PORTAL: portalConfig(
                **{
                    "enabled channels": ["1"],
                    "custom channel names": {"2": "Sportsnet"},
                    "custom channel numbers": {"2": "999"},
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


class ViewerGuideTestCase(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, viewerConfig())
        self.app.stb.getAllChannels.return_value = CHANNELS
        self.client = self.app.app.test_client()
        self.addAccount("katie", "secret", ["Kids", "Sports"])
        self.addAccount("mike", "secret", ["Hidden"])

        now = time.time()
        titles = {
            "1": "One Show",
            "2": "Two Show",
            "3": "Three Show",
            "4": "Four Show",
            "5": "Five Show",
            "6": "Six Show",
            "7": "Seven Show",
            "8": "Eight Show",
        }
        self.epg = {cid: [entry(now - 600, now + 600, title)] for cid, title in titles.items()}
        patcher = mock.patch.object(self.app.stb, "getEpg", return_value=self.epg)
        patcher.start()
        self.addCleanup(patcher.stop)

    def addAccount(self, username, password, blocks, enabled=True):
        self.app.getAccounts().append(
            {
                "username": username,
                "hash": self.app.accounts.hashPassword(password),
                "blocks": blocks,
                "enabled": enabled,
            }
        )

    def search(self, username=None, password="secret", **params):
        headers = basic(username, password) if username else {}
        return self.client.get("/api/guide/search", query_string=params, headers=headers).get_json()

    def searchResponse(self, username=None, password="secret", **params):
        headers = basic(username, password) if username else {}
        return self.client.get("/api/guide/search", query_string=params, headers=headers)

    def channels(self, username=None, password="secret", **params):
        res = self.search(username, password, now="true", **params)
        return {r["channelId"] for r in res["results"]}

    def channelGuide(self, username=None, **params):
        headers = basic(username, "secret") if username else {}
        return self.client.get("/api/guide/channel", query_string=params, headers=headers)


class SearchTest(ViewerGuideTestCase):
    def test_envelope_fields(self):
        res = self.search("katie", q="show")
        self.assertEqual(
            set(res.keys()),
            {"results", "total", "loadedAt", "programmes", "failed", "partial", "account"},
        )
        self.assertEqual(res["account"], "katie")
        self.assertEqual(res["failed"], [])
        self.assertEqual(res["partial"], [])

    def test_hit_fields_are_trimmed(self):
        res = self.search("katie", q="two show")
        self.assertEqual(res["total"], 1)
        self.assertEqual(set(res["results"][0].keys()), HIT_FIELDS)

    def test_hit_values_join_to_the_channel(self):
        hit = self.search("katie", q="two")["results"][0]
        self.assertEqual(hit["portal"], PORTAL)
        self.assertEqual(hit["channelId"], "2")
        self.assertEqual(hit["channelName"], "Sportsnet")  # custom name wins
        self.assertEqual(hit["channelNumber"], "999")  # custom number wins
        self.assertEqual(hit["epgId"], PORTAL[:6] + ".2")
        self.assertEqual(hit["title"], "Two Show")

    def test_epg_id_falls_back_to_the_default(self):
        hit = self.search("katie", q="one show")["results"][0]
        self.assertEqual(hit["epgId"], PORTAL[:6] + ".1")

    def test_account_is_scoped_to_its_lineup(self):
        self.assertEqual(self.channels("katie"), {"1", "2", "3", "4"})

    def test_hidden_block_is_invisible_unless_assigned(self):
        self.assertNotIn("6", self.channels("katie"))
        self.assertIn("6", self.channels("mike"))

    def test_dead_channels_are_always_hidden(self):
        self.assertNotIn("7", self.channels("katie"))

    def test_operator_gets_the_full_lineup_minus_hidden(self):
        self.assertEqual(self.channels("admin", password="12345"), {"1", "2", "3", "4", "8"})

    def test_empty_query_returns_nothing(self):
        self.assertEqual(self.search("katie")["results"], [])

    def test_on_now_without_a_query_lists_airing_programmes(self):
        res = self.search("katie", now="true")
        self.assertEqual(len(res["results"]), 4)

    def test_bad_regex_is_a_400(self):
        response = self.searchResponse("katie", q="(", mode="regex")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_limit_caps_results_but_not_total(self):
        res = self.search("katie", q="show", limit="1")
        self.assertEqual(len(res["results"]), 1)
        self.assertEqual(res["total"], 4)

    def test_limit_is_clamped_to_the_maximum(self):
        res = self.search("katie", q="show", limit="9999")
        self.assertEqual(len(res["results"]), 4)

    def test_channel_sub_filter_narrows_results(self):
        res = self.search("katie", now="true", channel="sportsnet")
        self.assertEqual([r["channelId"] for r in res["results"]], ["2"])

    def test_guide_is_cached_between_searches(self):
        self.search("katie", q="one")
        self.search("katie", q="two")
        self.assertEqual(self.app.stb.getEpg.call_count, 1)


class ChannelTimelineTest(ViewerGuideTestCase):
    def test_returns_the_channels_upcoming_programmes(self):
        res = self.channelGuide("katie", portal=PORTAL, channelId="1").get_json()
        self.assertEqual([p["title"] for p in res["programmes"]], ["One Show"])
        self.assertEqual(set(res["programmes"][0].keys()), {"start", "stop", "title", "desc"})

    def test_out_of_lineup_channel_is_a_404(self):
        response = self.channelGuide("katie", portal=PORTAL, channelId="8")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "Unknown channel")

    def test_hidden_block_channel_is_scoped(self):
        self.assertEqual(self.channelGuide("katie", portal=PORTAL, channelId="6").status_code, 404)
        self.assertEqual(self.channelGuide("mike", portal=PORTAL, channelId="6").status_code, 200)

    def test_unknown_portal_is_a_404(self):
        self.assertEqual(self.channelGuide("katie", portal="nope", channelId="1").status_code, 404)


if __name__ == "__main__":
    unittest.main()
