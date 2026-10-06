import json
import time
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class SavedFiltersTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.client = self.app.app.test_client()

    def post(self, page, body):
        return self.client.post("/filters/" + page, data=json.dumps(body), content_type="application/json")

    def test_save_list_and_delete(self):
        self.post("editor", {"name": " Canadian sports ", "filters": {"name": "TSN, sportsnet", "mode": "words"}})
        self.post("editor", {"name": "UK", "filters": {"genre": "ENGLISH | UK"}})
        self.assertEqual(sorted(self.client.get("/filters/editor").get_json()), ["Canadian sports", "UK"])
        self.assertEqual(self.client.get("/filters/guide").get_json(), {})  # each page has its own
        self.post("editor", {"name": "UK", "filters": {}, "delete": True})
        self.assertEqual(list(self.client.get("/filters/editor").get_json()), ["Canadian sports"])

    def test_kept_in_config_json(self):
        self.post("guide", {"name": "Hockey", "filters": {"q": "hockey", "onNow": True}})
        self.app.config = self.app.loadConfig()
        self.assertEqual(self.app.getSavedFilters()["guide"]["Hockey"], {"q": "hockey", "onNow": True})

    def test_bad_requests(self):
        self.assertEqual(self.post("editor", {"name": "", "filters": {}}).status_code, 400)
        self.assertEqual(self.post("editor", {"name": "x", "filters": "nope"}).status_code, 400)
        self.assertEqual(self.post("editor", {"name": "x", "filters": {"a": "y" * 5000}}).status_code, 400)
        self.assertEqual(self.post("portals", {"name": "x", "filters": {}}).status_code, 400)
        self.assertEqual(self.client.get("/filters/portals").status_code, 404)


def entry(start, stop, name, descr=""):
    return {"start_timestamp": str(int(start)), "stop_timestamp": str(int(stop)), "name": name, "descr": descr}


class GuideSearchModesTest(unittest.TestCase):
    def setUp(self):
        channels = [
            {"id": "1", "name": "TSN 1 FHD", "number": "101", "tv_genre_id": "9", "logo": ""},
            {"id": "2", "name": "SPORTSNET ONE", "number": "102", "tv_genre_id": "9", "logo": ""},
            {"id": "3", "name": "MOVIES 24/7", "number": "103", "tv_genre_id": "9", "logo": ""},
        ]
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.client = self.app.app.test_client()
        now = time.time()
        epg = {"1": [entry(now - 60, now + 600, "Oilers at Flames", "NHL hockey")],
               "2": [entry(now - 60, now + 600, "Sportsnet Central", "Highlights")],
               "3": [entry(now - 60, now + 600, "Tsnami", "A film")]}
        for name, value in {"getAllChannels": channels, "getEpg": epg}.items():
            patcher = mock.patch.object(self.app.stb, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def titles(self, **params):
        res = self.client.get("/guide/search", query_string=params)
        return res.get_json().get("error") or sorted(r["title"] for r in res.get_json()["results"])

    def test_words_start_with_by_default(self):
        self.assertEqual(self.titles(q="oiler"), ["Oilers at Flames"])
        self.assertEqual(self.titles(q="tsn"), ["Tsnami"])  # starts a word; inside "Sportsnet" doesn't count

    def test_other_modes(self):
        self.assertEqual(self.titles(q="oiler", mode="words"), [])
        self.assertEqual(self.titles(q="tsn", mode="contains"), ["Sportsnet Central", "Tsnami"])
        self.assertEqual(self.titles(q="hockey, highlights -central", mode="words"), ["Oilers at Flames"])

    def test_channel_filter_alone_lists_those_channels(self):
        self.assertEqual(self.titles(channel="TSN"), ["Oilers at Flames"])  # not SPORTSNET
        self.assertEqual(self.titles(channel="TSN, sportsnet"), ["Oilers at Flames", "Sportsnet Central"])

    def test_bad_regex_says_so(self):
        self.assertIn("Not a valid regex", self.titles(q="[", mode="regex"))


if __name__ == "__main__":
    unittest.main()
