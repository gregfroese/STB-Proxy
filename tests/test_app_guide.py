import time
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


def entry(start, stop, name, descr=""):
    return {"start_timestamp": str(int(start)), "stop_timestamp": str(int(stop)), "name": name, "descr": descr}


class GuideTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {
                PORTAL: portalConfig(
                    **{
                        "enabled channels": ["1"],
                        "custom channel names": {"2": "Sportsnet"},
                        "favourite channels": ["2"],
                        "dead channels": ["3"],
                        "channel blocks": {"2": ["NHL"]},
                    }
                )
            },
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        now = time.time()
        self.epg = {
            "1": [entry(now - 600, now + 600, "Morning News", "Headlines")],
            "2": [entry(now + 3600, now + 7200, "Oilers at Flames", "NHL hockey")],
            "3": [entry(now - 60, now + 60, "Hockey Classics")],
        }
        patcher = mock.patch.object(self.app.stb, "getEpg", return_value=self.epg)
        self.getEpg = patcher.start()
        self.addCleanup(patcher.stop)

    def search(self, **params):
        return self.client.get("/guide/search", query_string=params).get_json()

    def titles(self, **params):
        return [r["title"] for r in self.search(**params)["results"]]

    def test_search_returns_channel_details_for_preview(self):
        res = self.search(q="oilers")
        self.assertEqual(res["total"], 1)
        r = res["results"][0]
        self.assertEqual(r["title"], "Oilers at Flames")
        self.assertEqual(r["channelName"], "Two")
        self.assertEqual(r["customChannelName"], "Sportsnet")
        self.assertEqual(r["channelNumber"], "102")
        self.assertTrue(r["favourite"])
        self.assertFalse(r["available"])
        self.assertEqual(r["blocks"], ["NHL"])
        self.assertEqual(r["link"], "/play/p1/2?web=true")  # relative: works through a reverse proxy

    def test_searches_channels_outside_the_lineup(self):
        self.assertEqual(self.titles(q="hockey"), ["Oilers at Flames"])  # 3 is dead, hidden by default

    def test_filters(self):
        self.assertEqual(self.titles(q="hockey", hideDead="false"), ["Hockey Classics", "Oilers at Flames"])
        self.assertEqual(self.titles(now="true"), ["Morning News"])
        self.assertEqual(self.titles(lineup="true"), ["Morning News"])
        self.assertEqual(self.titles(favourites="true"), ["Oilers at Flames"])

    def test_empty_search_returns_nothing(self):
        self.assertEqual(self.search()["results"], [])

    def test_guide_is_cached_until_refresh(self):
        self.search(q="news")
        self.search(q="hockey")
        self.assertEqual(self.getEpg.call_count, 1)
        self.search(q="news", refresh="true")
        self.assertEqual(self.getEpg.call_count, 2)

    def test_portal_without_bulk_guide_falls_back_to_lineup(self):
        self.getEpg.return_value = None
        with mock.patch.object(
            self.app.stb, "getShortEpg", return_value={"1": self.epg["1"]}
        ) as getShortEpg:
            res = self.search(q="news")
        self.assertEqual(getShortEpg.call_args[0][3], {"1"})
        self.assertEqual([r["title"] for r in res["results"]], ["Morning News"])
        self.assertEqual(res["partial"], ["Test portal"])

    def test_failed_portal_is_reported_and_retried_sooner(self):
        with mock.patch.object(self.app.stb, "getAllChannels", return_value=None):
            res = self.search(q="news")
        self.assertEqual(res["failed"], ["Test portal"])
        self.assertEqual(res["results"], [])
        self.assertLess(self.app.guideCache["loaded"], time.time() - self.app.GUIDE_MAX_AGE + self.app.GUIDE_RETRY_AGE + 1)

    def test_guide_page(self):
        body = self.client.get("/guide").get_data(as_text=True)
        self.assertIn('id="query"', body)
        self.assertIn('id="playerPanel"', body)
        self.assertIn('id="blockChoices" data-blocks=\'["NHL"]\'', body)
        self.assertIn('href="/guide"', body)


if __name__ == "__main__":
    unittest.main()
