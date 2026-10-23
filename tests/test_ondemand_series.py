"""A Series' Seasons and a Season's Episodes: fetched from the portal when opened, cached
in the index for about 6 h, the stale copy served when the portal fails (ADR 0003), for
each of the three Series shapes (research 01)."""
import base64
import json
import os
import tempfile
import unittest

import ondemand

HOUR = 3600
T0 = 1_800_000_000


def infomirSeries(id, name="Show"):
    """Shape 2: an Infomir 5.x Series row of the type=vod listing."""
    return {"id": str(id), "name": name, "o_name": name, "added": "2026-10-01 10:00:00",
            "category_id": "10", "is_series": "1", "series": [], "has_files": "18",
            "cmd": "/media/{}.mpg".format(id)}


def infomirSeason(id, number, name="", count=0):
    return {"id": str(id), "video_id": "77", "season_number": str(number), "season_name": name,
            "season_original_name": name, "season_series": str(count),
            "name": "Season {}. Show S{:02d}".format(number, number), "is_season": True}


def infomirEpisode(id, season, number, name=""):
    return {"id": str(id), "season_id": str(season), "series_number": str(number),
            "series_name": name, "series_original_name": name, "series_files": "1",
            "name": "S01 E{:02d}  |  {}".format(number, name), "is_episode": True}


class FakeCatalogue:
    """A portal's Series drill-down: get_ordered_list pages keyed by (source, ids)."""

    def __init__(self, pageSize=14):
        self.pageSize = pageSize
        self.lists = {}  # {(source, sorted params): [rows]}
        self.calls = []
        self.failing = False

    def serve(self, rows, source="vod", **params):
        self.lists[(source, tuple(sorted(params.items())))] = rows

    def list(self, portal, params, p, source="vod"):
        self.calls.append((portal, source, dict(params), p))
        if self.failing:
            return None
        rows = self.lists.get((source, tuple(sorted(params.items()))), [])
        start = (p - 1) * self.pageSize
        return {"total": len(rows), "pageSize": self.pageSize, "items": rows[start:start + self.pageSize]}


class SeriesTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.index = ondemand.Index(os.path.join(folder.name, "ondemand.sqlite"))
        self.addCleanup(self.index.close)
        self.catalogue = FakeCatalogue()
        self.now = T0
        self.series = ondemand.SeriesCache(self.index, self.catalogue, clock=lambda: self.now)


class InfomirShapeTest(SeriesTestCase):
    """Shape 2, the user's portal: Seasons then Episodes, each listed newest first."""

    def setUp(self):
        super().setUp()
        self.index.addItems("p1", [infomirSeries(77)])
        self.catalogue.serve([infomirSeason(31685, 2, "Second", 4), infomirSeason(31684, 1, "", 14)],
                             movie_id="77")

    def test_seasons_come_in_ascending_order_with_their_numbers_names_and_episode_counts(self):
        self.assertEqual(self.series.seasons("p1", "77"), [
            {"id": "31684", "number": 1, "name": None, "episodeCount": 14},
            {"id": "31685", "number": 2, "name": "Second", "episodeCount": 4},
        ])
        self.assertEqual(self.catalogue.calls, [("p1", "vod", {"movie_id": "77"}, 1)])

    def test_episodes_come_in_ascending_order_with_names_and_what_playing_them_takes(self):
        self.catalogue.serve([infomirEpisode(902, 31685, 2, "Two"), infomirEpisode(901, 31685, 1, "")],
                             movie_id="77", season_id="31685")
        self.assertEqual(self.series.episodes("p1", "77", "31685"), [
            {"id": "901", "seasonId": "31685", "number": 1, "name": None,
             "play": {"movie_id": "77", "season_id": "31685", "episode_id": "901"}},
            {"id": "902", "seasonId": "31685", "number": 2, "name": "Two",
             "play": {"movie_id": "77", "season_id": "31685", "episode_id": "902"}},
        ])

    def test_a_long_season_is_read_page_by_page(self):
        self.catalogue.serve([infomirEpisode(1000 + n, 31684, n) for n in range(30, 0, -1)],
                             movie_id="77", season_id="31684")
        episodes = self.series.episodes("p1", "77", "31684")
        self.assertEqual([e["number"] for e in episodes], list(range(1, 31)))
        self.assertEqual([c[3] for c in self.catalogue.calls if "season_id" in c[2]], [1, 2, 3])

    def test_a_season_the_series_does_not_have_is_none(self):
        self.assertIsNone(self.series.episodes("p1", "77", "999"))

    def test_a_series_with_no_seasons_has_an_empty_list(self):
        self.catalogue.serve([], movie_id="77")
        self.assertEqual(self.series.seasons("p1", "77"), [])

    def test_a_movie_or_an_unknown_item_has_no_seasons(self):
        self.index.addItems("p1", [dict(infomirSeries(5), is_series="0", has_files="0")])
        self.assertIsNone(self.series.seasons("p1", "5"))
        self.assertIsNone(self.series.seasons("p1", "404"))
        self.assertIsNone(self.series.episodes("p1", "5", "1"))
        self.assertEqual(self.catalogue.calls, [])


class CacheTest(SeriesTestCase):
    """Seasons and Episodes are kept about 6 h; a failing portal gets the stale copy."""

    def setUp(self):
        super().setUp()
        self.index.addItems("p1", [infomirSeries(77)])
        self.catalogue.serve([infomirSeason(11, 1, "", 2)], movie_id="77")
        self.catalogue.serve([infomirEpisode(101, 11, 1, "Pilot")], movie_id="77", season_id="11")

    def asks(self):
        count = len(self.catalogue.calls)
        self.catalogue.calls.clear()
        return count

    def test_seasons_and_episodes_are_served_from_the_index_for_about_6_hours(self):
        self.series.seasons("p1", "77")
        self.series.episodes("p1", "77", "11")
        self.assertEqual(self.asks(), 2)
        self.now = T0 + 6 * HOUR - 1
        self.series.seasons("p1", "77")
        self.series.episodes("p1", "77", "11")
        self.assertEqual(self.asks(), 0)

    def test_after_6_hours_the_portal_is_asked_again_and_its_answer_replaces_the_copy(self):
        self.series.episodes("p1", "77", "11")
        self.catalogue.serve([infomirSeason(11, 1, "", 3), infomirSeason(12, 2, "", 1)], movie_id="77")
        self.catalogue.serve([infomirEpisode(101, 11, 1, "Pilot"), infomirEpisode(102, 11, 2, "Next")],
                             movie_id="77", season_id="11")
        self.asks()
        self.now = T0 + 6 * HOUR
        self.assertEqual([s["id"] for s in self.series.seasons("p1", "77")], ["11", "12"])
        self.assertEqual([e["name"] for e in self.series.episodes("p1", "77", "11")], ["Pilot", "Next"])
        self.assertEqual(self.asks(), 2)

    def test_a_failing_portal_gets_the_stale_copy(self):
        before = (self.series.seasons("p1", "77"), self.series.episodes("p1", "77", "11"))
        self.catalogue.failing = True
        self.now = T0 + 24 * HOUR
        self.assertEqual((self.series.seasons("p1", "77"), self.series.episodes("p1", "77", "11")), before)
        self.assertEqual(self.asks(), 4)  # each was tried again
        # The portal is asked again next time, not only after another 6 h.
        self.series.seasons("p1", "77")
        self.assertEqual(self.asks(), 1)

    def test_a_failing_portal_with_no_copy_is_a_portal_error(self):
        self.catalogue.failing = True
        with self.assertRaises(ondemand.PortalError):
            self.series.seasons("p1", "77")
        self.catalogue.failing = False
        self.series.seasons("p1", "77")
        self.catalogue.failing = True
        with self.assertRaises(ondemand.PortalError):
            self.series.episodes("p1", "77", "11")

    def test_a_season_gone_from_the_portal_takes_its_episodes_with_it(self):
        self.series.episodes("p1", "77", "11")
        self.catalogue.serve([infomirSeason(12, 2, "", 1)], movie_id="77")
        self.now = T0 + 7 * HOUR
        self.series.seasons("p1", "77")
        self.assertIsNone(self.index.fetchedAt("p1", "77", "11"))
        self.assertEqual(self.index.episodeList("p1", "77", "11"), [])

    def test_deleting_the_portal_drops_its_seasons_and_episodes(self):
        self.series.episodes("p1", "77", "11")
        self.index.purge("p1")
        self.assertEqual(self.index.seasonList("p1", "77"), [])
        self.assertEqual(self.index.episodeList("p1", "77", "11"), [])
        self.assertIsNone(self.index.fetchedAt("p1", "77"))


class LegacyShapeTest(SeriesTestCase):
    """Shape 1: a type=vod item with an array of Episode numbers and no Seasons."""

    def setUp(self):
        super().setUp()
        self.index.addItems("p1", [{"id": "40", "name": "Old show", "added": "2020-01-01 00:00:00",
                                    "category_id": "10", "is_series": "0", "series": [3, 1, 2],
                                    "has_files": "0", "cmd": "/media/40.mpg"}])

    def test_it_is_a_series_of_one_season_whose_episodes_play_the_item_cmd(self):
        self.assertEqual(self.index.item("p1", "40")["kind"], "series")
        self.assertEqual(self.series.seasons("p1", "40"),
                         [{"id": "1", "number": 1, "name": None, "episodeCount": 3}])
        self.assertEqual(self.series.episodes("p1", "40", "1"), [
            {"id": str(n), "seasonId": "1", "number": n, "name": None,
             "play": {"cmd": "/media/40.mpg", "series": n}} for n in (1, 2, 3)
        ])
        self.assertEqual(self.catalogue.calls, [])


def xtreamCmd(series, season):
    return base64.b64encode(json.dumps(
        {"series_id": series, "season_num": season, "type": "series"}).encode()).decode()


class XtreamShapeTest(SeriesTestCase):
    """Shape 3: type=series lists one row per Season; Episodes are only positions."""

    def setUp(self):
        super().setUp()
        self.index.addItems("p1", [{"id": "7", "name": "Panel show", "added": "2026-01-01 00:00:00",
                                    "category_id": "3", "is_series": 1, "series": [], "cmd": ""}],
                            source="series")

    def test_seasons_are_keyed_by_number_and_episodes_play_the_season_cmd(self):
        # XC_VM gives every Season row the Series id; the number is in the cmd.
        self.catalogue.serve([
            {"id": "7", "name": "Season 2", "series": [1, 2], "cmd": xtreamCmd(7, 2)},
            {"id": "7", "name": "Specials", "series": [1], "cmd": xtreamCmd(7, 0)},
            {"id": "7", "name": "Season 1", "series": [1, 2, 3], "cmd": xtreamCmd(7, 1)},
        ], source="series", movie_id="7")
        self.assertEqual(self.series.seasons("p1", "series:7"), [
            {"id": "0", "number": 0, "name": "Specials", "episodeCount": 1},
            {"id": "1", "number": 1, "name": "Season 1", "episodeCount": 3},
            {"id": "2", "number": 2, "name": "Season 2", "episodeCount": 2},
        ])
        self.assertEqual(self.series.episodes("p1", "series:7", "2"), [
            {"id": str(n), "seasonId": "2", "number": n, "name": None,
             "play": {"cmd": xtreamCmd(7, 2), "series": n}} for n in (1, 2)
        ])
        self.assertEqual(self.catalogue.calls, [("p1", "series", {"movie_id": "7"}, 1)])

    def test_other_panels_number_seasons_in_the_id_or_the_name(self):
        self.catalogue.serve([
            {"id": "season3", "name": "Third", "series": [1], "cmd": "/media/7:3.mpg"},
            {"id": "7:4", "name": "Fourth", "series": [1], "cmd": "/media/7:4.mpg"},
            {"id": "x", "name": "Season 5", "series": [1], "cmd": ""},
        ], source="series", movie_id="7")
        self.assertEqual([s["number"] for s in self.series.seasons("p1", "series:7")], [3, 4, 5])

    def test_a_page_repeated_by_the_paging_bug_ends_the_list(self):
        self.catalogue.pageSize = 1
        rows = [{"id": "7", "name": "Season 1", "series": [1], "cmd": xtreamCmd(7, 1)}]
        self.catalogue.serve(rows, source="series", movie_id="7")
        self.catalogue.list = lambda portal, params, p, source="vod": {
            "total": 3, "pageSize": 1, "items": rows}
        self.assertEqual([s["number"] for s in self.series.seasons("p1", "series:7")], [1])


if __name__ == "__main__":
    unittest.main()
