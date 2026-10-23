"""The On Demand index and its first crawl (ADR 0003), against a fake portal."""
import os
import tempfile
import threading
import unittest

import ondemand


def item(id, name, cat0, cat1="0", cat2="0", series=0, added="2026-10-01 10:00:00"):
    return {
        "id": str(id), "name": name, "o_name": name, "year": "2020", "added": added,
        "rating_kinopoisk": "7.1", "category_id": cat0, "category_id_1": cat1,
        "category_id_2": cat2, "is_series": series, "cmd": "/media/{}.mpg".format(id),
    }


class FakeCatalogue:
    """Portals as the crawler sees them: categories, then 14-ish item pages, newest first."""

    def __init__(self, portals, pageSize=2):
        self.portals_ = portals  # {portal: {"name", "categories", "items"}}
        self.pageSize = pageSize
        self.on = True
        self.calls = []
        self.failing = set()

    def portals(self):
        return {p: v["name"] for p, v in self.portals_.items()}

    def wanted(self):
        return self.on

    def categories(self, portal):
        self.calls.append((portal, "categories"))
        if portal in self.failing:
            return None
        return self.portals_[portal]["categories"]

    def page(self, portal, p):
        self.calls.append((portal, p))
        if portal in self.failing:
            return None
        items = self.portals_[portal]["items"]
        start = (p - 1) * self.pageSize
        return {"total": len(items), "pageSize": self.pageSize,
                "items": items[start:start + self.pageSize]}


ALL = {"id": "*", "title": "All", "alias": "*"}
COMING = {"id": "coming_soon", "title": "Coming soon", "alias": "coming_soon"}


def cat(id, title, censored=0):
    return {"id": id, "title": title, "alias": title.lower(), "censored": censored}


class IndexTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "ondemand.sqlite")
        self.index = ondemand.Index(self.path)
        self.addCleanup(self.index.close)
        self.sleeps = []

    def crawler(self, catalogue):
        return ondemand.Crawler(self.index, catalogue, sleep=self.sleeps.append)

    def counts(self, portals):
        return {c["name"]: c["count"] for c in self.index.categories(portals)}


class FirstCrawlTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        self.catalogue = FakeCatalogue({
            "p1": {
                "name": "One",
                "categories": [ALL, cat("10", "Action"), cat("11", "Kids")],
                "items": [item(i, "Film {}".format(i), "10") for i in range(5)],
            },
        })

    def test_every_page_is_indexed_and_the_portal_is_ready(self):
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.counts(["p1"]), {"Action": 5})
        status = self.index.status("p1")
        self.assertEqual(status["status"], "ready")
        self.assertIsNone(status["progress"])
        self.assertIsInstance(status["lastRefresh"], int)
        # Categories first, then pages 1..3 of 2 items, and no page past the end.
        self.assertEqual(self.catalogue.calls, [("p1", "categories"), ("p1", 1), ("p1", 2), ("p1", 3)])

    def test_requests_are_paced_at_one_a_second(self):
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.sleeps, [1.0] * 3)

    def test_a_portal_repeating_its_first_page_ends_the_crawl(self):
        # Some panels ignore p= and answer page 1 every time.
        self.catalogue.page = lambda portal, p: {
            "total": 100, "pageSize": 2, "items": [item(1, "A", "10"), item(2, "B", "10")]}
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.counts(["p1"]), {"Action": 2})
        self.assertEqual(self.index.status("p1")["status"], "ready")


class StatusTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        self.catalogue = FakeCatalogue({
            "p1": {"name": "One", "categories": [cat("10", "Action")],
                   "items": [item(i, "F{}".format(i), "10") for i in range(8)]},
            "p2": {"name": "Two", "categories": [cat("20", "Action")],
                   "items": [item(i, "G{}".format(i), "20") for i in range(2)]},
        })

    def test_a_portal_never_indexed_reads_failed(self):
        self.assertEqual(self.index.status("p1"), {"status": "failed", "progress": None, "lastRefresh": None})

    def test_indexing_shows_progress_and_what_is_indexed_so_far(self):
        seen = []
        page = self.catalogue.page

        def watch(portal, p):
            if portal == "p1":
                seen.append((self.index.status("p1")["progress"], self.index.status("p2")["status"],
                             self.counts(["p1"]).get("Action", 0)))
            return page(portal, p)

        self.catalogue.page = watch
        self.crawler(self.catalogue).crawl()
        # 4 pages of 2. A portal waiting its turn reads "indexing" too.
        self.assertEqual(seen, [(0, "indexing", 0), (25, "indexing", 2), (50, "indexing", 4), (75, "indexing", 6)])
        self.assertEqual(self.index.status("p2")["status"], "ready")

    def test_a_failed_first_crawl_reads_failed_and_the_next_portal_still_goes(self):
        self.catalogue.failing.add("p1")
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.index.status("p1")["status"], "failed")
        self.assertEqual(self.index.status("p2")["status"], "ready")

    def test_a_ready_portal_is_not_crawled_again(self):
        self.crawler(self.catalogue).crawl()
        self.catalogue.calls.clear()
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.catalogue.calls, [])

    def test_switching_every_account_off_pauses_the_crawl_and_keeps_the_index(self):
        page = self.catalogue.page

        def switchOffAfterTwo(portal, p):
            if p == 2:
                self.catalogue.on = False
            return page(portal, p)

        self.catalogue.page = switchOffAfterTwo
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.catalogue.calls, [("p1", "categories"), ("p1", 1), ("p1", 2)])
        self.assertEqual(self.counts(["p1"]), {"Action": 4})
        self.assertEqual(self.index.status("p1")["status"], "indexing")
        # Switched back on, it picks up again and finishes.
        self.catalogue.on = True
        self.catalogue.page = page
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.counts(["p1"]), {"Action": 8})
        self.assertEqual(self.index.status("p1")["status"], "ready")

    def test_nothing_is_crawled_while_every_account_is_off(self):
        self.catalogue.on = False
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.catalogue.calls, [])


class BackgroundTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        self.catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                               "items": [item(1, "A", "10")]}})

    def test_wake_crawls_in_one_background_thread(self):
        crawler = self.crawler(self.catalogue)
        thread = crawler.wake()
        self.assertIsInstance(thread, threading.Thread)
        thread.join(5)
        self.assertEqual(self.index.status("p1")["status"], "ready")

    def test_wake_does_nothing_while_every_account_is_off(self):
        self.catalogue.on = False
        self.assertIsNone(self.crawler(self.catalogue).wake())
        self.assertEqual(self.catalogue.calls, [])

    def test_waking_a_running_crawl_does_not_start_a_second(self):
        gate = threading.Event()
        categories = self.catalogue.categories

        def slow(portal):
            gate.wait(5)
            return categories(portal)

        self.catalogue.categories = slow
        crawler = self.crawler(self.catalogue)
        first = crawler.wake()
        self.assertIs(crawler.wake(), first)
        gate.set()
        first.join(5)
        self.assertEqual(self.index.status("p1")["status"], "ready")


class DisposableFileTest(IndexTestCase):
    def reopen(self):
        self.index.close()
        self.index = ondemand.Index(self.path)
        self.addCleanup(self.index.close)

    def test_the_index_survives_a_restart(self):
        catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                          "items": [item(1, "A", "10")]}})
        self.crawler(catalogue).crawl()
        self.reopen()
        self.assertEqual(self.counts(["p1"]), {"Action": 1})
        self.assertEqual(self.index.status("p1")["status"], "ready")

    def test_a_corrupt_file_is_recreated_empty(self):
        self.index.close()
        with open(self.path, "wb") as f:
            f.write(b"this is not a database" * 100)
        self.reopen()
        self.assertEqual(self.index.status("p1")["status"], "failed")
        self.assertEqual(self.index.categories(["p1"]), [])

    def test_a_file_from_another_schema_version_is_recreated(self):
        catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                          "items": [item(1, "A", "10")]}})
        self.crawler(catalogue).crawl()
        self.index.db.execute("PRAGMA user_version = 999")
        self.reopen()
        self.assertEqual(self.index.status("p1")["status"], "failed")

    def test_the_page_cache_is_capped_at_about_8_mb(self):
        self.assertEqual(self.index.db.execute("PRAGMA cache_size").fetchone()[0], -8192)


class SeriesTest(IndexTestCase):
    def test_series_flagged_in_the_movie_catalogue_are_series(self):
        catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Shows")], "items": [
            item(1, "A Movie", "10"),
            item(2, "A Series", "10", series=1),
            item(3, "Another", "10", series="1"),
            item(4, "Third", "10", series=True),
        ]}})
        self.crawler(catalogue).crawl()
        kinds = {id: self.index.item("p1", id)["kind"] for id in ("1", "2", "3", "4")}
        self.assertEqual(kinds, {"1": "movie", "2": "series", "3": "series", "4": "series"})


class MergedCategoriesTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        catalogue = FakeCatalogue({
            "p1": {"name": "One", "categories": [
                ALL, cat("10", "ENGLISH  Movies"), cat("11", "Kids"), cat("12", "Empty"), COMING,
            ], "items": [
                item(1, "A", "10"),
                item(2, "B", "10", "11"),        # second slot
                item(3, "C", "10", "0", "11"),   # third slot
                item(4, "D", "coming_soon"),
            ]},
            "p2": {"name": "Two", "categories": [cat("7", "english movies"), cat("8", "Docs")], "items": [
                item(1, "Same id, other portal", "7"),
                item(2, "E", "8", "7", "7"),     # the same category twice counts once
            ]},
        })
        self.crawler(catalogue).crawl()

    def test_same_named_categories_merge_and_items_count_in_every_slot(self):
        self.assertEqual(self.index.categories(["p1", "p2"]), [
            {"id": "docs", "name": "Docs", "count": 1},
            {"id": "english movies", "name": "ENGLISH  Movies", "count": 5},
            {"id": "kids", "name": "Kids", "count": 2},
        ])

    def test_the_name_comes_from_the_first_portal_listed(self):
        names = {c["id"]: c["name"] for c in self.index.categories(["p2", "p1"])}
        self.assertEqual(names["english movies"], "english movies")

    def test_only_the_portals_asked_for_are_counted(self):
        self.assertEqual(self.counts(["p2"]), {"english movies": 2, "Docs": 1})
        self.assertEqual(self.index.categories([]), [])

    def test_all_coming_soon_and_empty_categories_are_never_listed(self):
        ids = [c["id"] for c in self.index.categories(["p1", "p2"])]
        self.assertNotIn("all", ids)
        self.assertNotIn("coming soon", ids)
        self.assertNotIn("empty", ids)


if __name__ == "__main__":
    unittest.main()
