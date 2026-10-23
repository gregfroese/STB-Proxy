"""Resume points, Watched, Up next and Continue watching (ADR 0006): PUT /api/ondemand/progress,
GET /api/ondemand/continue, and the `progress` / `upNext` fields folded into the browse,
detail and Episode responses. The portal is faked through the stubbed stb calls."""
import unittest
from unittest import mock

from tests.test_api_lineup import basic
from tests.test_app_ondemand_browse import URL1, BrowseTestCase, movie
from tests.test_ondemand_series import infomirEpisode, infomirSeason, infomirSeries

T0 = 1_800_000_000


class ProgressTestCase(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [movie(5, "Heat", "2026-10-01 10:00:00"), movie(6, "Ronin", "2026-10-02 10:00:00"),
                         infomirSeries(77, "Show")])
        self.fill("p3", [movie(9, "Switched off", "2026-10-01 10:00:00")])
        self.lists = {}
        self.requests = []
        patcher = mock.patch.object(self.app.stb, "getOnDemandList", side_effect=self.portal)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = T0
        self.app.onDemandProgress().clock = lambda: self.now

    def addAccount(self, *args, **kwargs):
        # A cheap password hash: these tests log in on every report.
        with mock.patch.object(self.app.accounts, "ITERATIONS", 1000):
            super().addAccount(*args, **kwargs)

    def portal(self, url, mac, token, params, page, proxy=None, source="vod"):
        self.requests.append(dict(params))
        rows = self.lists.get((url, tuple(sorted(params.items()))), [])
        return {"total": len(rows), "pageSize": 14, "items": rows[(page - 1) * 14:page * 14]}

    def report(self, body, username="viewer", status=204):
        response = self.client.put("/api/ondemand/progress", json=body, headers=basic(username, "secret"))
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response

    def fetch(self, path, username="viewer"):
        response = self.get(path, username)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def movieProgress(self, id="5", username="viewer"):
        return self.fetch("/api/ondemand/item/p1/{}".format(id), username)["progress"]


class MovieProgressTest(ProgressTestCase):
    def test_a_reported_position_is_the_movies_resume_point(self):
        self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.assertEqual(self.movieProgress(), {
            "positionSec": 600, "durationSec": 6000, "watched": False, "updatedAt": T0})

    def test_under_a_minute_is_no_resume_point(self):
        self.report({"portal": "p1", "id": "5", "positionSec": 59, "durationSec": 6000})
        self.assertIsNone(self.movieProgress())

    def test_going_back_under_a_minute_clears_the_resume_point(self):
        self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.report({"portal": "p1", "id": "5", "positionSec": 20, "durationSec": 6000})
        self.assertIsNone(self.movieProgress())

    def test_ninety_percent_of_the_duration_is_watched_and_clears_the_resume_point(self):
        self.report({"portal": "p1", "id": "5", "positionSec": 5399, "durationSec": 6000})
        self.assertFalse(self.movieProgress()["watched"])
        self.now += 30
        self.report({"portal": "p1", "id": "5", "positionSec": 5400, "durationSec": 6000})
        self.assertEqual(self.movieProgress(), {
            "positionSec": None, "durationSec": 6000, "watched": True, "updatedAt": T0 + 30})

    def test_the_end_is_watched(self):
        self.report({"portal": "p1", "id": "5", "positionSec": 6000.4, "durationSec": 6000.4})
        self.assertTrue(self.movieProgress()["watched"])

    def test_rewatching_keeps_watched_and_records_a_new_resume_point(self):
        self.report({"portal": "p1", "id": "5", "watched": True})
        self.report({"portal": "p1", "id": "5", "positionSec": 120.7, "durationSec": 6000.2})
        self.assertEqual(self.movieProgress(), {
            "positionSec": 120, "durationSec": 6000, "watched": True, "updatedAt": T0})

    def test_with_no_duration_the_position_is_kept_but_never_watched(self):
        for duration in (None, 0):
            self.report({"portal": "p1", "id": "5", "positionSec": 99999, "durationSec": duration})
            self.assertEqual(self.movieProgress(), {
                "positionSec": 99999, "durationSec": None, "watched": False, "updatedAt": T0})
        self.report({"portal": "p1", "id": "5", "positionSec": 600})
        self.assertFalse(self.movieProgress()["watched"])

    def test_marking_watched_by_hand_clears_the_resume_point(self):
        self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.report({"portal": "p1", "id": "5", "watched": True})
        self.assertEqual(self.movieProgress(), {
            "positionSec": None, "durationSec": 6000, "watched": True, "updatedAt": T0})

    def test_marking_unwatched_clears_watched_and_the_resume_point(self):
        self.report({"portal": "p1", "id": "5", "watched": True})
        self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.report({"portal": "p1", "id": "5", "watched": False})
        self.assertIsNone(self.movieProgress())

    def test_progress_belongs_to_the_account(self):
        self.addAccount("other", onDemand=True)
        self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.assertIsNone(self.movieProgress(username="other"))

    def test_movie_list_items_carry_their_progress(self):
        self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        items = {i["id"]: i for i in self.fetch("/api/ondemand/items")["items"]}
        self.assertEqual(items["5"]["progress"]["positionSec"], 600)
        self.assertIsNone(items["6"]["progress"])
        self.assertNotIn("progress", items["77"])
        self.assertIsNone(items["77"]["upNext"])


SEASONS = (URL1, (("movie_id", "77"),))
SEASON_1 = (URL1, (("movie_id", "77"), ("season_id", "31684")))
SEASON_2 = (URL1, (("movie_id", "77"), ("season_id", "31685")))


def episode(id, season, **fields):
    return dict({"portal": "p1", "seriesId": "77", "seasonId": season, "episodeId": id}, **fields)


class SeriesProgressTestCase(ProgressTestCase):
    """Show: Season 1 (31684) has Episodes 901 and 902, Season 2 (31685) has 911 and 912."""

    def setUp(self):
        super().setUp()
        self.lists = {
            SEASONS: [infomirSeason(31685, 2, "Second", 2), infomirSeason(31684, 1, "", 2)],
            SEASON_1: [infomirEpisode(902, 31684, 2, "Two"), infomirEpisode(901, 31684, 1, "One")],
            SEASON_2: [infomirEpisode(912, 31685, 2, "Twelve"), infomirEpisode(911, 31685, 1, "Eleven")],
        }
        # The viewer opened the Series and Season 1 to play from it.
        self.fetch("/api/ondemand/item/p1/77")
        self.fetch("/api/ondemand/series/p1/77/season/31684")
        self.requests.clear()

    def upNext(self):
        return self.fetch("/api/ondemand/item/p1/77")["upNext"]

    def episodes(self, season="31684"):
        return {e["id"]: e["progress"] for e in self.fetch("/api/ondemand/series/p1/77/season/" + season)}


class EpisodeProgressTest(SeriesProgressTestCase):

    def test_episodes_carry_their_progress(self):
        self.report(episode("901", "31684", positionSec=300, durationSec=2400))
        self.assertEqual(self.episodes(), {
            "901": {"positionSec": 300, "durationSec": 2400, "watched": False, "updatedAt": T0},
            "902": None})

    def test_an_unfinished_episode_is_its_own_up_next(self):
        self.assertIsNone(self.upNext())
        self.report(episode("902", "31684", positionSec=300, durationSec=2400))
        self.assertEqual(self.upNext(), {"seasonId": "31684", "seasonNumber": 1, "episodeId": "902",
                                         "episodeNumber": 2, "name": "Two", "positionSec": 300,
                                         "durationSec": 2400})

    def test_up_next_moves_to_the_next_episode_once_one_is_watched(self):
        self.report(episode("901", "31684", positionSec=2200, durationSec=2400))
        self.assertEqual(self.upNext(), {"seasonId": "31684", "seasonNumber": 1, "episodeId": "902",
                                         "episodeNumber": 2, "name": "Two", "positionSec": None,
                                         "durationSec": None})
        self.assertEqual(self.requests, [])

    def test_up_next_crosses_into_the_next_season_fetching_it_once(self):
        self.report(episode("902", "31684", watched=True))
        self.assertEqual(self.upNext(), {"seasonId": "31685", "seasonNumber": 2, "episodeId": "911",
                                         "episodeNumber": 1, "name": "Eleven", "positionSec": None,
                                         "durationSec": None})
        self.assertEqual(self.requests, [{"movie_id": "77", "season_id": "31685"}])
        self.report(episode("902", "31684", positionSec=2400, durationSec=2400))  # the end, after 90%
        self.assertEqual(len(self.requests), 1)

    def test_up_next_is_null_after_the_last_episode(self):
        self.report(episode("912", "31685", watched=True))
        self.assertIsNone(self.upNext())

    def test_the_latest_touched_episode_wins_even_out_of_order(self):
        self.report(episode("912", "31685", positionSec=600, durationSec=2400))
        self.now += 10
        self.report(episode("901", "31684", positionSec=100, durationSec=2400))
        self.assertEqual(self.upNext()["episodeId"], "901")
        self.now += 10
        self.report(episode("912", "31685", watched=False))
        self.assertEqual(self.upNext()["episodeId"], "912")

    def test_series_list_items_carry_up_next(self):
        self.report(episode("901", "31684", positionSec=300, durationSec=2400))
        items = {i["id"]: i for i in self.fetch("/api/ondemand/items")["items"]}
        self.assertEqual(items["77"]["upNext"]["episodeId"], "901")

    def test_unknown_episodes_and_seasons_are_not_found(self):
        for body in (episode("999", "31684"), episode("901", "99"), episode("901", "31685"),
                     dict(episode("901", "31684"), seriesId="5"),       # a Movie, not a Series
                     dict(episode("901", "31684"), seriesId="404")):
            response = self.report(dict(body, watched=True), status=404)
            self.assertEqual(response.get_json()["code"], "not_found", body)
        self.assertIsNone(self.upNext())

    def test_an_episode_of_a_season_not_opened_yet_is_looked_up(self):
        self.report(episode("912", "31685", positionSec=300, durationSec=2400))
        self.assertEqual(self.upNext()["name"], "Twelve")


class ContinueWatchingTest(SeriesProgressTestCase):
    def continued(self):
        return [(i["id"], i.get("progress", i.get("upNext"))["positionSec"])
                for i in self.fetch("/api/ondemand/continue")["items"]]

    def play(self, body):
        self.now += 60
        self.report(body)

    def test_movies_with_a_resume_point_and_series_with_up_next_most_recent_first(self):
        self.play({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.play(episode("901", "31684", positionSec=300, durationSec=2400))
        self.play({"portal": "p1", "id": "6", "positionSec": 700, "durationSec": 6000})
        self.assertEqual(self.continued(), [("6", 700), ("77", 300), ("5", 600)])
        self.play({"portal": "p1", "id": "5", "positionSec": 660, "durationSec": 6000})
        self.assertEqual(self.continued(), [("5", 660), ("6", 700), ("77", 300)])

    def test_an_entry_is_a_list_item_plus_its_progress_fields(self):
        self.play({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.play(episode("901", "31684", watched=True))
        series, film = self.fetch("/api/ondemand/continue")["items"]
        self.assertEqual(film, {
            "portal": "p1", "portalName": "First", "id": "5", "kind": "movie", "name": "Heat", "year": 2020,
            "rating": 6.5, "added": "2026-10-01 10:00:00", "poster": "/api/ondemand/poster/p1/5",
            "progress": {"positionSec": 600, "durationSec": 6000, "watched": False, "updatedAt": T0 + 60}})
        self.assertEqual((series["name"], series["kind"], series["upNext"]["episodeId"]), ("Show", "series", "902"))
        self.assertNotIn("progress", series)

    def test_watched_movies_and_finished_series_leave_it(self):
        self.play({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.play(episode("912", "31685", positionSec=300, durationSec=2400))
        self.play({"portal": "p1", "id": "5", "positionSec": 6000, "durationSec": 6000})
        self.play(episode("912", "31685", positionSec=2300, durationSec=2400))
        self.assertEqual(self.continued(), [])

    def test_at_most_20(self):
        self.fill("p2", [movie(100 + n, "Film {}".format(n), "2026-10-01 10:00:00") for n in range(25)])
        for n in range(25):
            self.play({"portal": "p2", "id": str(100 + n), "positionSec": 600, "durationSec": 6000})
        self.assertEqual([id for id, _ in self.continued()], [str(124 - n) for n in range(20)])

    def test_hidden_vanished_and_switched_off_items_are_skipped_but_kept(self):
        self.fill("p2", [movie(50, "Elsewhere", "2026-10-01 10:00:00")])
        for body in ({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000},
                     {"portal": "p1", "id": "6", "positionSec": 600, "durationSec": 6000},
                     {"portal": "p2", "id": "50", "positionSec": 600, "durationSec": 6000},
                     episode("901", "31684", positionSec=300, durationSec=2400)):
            self.play(body)
        self.app.getHiddenOnDemand().append("action")       # 5, 6 and 77 are in Action
        self.app.getPortals()["p2"]["enabled"] = "false"
        self.assertEqual(self.continued(), [])
        self.app.getHiddenOnDemand().clear()
        self.app.getPortals()["p2"]["enabled"] = "true"
        self.index.keepOnly("p1", {"5", "77"})              # a full crawl no longer finds 6
        self.assertEqual(self.continued(), [("77", 300), ("50", 600), ("5", 600)])
        self.index.addItems("p1", [movie(6, "Ronin", "2026-10-02 10:00:00")])  # and 6 comes back
        self.assertEqual(self.continued()[2], ("6", 600))

    def test_a_switched_off_account_keeps_its_rows(self):
        self.play({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        account = self.app.accounts.findAccount(self.app.getAccounts(), "viewer")
        account["on demand"] = False
        self.assertEqual(self.get("/api/ondemand/continue", "viewer").status_code, 404)
        account["on demand"] = True
        self.assertEqual(self.continued(), [("5", 600)])


class DeletionTest(SeriesProgressTestCase):
    def operator(self):
        settings = self.app.getSettings()
        return basic(settings["username"], settings["password"])

    def test_deleting_an_account_deletes_its_rows(self):
        self.addAccount("other", onDemand=True)
        for username in ("viewer", "other"):
            self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000}, username)
            self.report(episode("901", "31684", positionSec=300, durationSec=2400), username)
        self.client.post("/accounts/delete", headers=self.operator(), data={"username": "viewer"})
        self.addAccount("viewer", onDemand=True)  # the username again, starting clean
        self.assertIsNone(self.movieProgress())
        self.assertIsNone(self.upNext())
        self.assertEqual(self.fetch("/api/ondemand/continue")["items"], [])
        self.assertEqual(len(self.fetch("/api/ondemand/continue", "other")["items"]), 2)

    def test_deleting_a_portal_deletes_its_rows(self):
        self.fill("p2", [movie(50, "Elsewhere", "2026-10-01 10:00:00")])
        self.report({"portal": "p2", "id": "50", "positionSec": 600, "durationSec": 6000})
        self.report({"portal": "p1", "id": "5", "positionSec": 600, "durationSec": 6000})
        self.report(episode("901", "31684", positionSec=300, durationSec=2400))
        self.client.post("/portal/remove", headers=self.operator(), data={"deleteId": "p1"})
        self.assertEqual([i["id"] for i in self.fetch("/api/ondemand/continue")["items"]], ["50"])
        progress = self.app.onDemandProgress()
        self.assertEqual(progress.movies("viewer", [("p1", "5")]), {})
        self.assertEqual(progress.upNext("viewer", [("p1", "77")]), {})


class ProgressRequestTest(ProgressTestCase):
    def test_malformed_reports_are_bad_requests(self):
        for body in (None, [], {"portal": "p1", "id": "5"},                        # neither
                     {"portal": "p1", "id": "5", "positionSec": 600, "watched": True},  # both
                     {"portal": "p1", "positionSec": 600},                        # no item
                     {"id": "5", "positionSec": 600},                             # no portal
                     {"portal": "p1", "id": "5", "seriesId": "77", "seasonId": "1", "episodeId": "2",
                      "positionSec": 600},                                        # Movie and Episode
                     {"portal": "p1", "seriesId": "77", "seasonId": "1", "positionSec": 600},
                     {"portal": "p1", "id": "5", "positionSec": "600"},
                     {"portal": "p1", "id": "5", "positionSec": -1},
                     {"portal": "p1", "id": "5", "positionSec": 600, "durationSec": -5},
                     {"portal": "p1", "id": "5", "watched": "yes"}):
            response = self.report(body, status=400)
            self.assertEqual(response.get_json()["code"], "bad_request", body)

    def test_unknown_hidden_and_switched_off_items_are_not_found(self):
        self.app.getHiddenOnDemand().append("action")
        for body in ({"portal": "p1", "id": "404"}, {"portal": "nope", "id": "5"},
                     {"portal": "p3", "id": "9"},                                 # its portal is off
                     {"portal": "p1", "id": "77"},                                # a Series, not a Movie
                     {"portal": "p1", "id": "5"}):                                # hidden
            response = self.report(dict(body, positionSec=600, durationSec=6000), status=404)
            self.assertEqual(response.get_json()["code"], "not_found", body)
        self.app.getHiddenOnDemand().clear()
        self.assertIsNone(self.movieProgress())

    def test_the_gate_applies(self):
        self.addAccount("off", onDemand=False)
        response = self.report({"portal": "p1", "id": "5", "watched": True}, username="off", status=404)
        self.assertEqual(response.get_json()["code"], "on_demand_off")
        response = self.get("/api/ondemand/continue", "off")
        self.assertEqual((response.status_code, response.get_json()["code"]), (404, "on_demand_off"))


if __name__ == "__main__":
    unittest.main()
