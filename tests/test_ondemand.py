"""The On Demand index, its crawls and refreshes (ADR 0003), against a fake portal and clock."""
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock

import ondemand


def item(id, name, cat0, cat1="0", cat2="0", series=0, added="2026-10-01 10:00:00"):
    return {
        "id": str(id), "name": name, "o_name": name, "year": "2020", "added": added,
        "rating_kinopoisk": "7.1", "category_id": cat0, "category_id_1": cat1,
        "category_id_2": cat2, "is_series": series, "cmd": "/media/{}.mpg".format(id),
    }


class FakeCatalogue:
    """Portals as the crawler sees them: categories, then 14-ish item pages, newest first.

    A portal with a "series" entry ({"categories", "items"}) is an Xtream-family portal
    that also answers type=series; one without answers type=series with None (Infomir).
    Type=vod calls are recorded as (portal, "categories") and (portal, p), type=series
    calls as (portal, "series", "categories") and (portal, "series", p).
    """

    def __init__(self, portals, pageSize=2):
        self.portals_ = portals  # {portal: {"name", "categories", "items"[, "series"]}}
        self.pageSize = pageSize
        self.on = True
        self.calls = []
        self.failing = set()

    def portals(self):
        return {p: v["name"] for p, v in self.portals_.items()}

    def wanted(self):
        return self.on

    def listing(self, portal, source):
        return self.portals_[portal] if source == "vod" else self.portals_[portal].get("series")

    def record(self, portal, source, what):
        self.calls.append((portal, what) if source == "vod" else (portal, source, what))

    def categories(self, portal, source="vod"):
        self.record(portal, source, "categories")
        if portal in self.failing or self.listing(portal, source) is None:
            return None
        return self.listing(portal, source)["categories"]

    def page(self, portal, p, source="vod"):
        self.record(portal, source, p)
        if portal in self.failing or self.listing(portal, source) is None:
            return None
        items = self.listing(portal, source)["items"]
        start = (p - 1) * self.pageSize
        return {"total": len(items), "pageSize": self.pageSize,
                "items": items[start:start + self.pageSize]}

    def pages(self, portal, source="vod"):
        """The page numbers asked of one portal's listing, in order."""
        want = 2 if source == "vod" else 3
        return [c[-1] for c in self.calls
                if c[0] == portal and len(c) == want and isinstance(c[-1], int)
                and (source == "vod" or c[1] == source)]


# Thursday 2026-10-15 14:00 local time: the injectable clock's start.
T0 = time.mktime((2026, 10, 15, 14, 0, 0, 0, 0, -1))
HOUR = 3600
DAY = 24 * HOUR

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
        self.now = T0

    def crawler(self, catalogue):
        return ondemand.Crawler(self.index, catalogue, sleep=self.sleeps.append, clock=lambda: self.now)

    def later(self, seconds):
        self.now += seconds

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
        # Categories first, then pages 1..3 of 2 items, and no page past the end. Then
        # type=series is asked for its categories: this portal doesn't answer (Infomir).
        self.assertEqual(self.catalogue.calls, [("p1", "categories"), ("p1", 1), ("p1", 2), ("p1", 3),
                                                ("p1", "series", "categories")])

    def test_requests_are_paced_at_one_a_second(self):
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.sleeps, [1.0] * 4)

    def test_a_portal_repeating_its_first_page_ends_the_crawl(self):
        # Some panels ignore p= and answer page 1 every time.
        self.catalogue.page = lambda portal, p, source="vod": {
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

        def watch(portal, p, source="vod"):
            if portal == "p1":
                seen.append((self.index.status("p1")["progress"], self.index.status("p2")["status"],
                             self.counts(["p1"]).get("Action", 0)))
            return page(portal, p, source)

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

        def switchOffAfterTwo(portal, p, source="vod"):
            if p == 2:
                self.catalogue.on = False
            return page(portal, p, source)

        self.catalogue.page = switchOffAfterTwo
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.catalogue.calls, [("p1", "categories"), ("p1", 1), ("p1", 2)])
        self.assertEqual(self.counts(["p1"]), {"Action": 4})
        self.assertEqual(self.index.status("p1")["status"], "indexing")
        # Switched back on, it picks up where it stopped (the last page again, in case new
        # items pushed the list down) and finishes.
        self.catalogue.on = True
        self.catalogue.page = page
        self.catalogue.calls.clear()
        self.crawler(self.catalogue).crawl()
        self.assertEqual(self.catalogue.pages("p1"), [2, 3, 4])
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

        def slow(portal, source="vod"):
            gate.wait(5)
            return categories(portal, source)

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

    def test_a_file_found_corrupt_while_crawling_is_recreated_and_crawled_again(self):
        catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                          "items": films(range(4))}})
        crawler = self.crawler(catalogue)
        crawler.crawl()
        self.later(2 * HOUR)
        with mock.patch.object(self.index, "addItems",
                               side_effect=sqlite3.DatabaseError("database disk image is malformed")):
            with self.assertLogs("STB-Proxy", "ERROR"):
                crawler.crawl()
        self.assertEqual(self.index.status("p1")["status"], "failed")
        self.assertEqual(self.index.categories(["p1"]), [])
        crawler.crawl()
        self.assertEqual(self.counts(["p1"]), {"Action": 4})
        self.assertEqual(self.index.status("p1")["status"], "ready")

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


def films(ids, cat0="10", added="2026-10-01 10:00:00"):
    return [item(i, "Film {}".format(i), cat0, added=added) for i in ids]


class IncrementalRefreshTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        # Newest first, as sortby=added lists them: 3 pages of 2.
        self.catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                               "items": films(range(6))}})
        self.crawler_ = self.crawler(self.catalogue)
        self.crawler_.crawl()
        self.catalogue.calls.clear()

    def test_nothing_is_pulled_before_two_hours(self):
        self.later(2 * HOUR - 60)
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.calls, [])

    def test_the_pull_stops_at_the_first_page_with_nothing_new(self):
        items = self.catalogue.portals_["p1"]["items"]
        items[:0] = films([100, 101, 102], added="2026-10-10 10:00:00")
        self.later(2 * HOUR)
        self.crawler_.crawl()
        # Page 1 is all new, page 2 has one new item, page 3 has nothing new: stop there.
        self.assertEqual(self.catalogue.pages("p1"), [1, 2, 3])
        self.assertEqual(self.counts(["p1"]), {"Action": 9})
        status = self.index.status("p1")
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["lastRefresh"], int(self.now))

    def test_categories_are_read_again_on_every_pull(self):
        self.catalogue.portals_["p1"]["categories"] = [cat("10", "Action films")]
        self.later(2 * HOUR)
        self.crawler_.crawl()
        self.assertIn(("p1", "categories"), self.catalogue.calls)
        self.assertEqual(self.counts(["p1"]), {"Action films": 6})

    def test_a_series_whose_added_moved_counts_as_changed(self):
        items = self.catalogue.portals_["p1"]["items"]
        # A new Episode moves a Series (item 5, on the last page) to the top.
        moved = items.pop(5)
        items[:0] = [dict(moved, added="2026-10-12 08:00:00", is_series=1), *films([100])]
        self.later(2 * HOUR)
        self.crawler_.crawl()
        # Page 1 holds the changed Series and a new film; page 2 has nothing new.
        self.assertEqual(self.catalogue.pages("p1"), [1, 2])
        self.assertEqual(self.index.item("p1", "5")["added"], "2026-10-12 08:00:00")

    def test_an_unchanged_first_page_ends_the_pull_at_once(self):
        self.later(2 * HOUR)
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.pages("p1"), [1])


def local(month, day, hour, minute=0):
    return time.mktime((2026, month, day, hour, minute, 0, 0, 0, -1))


class WeeklyRecrawlTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        self.catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                               "items": films(range(6))}})
        self.crawler_ = self.crawler(self.catalogue)
        self.crawler_.crawl()  # Thursday 15 October, 14:00
        # The portal drops two items, at the end of its list.
        del self.catalogue.portals_["p1"]["items"][4:]
        self.catalogue.calls.clear()

    def at(self, when):
        self.now = when
        self.crawler_.crawl()

    def test_the_week_out_pulls_are_incremental_and_keep_removed_items(self):
        self.at(local(10, 22, 3, 50))
        self.assertEqual(self.catalogue.pages("p1"), [1])
        self.assertEqual(self.counts(["p1"]), {"Action": 6})

    def test_about_04_00_a_week_on_a_full_crawl_drops_what_the_portal_no_longer_lists(self):
        self.at(local(10, 22, 4, 0))
        self.assertEqual(self.catalogue.pages("p1"), [1, 2])
        self.assertEqual(self.counts(["p1"]), {"Action": 4})
        self.assertIsNone(self.index.item("p1", "5"))
        self.assertEqual(self.index.status("p1")["status"], "ready")
        self.assertEqual(self.index.status("p1")["lastRefresh"], int(self.now))

    def test_the_next_full_crawl_is_a_week_later(self):
        self.at(local(10, 22, 4, 0))
        self.catalogue.calls.clear()
        self.at(local(10, 29, 3, 0))
        self.assertEqual(self.catalogue.pages("p1"), [1])
        self.catalogue.calls.clear()
        self.at(local(10, 29, 4, 5))
        self.assertEqual(self.catalogue.pages("p1"), [1, 2])

    def test_a_full_crawl_cut_short_drops_nothing(self):
        self.catalogue.failing.add("p1")
        self.at(local(10, 22, 4, 0))
        self.assertEqual(self.counts(["p1"]), {"Action": 6})


class StaleTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        self.catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                               "items": films(range(4))}})
        self.crawler_ = self.crawler(self.catalogue)

    def test_a_failed_refresh_keeps_the_index_and_reads_stale_with_the_last_good_time(self):
        self.crawler_.crawl()
        good = int(self.now)
        self.catalogue.failing.add("p1")
        self.later(2 * HOUR)
        self.crawler_.crawl()
        self.assertEqual(self.index.status("p1"), {"status": "stale", "progress": None, "lastRefresh": good})
        self.assertEqual(self.counts(["p1"]), {"Action": 4})

    def test_a_stale_portal_retries_after_five_minutes(self):
        self.crawler_.crawl()
        self.catalogue.failing.add("p1")
        self.later(2 * HOUR)
        self.crawler_.crawl()
        self.catalogue.failing.clear()
        self.catalogue.calls.clear()
        self.later(5 * 60 - 1)
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.calls, [])
        self.later(1)
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.pages("p1"), [1])
        self.assertEqual(self.index.status("p1")["status"], "ready")
        self.assertEqual(self.index.status("p1")["lastRefresh"], int(self.now))

    def test_a_failed_first_crawl_retries_after_five_minutes(self):
        self.catalogue.failing.add("p1")
        self.crawler_.crawl()
        self.assertEqual(self.index.status("p1")["status"], "failed")
        self.catalogue.failing.clear()
        self.catalogue.calls.clear()
        self.later(4 * 60)
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.calls, [])
        self.later(60)
        self.crawler_.crawl()
        self.assertEqual(self.index.status("p1")["status"], "ready")
        self.assertEqual(self.counts(["p1"]), {"Action": 4})

    def test_a_failed_weekly_crawl_is_retried_as_a_full_crawl(self):
        self.crawler_.crawl()
        del self.catalogue.portals_["p1"]["items"][3:]
        self.catalogue.failing.add("p1")
        self.now = local(10, 22, 4, 0)
        self.crawler_.crawl()
        self.assertEqual(self.index.status("p1")["status"], "stale")
        self.catalogue.failing.clear()
        self.later(5 * 60)
        self.crawler_.crawl()
        self.assertEqual(self.counts(["p1"]), {"Action": 3})
        self.assertEqual(self.index.status("p1")["status"], "ready")


class FakeTimer:
    """threading.Timer as the crawler arms it, recorded instead of run."""
    armed = []

    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelled, self.daemon = delay, fn, False, False

    def start(self):
        FakeTimer.armed.append(self)

    def cancel(self):
        self.cancelled = True


class ScheduleTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        FakeTimer.armed = []
        self.catalogue = FakeCatalogue({"p1": {"name": "One", "categories": [cat("10", "Action")],
                                               "items": films(range(4))}})
        self.crawler_ = ondemand.Crawler(self.index, self.catalogue, sleep=self.sleeps.append,
                                         clock=lambda: self.now, timer=FakeTimer)

    def runInBackground(self):
        thread = self.crawler_.wake()
        thread.join(5)
        self.assertFalse(thread.is_alive())

    def test_after_a_crawl_the_next_wake_is_the_incremental_pull_two_hours_on(self):
        self.runInBackground()
        self.assertEqual([t.delay for t in FakeTimer.armed], [2 * HOUR])
        self.assertTrue(FakeTimer.armed[0].daemon)
        self.later(2 * HOUR)
        FakeTimer.armed[0].fn().join(5)  # the timer fires
        self.assertEqual(self.catalogue.pages("p1"), [1, 2, 1])

    def test_after_a_failure_the_next_wake_is_the_retry(self):
        self.catalogue.failing.add("p1")
        self.runInBackground()
        self.assertEqual([t.delay for t in FakeTimer.armed], [5 * 60])

    def test_a_crawl_that_crashes_waits_five_minutes_before_trying_again(self):
        def crash(portal, source="vod"):
            raise RuntimeError("bug")

        self.catalogue.categories = crash
        with self.assertLogs("STB-Proxy", "ERROR"):
            self.runInBackground()
        self.assertEqual([t.delay for t in FakeTimer.armed], [5 * 60])

    def test_a_new_wake_replaces_the_armed_one(self):
        self.runInBackground()
        self.runInBackground()
        self.assertEqual([t.cancelled for t in FakeTimer.armed], [True, False])

    def test_refreshes_pause_while_every_account_is_off_and_the_index_is_kept(self):
        self.runInBackground()
        self.catalogue.on = False
        self.catalogue.calls.clear()
        self.later(3 * HOUR)
        FakeTimer.armed[0].fn()
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.calls, [])
        self.assertEqual(len(FakeTimer.armed), 1)  # nothing re-armed while off
        self.assertEqual(self.counts(["p1"]), {"Action": 4})
        # Switched back on, the overdue pull happens.
        self.catalogue.on = True
        self.runInBackground()
        self.assertEqual(self.catalogue.pages("p1"), [1])


def show(id, name, cat0, added="2026-10-01 10:00:00"):
    """An Xtream type=series row."""
    return {"id": str(id), "name": name, "o_name": name, "year": "2024-05-01", "added": added,
            "rating_kinopoisk": "8", "category_id": cat0, "is_series": 1, "has_files": 1,
            "series": [], "cmd": ""}


class XtreamSeriesTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        self.catalogue = FakeCatalogue({"p1": {
            "name": "Xtream", "categories": [cat("1", "Action"), cat("2", "Drama")],
            "items": films(range(3), cat0="1"),
            # Series ids and category ids are their own: they collide with the Movies'.
            "series": {"categories": [cat("1", "Action"), cat("5", "Kids")],
                       "items": [show(1, "Show 1", "1"), show(2, "Show 2", "5"), show(3, "Show 3", "5")]},
        }})
        self.crawler_ = self.crawler(self.catalogue)

    def test_type_series_is_crawled_as_well_and_kept_apart_from_movies(self):
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.pages("p1", "series"), [1, 2])
        self.assertEqual(self.counts(["p1"]), {"Action": 4, "Kids": 2})
        self.assertEqual(self.index.item("p1", "1")["kind"], "movie")
        show1 = self.index.item("p1", "series:1")
        self.assertEqual((show1["kind"], show1["name"]), ("series", "Show 1"))
        # The portal's own row keeps the portal's ids, for the Seasons call (06).
        self.assertEqual(show1["raw"]["id"], "1")
        self.assertEqual(self.index.status("p1")["status"], "ready")

    def test_the_series_paging_bug_stops_the_crawl_and_reads_partial(self):
        # XC_VM's type=series ignores p= and answers page 1 every time.
        page = self.catalogue.page

        def buggy(portal, p, source="vod"):
            return page(portal, 1 if source == "series" else p, source)

        self.catalogue.page = buggy
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.pages("p1", "series"), [1, 1])
        self.assertEqual(self.counts(["p1"]), {"Action": 4, "Kids": 1})
        status = self.index.status("p1")
        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["lastRefresh"], int(self.now))
        # Partial sticks through incremental pulls, which never reach page 2 ...
        self.catalogue.portals_["p1"]["items"].insert(0, item(50, "New", "1"))
        self.later(2 * HOUR)
        self.crawler_.crawl()
        self.assertEqual(self.index.status("p1")["status"], "partial")
        self.assertEqual(self.counts(["p1"]), {"Action": 5, "Kids": 1})
        # ... until a full crawl gets through every page.
        self.catalogue.page = page
        self.now = local(10, 22, 4, 0)
        self.crawler_.crawl()
        self.assertEqual(self.index.status("p1")["status"], "ready")
        self.assertEqual(self.counts(["p1"]), {"Action": 5, "Kids": 2})

    def test_the_weekly_crawl_drops_series_the_portal_no_longer_lists(self):
        self.crawler_.crawl()
        del self.catalogue.portals_["p1"]["series"]["items"][2]
        self.now = local(10, 22, 4, 0)
        self.crawler_.crawl()
        self.assertIsNone(self.index.item("p1", "series:3"))
        self.assertIsNotNone(self.index.item("p1", "series:2"))
        self.assertEqual(self.counts(["p1"]), {"Action": 4, "Kids": 1})

    def test_series_are_kept_when_type_series_doesnt_answer_on_a_weekly_crawl(self):
        self.crawler_.crawl()
        del self.catalogue.portals_["p1"]["series"]
        self.now = local(10, 22, 4, 0)
        self.crawler_.crawl()
        self.assertEqual(self.counts(["p1"]), {"Action": 4, "Kids": 2})


class PurgeTest(IndexTestCase):
    def setUp(self):
        super().setUp()
        self.catalogue = FakeCatalogue({
            "p1": {"name": "One", "categories": [cat("10", "Action")], "items": films(range(4))},
            "p2": {"name": "Two", "categories": [cat("20", "Action")], "items": films(range(3), cat0="20")},
        })
        self.crawler_ = self.crawler(self.catalogue)

    def test_purging_a_portal_removes_its_items_categories_and_status(self):
        self.crawler_.crawl()
        self.index.purge("p1")
        self.assertIsNone(self.index.item("p1", "1"))
        self.assertEqual(self.counts(["p1"]), {})
        self.assertEqual(self.index.status("p1")["status"], "failed")
        self.assertEqual(self.counts(["p2"]), {"Action": 3})

    def test_a_portal_deleted_while_it_is_crawled_is_not_written_back(self):
        page = self.catalogue.page

        def deleteAfterOne(portal, p, source="vod"):
            result = page(portal, p, source)
            if portal == "p1" and p == 1:
                del self.catalogue.portals_["p1"]
                self.index.purge("p1")
            return result

        self.catalogue.page = deleteAfterOne
        self.crawler_.crawl()
        self.assertEqual(self.catalogue.pages("p1"), [1])
        self.assertIsNone(self.index.item("p1", "1"))
        self.assertIsNone(self.index.refreshState("p1"))
        self.assertEqual(self.index.status("p2")["status"], "ready")


if __name__ == "__main__":
    unittest.main()
