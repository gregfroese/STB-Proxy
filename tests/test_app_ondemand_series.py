"""Series detail with its Seasons, and a Season's Episodes: /api/ondemand/item and
/api/ondemand/series/<portal>/<seriesId>/season/<seasonId> (the viewer On Demand API
contract), fetched from a fake portal through the stubbed stb calls (no network)."""
import unittest
from unittest import mock

from tests.test_app_ondemand_browse import OFF_URL, URL1, BrowseTestCase, movie
from tests.test_ondemand_series import infomirEpisode, infomirSeason, infomirSeries


class SeriesRoutesTest(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [infomirSeries(77, "Show"), movie(5, "Heat", "2026-10-01 10:00:00")])
        self.fill("p3", [infomirSeries(88, "Hidden show")])
        self.lists = {
            (URL1, (("movie_id", "77"),)): [infomirSeason(31685, 2, "Second", 4), infomirSeason(31684, 1, "", 14)],
            (URL1, (("movie_id", "77"), ("season_id", "31685"))): [
                infomirEpisode(902, 31685, 2, "Two"), infomirEpisode(901, 31685, 1, "One")],
        }
        self.requests = []
        self.failing = False
        patcher = mock.patch.object(self.app.stb, "getOnDemandList", side_effect=self.portal)
        patcher.start()
        self.addCleanup(patcher.stop)

    def portal(self, url, mac, token, params, page, proxy=None, source="vod"):
        self.requests.append((url, dict(params), page, source))
        if self.failing:
            return None
        rows = self.lists.get((url, tuple(sorted(params.items()))), [])
        return {"total": len(rows), "pageSize": 14, "items": rows[(page - 1) * 14:page * 14]}

    def fetch(self, path, status=200):
        response = self.get(path, "viewer")
        self.assertEqual(response.status_code, status, response.get_json())
        return response.get_json()

    def test_a_series_detail_lists_its_seasons_in_ascending_order(self):
        body = self.fetch("/api/ondemand/item/p1/77")
        self.assertEqual((body["kind"], body["name"], body["portalName"]), ("series", "Show", "First"))
        self.assertEqual(body["seasons"], [
            {"id": "31684", "number": 1, "name": None, "episodeCount": 14},
            {"id": "31685", "number": 2, "name": "Second", "episodeCount": 4},
        ])

    def test_a_movie_detail_has_no_seasons_and_asks_the_portal_nothing(self):
        self.assertNotIn("seasons", self.fetch("/api/ondemand/item/p1/5"))
        self.assertEqual(self.requests, [])

    def test_a_season_lists_its_episodes_in_ascending_order(self):
        self.assertEqual(self.fetch("/api/ondemand/series/p1/77/season/31685"), [
            {"id": "901", "seasonId": "31685", "number": 1, "name": "One"},
            {"id": "902", "seasonId": "31685", "number": 2, "name": "Two"},
        ])

    def test_unknown_series_seasons_and_switched_off_portals_are_not_found(self):
        for path in ("/api/ondemand/series/p1/404/season/1",       # no such Series
                     "/api/ondemand/series/p1/5/season/1",         # a Movie
                     "/api/ondemand/series/p1/77/season/999",      # not one of its Seasons
                     "/api/ondemand/series/p3/88/season/1",        # its portal is switched off
                     "/api/ondemand/series/nope/77/season/1",      # no such portal
                     "/api/ondemand/item/p3/88"):
            self.assertEqual(self.fetch(path, 404)["code"], "not_found", path)
        self.assertEqual([r for r in self.requests if r[0] == OFF_URL], [])

    def test_a_portal_failure_with_no_copy_is_a_portal_error_for_that_series_only(self):
        self.failing = True
        for path in ("/api/ondemand/item/p1/77", "/api/ondemand/series/p1/77/season/31685"):
            body = self.fetch(path, 502)
            self.assertEqual(body["code"], "portal_error", path)
            self.assertTrue(body["error"])
        self.assertEqual(self.fetch("/api/ondemand/item/p1/5")["name"], "Heat")

    def test_a_portal_failure_serves_the_copy_already_fetched(self):
        detail = self.fetch("/api/ondemand/item/p1/77")
        episodes = self.fetch("/api/ondemand/series/p1/77/season/31685")
        self.failing = True
        self.app.onDemandSeries().clock = lambda: 2e10  # long after the 6 h
        self.assertEqual(self.fetch("/api/ondemand/item/p1/77"), detail)
        self.assertEqual(self.fetch("/api/ondemand/series/p1/77/season/31685"), episodes)

    def test_the_gate_applies(self):
        self.addAccount("off", onDemand=False)
        response = self.get("/api/ondemand/series/p1/77/season/31685", "off")
        self.assertEqual((response.status_code, response.get_json()["code"]), (404, "on_demand_off"))


if __name__ == "__main__":
    unittest.main()
