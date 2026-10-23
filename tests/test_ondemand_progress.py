"""The durable viewer-state file (ADR 0006): it survives the index being rebuilt, is never
rebuilt itself, and prunes old Resume points and Watched markers past the cap."""
import os
import tempfile
import unittest
from unittest import mock

import ondemand
from tests.test_ondemand_series import FakeCatalogue

DAY = 24 * 3600
T0 = 1_800_000_000


def movieRow(id, name="Film"):
    return {"id": str(id), "name": name, "o_name": name, "added": "2026-10-01 10:00:00", "category_id": "10"}


class ProgressStoreTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "ondemand.sqlite")
        self.progressPath = os.path.join(folder.name, "ondemand-progress.sqlite")
        self.now = T0
        self.open()

    def open(self):
        self.index = ondemand.Index(self.path, progressPath=self.progressPath)
        self.addCleanup(self.index.close)
        self.progress = ondemand.Progress(self.index, ondemand.SeriesCache(self.index, FakeCatalogue()),
                                          clock=lambda: self.now)

    def state(self, id, account="viewer"):
        return self.progress.movies(account, [("p1", str(id))]).get(("p1", str(id)))


class DurableTest(ProgressStoreTestCase):
    def test_rebuilding_the_index_keeps_the_viewer_state(self):
        self.index.addItems("p1", [movieRow(5)])
        self.progress.report("viewer", ("p1", "5"), 600, 6000)
        self.index.recreate()
        self.assertEqual(self.state(5)["positionSec"], 600)
        self.index.close()
        os.remove(self.path)  # the operator deletes the index to force a re-crawl
        self.open()
        self.assertEqual(self.state(5)["positionSec"], 600)

    def test_an_unreadable_progress_file_is_moved_aside_not_lost(self):
        self.index.close()
        with open(self.progressPath, "wb") as f:
            f.write(b"not a database at all" * 100)
        self.open()
        with open(self.progressPath + ".bad", "rb") as f:
            self.assertTrue(f.read().startswith(b"not a database"))
        self.progress.report("viewer", ("p1", "5"), 600, 6000)
        self.assertEqual(self.state(5)["positionSec"], 600)


class PruningTest(ProgressStoreTestCase):
    def test_resume_points_untouched_for_180_days_are_dropped(self):
        self.progress.report("viewer", ("p1", "1"), 600, 6000)
        self.progress.mark("viewer", ("p1", "2"), True)
        self.progress.report("viewer", ("p1", "2"), 700, 6000)   # a rewatch of a Watched one
        self.now += 100 * DAY
        self.progress.report("viewer", ("p1", "3"), 800, 6000)
        self.now += 80 * DAY + 1
        self.progress.prune()
        self.assertIsNone(self.state(1))
        self.assertEqual(self.state(2), {"positionSec": None, "durationSec": 6000, "watched": True,
                                         "updatedAt": T0})
        self.assertEqual(self.state(3)["positionSec"], 800)

    def test_up_next_untouched_for_180_days_is_dropped_too(self):
        self.index.addItems("p1", [dict(movieRow(77, "Show"), is_series="1")])
        season = {"id": "1", "number": 1, "name": None, "episodeCount": 1}
        self.index.setSeasons("p1", "77", [(season, [
            {"id": "1", "seasonId": "1", "number": 1, "name": None, "play": {}}])], T0)
        self.progress.report("viewer", ("p1", "77", "1", "1"), 600, 2400)
        self.now += 179 * DAY
        self.progress.prune()
        self.assertEqual(self.progress.upNext("viewer", [("p1", "77")])[("p1", "77")]["episodeId"], "1")
        self.now += 1 * DAY + 1
        self.progress.prune()
        self.assertEqual(self.progress.upNext("viewer", [("p1", "77")]), {})

    def test_pruning_runs_by_itself_on_a_write_once_a_day(self):
        self.progress.report("viewer", ("p1", "1"), 600, 6000)
        self.now += 181 * DAY
        self.progress.report("viewer", ("p1", "2"), 600, 6000)
        self.assertIsNone(self.state(1))

    @mock.patch.object(ondemand, "WATCHED_MAX", 50)  # 10,000 in use; fewer keeps the test quick
    def test_watched_markers_are_capped_per_account_oldest_first(self):
        for n in range(ondemand.WATCHED_MAX + 2):
            self.now += 1
            self.progress.mark("viewer", ("p1", str(n)), True)
        self.progress.mark("other", ("p1", "0"), True)
        self.progress.prune()
        self.assertIsNone(self.state(0))
        self.assertIsNone(self.state(1))
        self.assertTrue(self.state(2)["watched"])
        self.assertTrue(self.state(ondemand.WATCHED_MAX + 1)["watched"])
        self.assertTrue(self.state(0, "other")["watched"])


if __name__ == "__main__":
    unittest.main()
