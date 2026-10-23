"""Browse, search, Movie detail and posters: /api/ondemand/items, /item and /poster,
answered from the On Demand index (ADR 0003, the viewer On Demand API contract)."""
import threading
import time
import unittest
from unittest import mock

from tests.support import loadApp, portalConfig
from tests.test_app_ondemand import OnDemandTestCase, onDemandConfig

URL1 = "http://portal.test/stalker_portal/server/load.php"
URL2 = "http://other.test/c/"
OFF_URL = "http://off.test/stalker_portal/server/load.php"


def movie(id, name, added, cat0="10", cat1="0", cat2="0", **fields):
    row = {"id": str(id), "name": name, "o_name": name, "year": "2020", "added": added,
           "rating_kinopoisk": "6.5", "category_id": cat0, "category_id_1": cat1,
           "category_id_2": cat2, "is_series": 0,
           "screenshot_uri": "/stalker_portal/screenshots/1/{}.jpg".format(id)}
    row.update(fields)
    return row


class BrowseTestCase(OnDemandTestCase):
    """Two enabled portals and one switched off, their index filled directly."""

    def setUp(self):
        self.app = loadApp(self, onDemandConfig(portals={
            "p1": portalConfig(name="First", url=URL1),
            "p2": portalConfig(name="Second", url=URL2),
            "p3": portalConfig(name="Switched off", url=OFF_URL, enabled="false"),
        }))
        self.client = self.app.app.test_client()
        self.app.getSettings()["enable security"] = "true"
        self.addAccount("viewer", onDemand=True)
        self.index = self.app.onDemandIndex()
        self.addCleanup(self.index.close)

    def fill(self, portal, items, categories=({"id": "10", "title": "Action"},)):
        self.index.setCategories(portal, list(categories))
        self.index.addItems(portal, items)
        self.index.setStatus(portal, "ready", lastRefresh=1)

    def items(self, query="", status=200):
        response = self.get("/api/ondemand/items" + query, "viewer")
        self.assertEqual(response.status_code, status, response.get_json())
        return response.get_json()

    def names(self, query=""):
        return [i["name"] for i in self.items(query)["items"]]


class PagingTest(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [movie(i, "Film {}".format(i), "2026-10-01 10:{:02d}:00".format(i))
                         for i in range(70)])

    def test_a_page_defaults_to_60_newest_first_with_an_exact_total(self):
        body = self.items()
        self.assertEqual(body["total"], 70)
        self.assertEqual(len(body["items"]), 60)
        self.assertEqual(body["items"][0]["name"], "Film 69")
        self.assertEqual(body["items"][59]["name"], "Film 10")

    def test_offset_and_limit_page_through(self):
        body = self.items("?offset=60&limit=20")
        self.assertEqual(body["total"], 70)
        self.assertEqual([i["name"] for i in body["items"]],
                         ["Film {}".format(i) for i in range(9, -1, -1)])

    def test_limit_is_capped_at_200(self):
        self.fill("p2", [movie(i, "More {}".format(i), "2025-01-01 00:00:00") for i in range(200)])
        body = self.items("?limit=500")
        self.assertEqual(body["total"], 270)
        self.assertEqual(len(body["items"]), 200)

    def test_malformed_paging_is_a_bad_request(self):
        for query in ("?offset=x", "?limit=", "?limit=0", "?offset=-1"):
            self.assertEqual(self.items(query, status=400)["code"], "bad_request", query)


class ListItemTest(BrowseTestCase):
    def test_a_list_item_has_the_contract_fields_and_a_proxied_poster(self):
        self.fill("p1", [movie(5, "Heat", "2026-10-01 10:00:00", year="1995", rating_kinopoisk="8.3",
                               description="Long", actors="Somebody")])
        self.fill("p2", [movie(6, "Show", "2026-09-01 10:00:00", is_series="1")])
        self.assertEqual(self.items()["items"], [
            {"portal": "p1", "portalName": "First", "id": "5", "kind": "movie", "name": "Heat",
             "year": 1995, "poster": "/api/ondemand/poster/p1/5", "rating": 8.3,
             "added": "2026-10-01 10:00:00", "progress": None},
            {"portal": "p2", "portalName": "Second", "id": "6", "kind": "series", "name": "Show",
             "year": 2020, "poster": "/api/ondemand/poster/p2/6", "rating": 6.5,
             "added": "2026-09-01 10:00:00", "upNext": None},
        ])

    def test_placeholders_read_null(self):
        self.fill("p1", [
            movie(1, "No cover", "2026-10-04 00:00:00", screenshot_uri=False, year="N/A",
                  rating_kinopoisk="0"),
            movie(2, "Empty cover", "2026-10-03 00:00:00", screenshot_uri="", year="-",
                  rating_kinopoisk="N/a"),
            movie(3, "Dash cover", "2026-10-02 00:00:00", screenshot_uri="-", year="",
                  rating_kinopoisk="-"),
        ])
        for item in self.items()["items"]:
            self.assertEqual((item["poster"], item["year"], item["rating"]), (None, None, None),
                             item["name"])


class SortTest(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [
            movie(1, "banana", "2026-10-03 00:00:00", year="1999", rating_kinopoisk="8.1"),
            movie(2, "Apple", "2026-10-01 00:00:00", year="2024", rating_kinopoisk="0"),
            movie(3, "cherry", "2026-10-04 00:00:00", year="N/A", rating_kinopoisk="5.0"),
        ])
        self.fill("p2", [movie(1, "Date", "2026-10-02 00:00:00", year="2024",
                               rating_kinopoisk="9.4")])

    def test_recently_added_is_the_default(self):
        self.assertEqual(self.names(), ["cherry", "banana", "Date", "Apple"])
        self.assertEqual(self.names("?sort=added"), ["cherry", "banana", "Date", "Apple"])

    def test_name_sorts_a_to_z_ignoring_case(self):
        self.assertEqual(self.names("?sort=name"), ["Apple", "banana", "cherry", "Date"])

    def test_year_sorts_newest_first_then_recently_added_and_unknown_years_last(self):
        self.assertEqual(self.names("?sort=year"), ["Date", "Apple", "banana", "cherry"])

    def test_rating_sorts_highest_first_and_unrated_last(self):
        self.assertEqual(self.names("?sort=rating"), ["Date", "banana", "cherry", "Apple"])

    def test_an_unknown_sort_is_a_bad_request(self):
        self.assertEqual(self.items("?sort=random", status=400)["code"], "bad_request")


class SearchTest(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [
            movie(1, "The Dark Knight", "2026-10-01 00:00:00", actors="Christian Bale"),
            movie(2, "Amélie", "2026-10-02 00:00:00", o_name="Le Fabuleux Destin d'Amélie Poulain"),
            movie(3, "Knives Out", "2026-10-03 00:00:00", director="Rian Johnson"),
            movie(4, "Dark Waters", "2026-10-04 00:00:00"),
        ])

    def test_each_word_matches_as_a_prefix_ignoring_case(self):
        self.assertEqual(self.names("?q=dar+KNI"), ["The Dark Knight"])
        self.assertEqual(self.names("?q=kni"), ["Knives Out", "The Dark Knight"])

    def test_accents_are_folded_both_ways(self):
        self.assertEqual(self.names("?q=amelie"), ["Amélie"])
        self.assertEqual(self.names("?q=d%C3%A0rk+w%C3%A0"), ["Dark Waters"])

    def test_the_original_name_is_searched(self):
        self.assertEqual(self.names("?q=fabuleux"), ["Amélie"])

    def test_actors_and_directors_are_not_searched(self):
        self.assertEqual(self.items("?q=bale")["total"], 0)
        self.assertEqual(self.items("?q=rian")["total"], 0)

    def test_a_search_under_two_characters_is_a_bad_request(self):
        for query in ("?q=a", "?q=+a+", "?q="):
            self.assertEqual(self.items(query, status=400)["code"], "bad_request", query)

    def test_punctuation_alone_finds_nothing(self):
        self.assertEqual(self.items('?q=%22*%22()')["items"], [])

    def test_results_rank_by_relevance_then_recently_added(self):
        self.fill("p2", [movie(1, "Dark", "2026-09-01 00:00:00"),
                         movie(2, "Dark Places", "2026-10-05 00:00:00"),
                         movie(3, "Dark Matter", "2026-09-02 00:00:00")])
        # The closest (shortest) title first; equally good ones newest first.
        self.assertEqual(self.names("?q=dark"),
                         ["Dark", "Dark Places", "Dark Waters", "Dark Matter", "The Dark Knight"])

    def test_a_sort_applies_to_a_search_only_when_sent(self):
        self.fill("p2", [movie(1, "Dark", "2026-09-01 00:00:00")])
        self.assertEqual(self.names("?q=dark&sort=name"), ["Dark", "Dark Waters", "The Dark Knight"])
        self.assertEqual(self.names("?q=dark&sort=added"), ["Dark Waters", "The Dark Knight", "Dark"])

    def test_a_search_combines_with_a_category_and_pages(self):
        self.fill("p2", [movie(1, "Dark comedy", "2026-09-01 00:00:00", "7"),
                         movie(2, "Darker comedy", "2026-09-02 00:00:00", "7")],
                  [{"id": "7", "title": "Comedy"}])
        body = self.items("?q=dark&category=comedy&limit=1&offset=1")
        self.assertEqual(body["total"], 2)
        self.assertEqual([i["name"] for i in body["items"]], ["Dark comedy"])


class DetailTest(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [
            movie(5, "Heat", "2026-10-01 10:00:00", "10", "0", "11", year="1995",
                  rating_kinopoisk="8.3", o_name="Heat (Director's Cut)",
                  description="A crew of thieves.", genres_str="Crime, Drama",
                  director="Someone", actors="A, B", country="USA", time="170",
                  rating_mpaa="R"),
            movie(6, "Bare", "2026-10-02 10:00:00", screenshot_uri=False, description="N/A",
                  genres_str="", director="-", actors="N/a", country=None, time="0",
                  rating_mpaa="N/A"),
        ], [{"id": "10", "title": "Action"}, {"id": "11", "title": "Crime  Films"}])

    def detail(self, portal, id, status=200):
        response = self.get("/api/ondemand/item/{}/{}".format(portal, id), "viewer")
        self.assertEqual(response.status_code, status, response.get_json())
        return response.get_json()

    def test_a_movie_detail_is_the_list_item_plus_its_facts(self):
        self.assertEqual(self.detail("p1", "5"), {
            "portal": "p1", "portalName": "First", "id": "5", "kind": "movie", "name": "Heat",
            "year": 1995, "poster": "/api/ondemand/poster/p1/5", "rating": 8.3,
            "added": "2026-10-01 10:00:00", "originalName": "Heat (Director's Cut)",
            "description": "A crew of thieves.", "genres": "Crime, Drama", "director": "Someone",
            "actors": "A, B", "country": "USA", "durationMin": 170, "ageRating": "R",
            "categories": ["action", "crime films"], "progress": None,
        })

    def test_placeholders_read_null_and_an_unchanged_original_name_is_left_out(self):
        body = self.detail("p1", "6")
        self.assertNotIn("originalName", body)
        for field in ("poster", "description", "genres", "director", "actors", "country",
                      "durationMin", "ageRating"):
            self.assertIsNone(body[field], field)
        self.assertEqual(body["categories"], ["action"])

    def test_an_unknown_item_is_not_found(self):
        self.assertEqual(self.detail("p1", "404", status=404)["code"], "not_found")
        self.assertEqual(self.detail("nope", "5", status=404)["code"], "not_found")

    def test_an_item_of_a_portal_switched_off_is_not_found(self):
        self.app.getPortals()["p1"]["enabled"] = "false"
        self.assertEqual(self.detail("p1", "5", status=404)["code"], "not_found")


class Upstream:
    """The portals' poster server, faked at requests.get (no network)."""

    def __init__(self, testCase, app, images=None, hold=None):
        self.images = images or {}  # {url: (status, bytes)}
        self.hold = hold            # an Event every fetch waits for, when set
        self.calls = []
        self.inFlight = 0
        self.most = 0
        self.changed = threading.Condition()
        patcher = mock.patch.object(app.requests, "get", side_effect=self.get)
        patcher.start()
        testCase.addCleanup(patcher.stop)

    def get(self, url, **kwargs):
        with self.changed:
            self.calls.append((url, kwargs))
            self.inFlight += 1
            self.most = max(self.most, self.inFlight)
            self.changed.notify_all()
        try:
            if self.hold is not None:
                self.hold.wait(5)
            status, body = self.images.get(url, (404, b"Not found"))
            return mock.Mock(status_code=status, content=body,
                             headers={"Content-Type": "image/jpeg" if status == 200 else "text/html"})
        finally:
            with self.changed:
                self.inFlight -= 1

    def waitFor(self, inFlight):
        with self.changed:
            self.changed.wait_for(lambda: self.inFlight == inFlight, 5)


class PosterTest(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [
            movie(i, "Film {}".format(i), "2026-10-01 00:00:00") for i in range(1, 9)
        ] + [movie(20, "No cover", "2026-10-01 00:00:00", screenshot_uri=False),
             movie(21, "Elsewhere", "2026-10-01 00:00:00",
                   screenshot_uri="https://images.test/w300/abc.jpg")])

    def poster(self, id, client=None):
        return (client or self.client).get("/api/ondemand/poster/p1/{}".format(id),
                                           headers=self.auth())

    def auth(self):
        from tests.test_api_lineup import basic
        return basic("viewer", "secret")

    def test_a_portal_relative_poster_is_fetched_from_the_portal_host_and_cached_a_week(self):
        upstream = Upstream(self, self.app, {
            "http://portal.test/stalker_portal/screenshots/1/5.jpg": (200, b"JPEG5")})
        response = self.poster(5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"JPEG5")
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")
        self.assertIn("max-age=604800", response.headers["Cache-Control"])
        self.assertEqual(upstream.calls[0][1]["timeout"], 5)

    def test_an_absolute_poster_is_fetched_as_it_is(self):
        Upstream(self, self.app, {"https://images.test/w300/abc.jpg": (200, b"JPEG")})
        self.assertEqual(self.poster(21).data, b"JPEG")

    def test_no_poster_an_unknown_item_or_an_upstream_404_is_not_found(self):
        upstream = Upstream(self, self.app)
        for id in (20, 99, 5):
            response = self.poster(id)
            self.assertEqual(response.status_code, 404, id)
            self.assertEqual(response.get_json()["code"], "not_found")
        self.assertEqual(len(upstream.calls), 1)  # only item 5 has a poster to fetch

    def test_an_upstream_failure_is_a_portal_error(self):
        Upstream(self, self.app, {
            "http://portal.test/stalker_portal/screenshots/1/5.jpg": (500, b"Oops")})
        self.assertEqual(self.poster(5).status_code, 502)
        self.app.requests.get.side_effect = OSError("timed out")
        self.assertEqual(self.poster(5).get_json()["code"], "portal_error")

    def fetchInThreads(self, ids):
        statuses = []

        def fetch(id):
            statuses.append(self.poster(id, self.app.app.test_client()).status_code)

        threads = [threading.Thread(target=fetch, args=(id,)) for id in ids]
        for thread in threads:
            thread.start()
        return threads, statuses

    def images(self):
        return {"http://portal.test/stalker_portal/screenshots/1/{}.jpg".format(i): (200, b"J")
                for i in range(1, 9)}

    def test_at_most_six_posters_are_fetched_at_once_and_the_rest_wait_their_turn(self):
        release = threading.Event()
        upstream = Upstream(self, self.app, self.images(), hold=release)
        threads, statuses = self.fetchInThreads(range(1, 9))
        upstream.waitFor(6)
        time.sleep(0.1)  # the other two are queued, not fetching
        self.assertEqual(upstream.inFlight, 6)
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(statuses, [200] * 8)
        self.assertEqual(upstream.most, 6)

    def test_a_poster_queued_over_the_wait_gets_504(self):
        self.app.ONDEMAND_POSTER_WAIT = 0.2
        release = threading.Event()
        upstream = Upstream(self, self.app, self.images(), hold=release)
        threads, statuses = self.fetchInThreads(range(1, 7))
        upstream.waitFor(6)
        started = time.monotonic()
        response = self.poster(7)
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.get_json(), {"error": "Too many posters at once, try again", "code": "timeout"})
        self.assertGreaterEqual(time.monotonic() - started, 0.2)
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(statuses, [200] * 6)


class AllTest(BrowseTestCase):
    def setUp(self):
        super().setUp()
        categories = [{"id": "10", "title": "Action"}, {"id": "11", "title": "Comedy"}]
        self.fill("p1", [movie(1, "Both", "2026-10-02 00:00:00", "10", "11", "10")], categories)
        self.fill("p2", [movie(1, "Elsewhere", "2026-10-01 00:00:00")])
        self.fill("p3", [movie(1, "Never", "2026-10-03 00:00:00")])

    def test_all_merges_enabled_portals_and_lists_an_item_once_whatever_its_categories(self):
        body = self.items()
        self.assertEqual(body["total"], 2)
        self.assertEqual([(i["portal"], i["portalName"], i["name"]) for i in body["items"]],
                         [("p1", "First", "Both"), ("p2", "Second", "Elsewhere")])

    def test_a_category_lists_its_items_from_every_portal_once_each(self):
        self.fill("p2", [movie(1, "Elsewhere", "2026-10-01 00:00:00", "7"),
                         movie(2, "Not funny", "2026-10-01 00:00:00", "8")],
                  [{"id": "7", "title": "comedy"}, {"id": "8", "title": "Drama"}])
        body = self.items("?category=comedy")
        self.assertEqual(body["total"], 2)
        self.assertEqual([i["name"] for i in body["items"]], ["Both", "Elsewhere"])
        self.assertEqual(self.names("?category=action"), ["Both"])

    def test_an_unknown_category_is_empty(self):
        self.assertEqual(self.items("?category=westerns"), {"items": [], "total": 0, "offset": 0, "limit": 60})

    def test_a_portal_switched_off_drops_out_at_once_and_keeps_its_rows(self):
        portals = self.app.getPortals()
        portals["p1"]["enabled"] = "false"
        self.assertEqual(self.names(), ["Elsewhere"])
        portals["p1"]["enabled"] = "true"
        self.assertEqual(self.names(), ["Both", "Elsewhere"])


if __name__ == "__main__":
    unittest.main()
