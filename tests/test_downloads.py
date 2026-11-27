import logging
import os
import tempfile
import threading
import unittest

import downloads
import ondemandsession

LOG = logging.getLogger("test-downloads")
MASTER = ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n"
          "#EXT-X-STREAM-INF:AVERAGE-BANDWIDTH=9000000,BANDWIDTH=2000000\nhigh.m3u8\n")


def media(n):
    return "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n" + "".join(
        "#EXTINF:8,\ns{}.ts\n".format(i) for i in range(n)) + "#EXT-X-ENDLIST\n"


class FakeSession:
    """An ondemandsession.Session over canned playlists and segments. `onSegment(name)` runs
    before each segment is sent; `breakAt` names a segment that fails as an eviction."""

    def __init__(self, segments=3, master=MASTER):
        self.reason = None
        self.master = master
        self.count = segments
        self.fetched = []
        self.onSegment = None
        self.breakAt = None
        self.link = None

    def open(self, link):
        self.link = link

    def end(self, reason):
        if self.reason is None:
            self.reason = reason

    def playlist(self, name):
        if self.reason:
            raise ondemandsession.Ended(self.reason)
        return self.master if name == ondemandsession.MASTER else media(self.count)

    def segment(self, name, range=None):
        if self.reason:
            raise ondemandsession.Ended(self.reason)
        if name == self.breakAt:
            self.end("evicted")
            raise ondemandsession.Ended("evicted")
        if self.onSegment:
            self.onSegment(name)
        self.fetched.append(name)
        body = name.encode() * 10
        return 200, {"Content-Length": str(len(body))}, iter([body[:5], body[5:]])


class DownloaderTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = os.path.join(self.dir.name, "movies")
        self.tvFolder = os.path.join(self.dir.name, "tv")
        self.now = 10_000.0
        self.streaming = set()  # portals someone else streams from
        self.slots = []  # (portal, mac) taken by downloads
        self.sessions = []
        self.remuxed = []
        self.free = 10 * 1024 ** 3
        self.nextSession = lambda: FakeSession()
        self.store = downloads.DownloadStore(os.path.join(self.dir.name, "downloads.json"), LOG)
        self.downloader = self.make()

    def make(self):
        return downloads.Downloader(
            self.store, lambda kind: self.folder if kind == "movie" else self.tvFolder, busy=lambda portal: portal in self.streaming,
            admit=self.admit, mint=lambda rec, mac: "http://storage/" + rec["id"],
            openSession=self.open, log=LOG, clock=lambda: self.now, remux=self.remux,
            freeSpace=lambda folder: self.free)

    def admit(self, rec, stillQuiet):
        if not stillQuiet():
            return None
        slot = (rec["portal"], "mac1")
        self.slots.append(slot)
        return "mac1", lambda: slot in self.slots and self.slots.remove(slot)

    def open(self, rec, mac):
        session = self.nextSession()
        self.sessions.append(session)
        return session

    def remux(self, parts, out):
        with open(parts[0], "rb") as f:
            data = f.read()
        self.remuxed.append((out, data))
        with open(out, "wb") as f:
            f.write(b"mp4:" + data)

    def movie(self, portal="p1", id="5", name="Heat", year=1995):
        rec, _ = self.downloader.request("viewer", portal, {"id": id}, "movie", name,
                                         {"name": name, "year": year}, {"cmd": "/media/5.mpg", "series": 0})
        return rec

    def runQueue(self, portal="p1"):
        """One look at the queue, then wait for the download it started to stop."""
        self.downloader.tick()
        job = self.downloader.running.get(portal)
        if job is not None:
            job["thread"].join(5)
        return job

    def later(self, seconds=downloads.QUIET):
        self.now += seconds


class QueueTest(DownloaderTestCase):
    def test_a_movie_waits_for_quiet_then_lands_in_the_library(self):
        rec = self.movie()
        self.assertEqual(rec["status"], "queued")
        self.assertIsNone(self.runQueue())  # STB-Proxy has only just started
        self.later()
        self.runQueue()
        done = self.store.get(rec["id"])
        path = os.path.join(self.folder, "Heat (1995)", "Heat (1995).mp4")
        self.assertEqual((done["status"], done["progress"], done["file"]), ("done", 100, path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"mp4:" + b"".join(n.encode() * 10 for n in ("s0.ts", "s1.ts", "s2.ts")))
        self.assertEqual(done["size"], os.path.getsize(path))
        self.assertEqual(self.sessions[0].link, "http://storage/" + rec["id"])
        self.assertEqual(self.slots, [])  # the slot is back
        self.assertEqual(os.listdir(os.path.join(self.folder, downloads.PARTIAL)), [])

    def test_episodes_are_named_for_plex(self):
        rec, _ = self.downloader.request(
            "viewer", "p1", {"seriesId": "77", "seasonId": "3", "episodeId": "901"}, "episode",
            "Show - S2E5", {"series": "Show", "year": 2020, "season": 2, "episode": 5, "episodeName": "Five"},
            {"movie_id": "77"})
        self.assertEqual(downloads.libraryPath("/tv", rec),
                         "/tv/Show (2020)/Season 02/Show (2020) - S02E05.mp4")
        rec["names"].update(season=None, seasonName="Extras", episode=None, year=None)
        self.assertEqual(downloads.libraryPath("/tv", rec), "/tv/Show/Extras/Show - Five.mp4")

    def test_the_library_is_told_and_its_failure_changes_nothing(self):
        told = []

        def done(rec, folder):
            told.append((rec["status"], rec["file"], folder))
            raise RuntimeError("Plex is away")
        self.downloader.done = done
        rec = self.movie()
        self.later()
        self.runQueue()
        path = os.path.join(self.folder, "Heat (1995)", "Heat (1995).mp4")
        self.assertEqual(told, [("done", path, self.folder)])
        self.assertEqual(self.store.get(rec["id"])["status"], "done")

    def test_a_taken_name_gets_a_number(self):
        os.makedirs(os.path.join(self.folder, "Heat (1995)"))
        open(os.path.join(self.folder, "Heat (1995)", "Heat (1995).mp4"), "w").close()
        rec = self.movie()
        self.later()
        self.runQueue()
        self.assertTrue(self.store.get(rec["id"])["file"].endswith("Heat (1995) (2).mp4"))

    def test_asking_again_gives_the_same_download(self):
        first = self.movie()
        again, queued = self.downloader.request("other", "p1", {"id": "5"}, "movie", "Heat", {"name": "Heat"}, {})
        self.assertEqual((again["id"], again["account"], queued), (first["id"], "viewer", False))
        self.assertEqual(len(self.store.all()), 1)

    def test_a_downloaded_file_that_has_gone_is_downloaded_again(self):
        first = self.movie()
        self.later()
        self.runQueue()
        os.remove(self.store.get(first["id"])["file"])
        again = self.movie()
        self.assertNotEqual(again["id"], first["id"])
        self.assertEqual(again["status"], "queued")

    def test_one_download_per_portal_at_a_time_oldest_first(self):
        gate = threading.Event()
        self.nextSession = lambda: self.gated(gate)
        first, second = self.movie(id="5"), self.movie(id="6", name="Ronin")
        other = self.movie(portal="p2", id="5")
        self.later()
        self.downloader.tick()
        self.assertEqual({p: j["id"] for p, j in self.downloader.running.items()},
                         {"p1": first["id"], "p2": other["id"]})
        self.assertEqual(self.store.get(second["id"])["status"], "queued")
        gate.set()
        for job in list(self.downloader.running.values()):
            job["thread"].join(5)
        self.runQueue()
        self.assertEqual(self.store.get(second["id"])["status"], "done")

    def gated(self, gate):
        session = FakeSession()
        session.onSegment = lambda name: gate.wait(5)
        return session

    def test_nothing_runs_without_a_folder_and_the_queue_keeps(self):
        self.folder = ""
        rec = self.movie()
        self.later()
        self.assertIsNone(self.runQueue())
        self.assertEqual(self.store.get(rec["id"])["status"], "queued")

    def test_a_kind_with_no_folder_waits_without_holding_up_the_other(self):
        self.tvFolder = ""
        episode, _ = self.downloader.request(
            "viewer", "p1", {"seriesId": "77", "seasonId": "3", "episodeId": "901"}, "episode",
            "Show - S2E5", {"series": "Show", "year": 2020, "season": 2, "episode": 5}, {"movie_id": "77"})
        self.now += 1
        movie = self.movie()
        self.later()
        self.runQueue()
        self.assertEqual(self.store.get(movie["id"])["status"], "done")
        self.assertEqual(self.store.get(episode["id"])["status"], "queued")

    def test_a_folder_it_cant_reach_fails_with_a_reason(self):
        def gone(folder):
            raise FileNotFoundError(folder)
        self.downloader.freeSpace = gone
        rec = self.movie()
        self.later()
        self.runQueue()
        failed = self.store.get(rec["id"])
        self.assertEqual((failed["status"], failed["error"]),
                         ("failed", "Can't reach the downloads folder " + self.folder))

    def test_no_room_on_the_disk_fails_with_a_reason(self):
        self.free = 10
        rec = self.movie()
        self.later()
        self.runQueue()
        failed = self.store.get(rec["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("free space", failed["error"])

    def test_a_running_download_is_queued_again_after_a_restart(self):
        rec = self.movie()
        self.store.update(rec["id"], status="downloading")
        self.make()
        self.assertEqual(self.store.get(rec["id"])["status"], "queued")

    def test_cancel_removes_it_and_its_partial_file(self):
        rec = self.movie()
        self.store.update(rec["id"], status="failed", segmentsDone=1, bytes=3)
        os.makedirs(os.path.join(self.folder, downloads.PARTIAL))
        partial = os.path.join(self.folder, downloads.PARTIAL, rec["id"] + ".ts")
        open(partial, "w").close()
        self.assertTrue(self.downloader.cancel(rec["id"]))
        self.assertIsNone(self.store.get(rec["id"]))
        self.assertFalse(os.path.exists(partial))

    def test_delete_removes_a_finished_file(self):
        rec = self.movie()
        self.later()
        self.runQueue()
        path = self.store.get(rec["id"])["file"]
        self.assertFalse(self.downloader.cancel(rec["id"]))  # viewers can't cancel a finished one
        self.assertTrue(self.downloader.delete(rec["id"]))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.store.all(), [])


class GivingWayTest(DownloaderTestCase):
    def test_a_viewer_pauses_it_and_it_goes_on_from_where_it_was(self):
        self.later()
        rec = self.movie()
        holder = {}

        def watchMidway(name):
            if name == "s1.ts" and not holder:
                holder["yielded"] = True
                self.downloader.yieldPortal("p1")
                self.assertEqual(self.slots, [])  # freed before the viewer is admitted

        first = FakeSession()
        first.onSegment = watchMidway
        self.nextSession = lambda: first
        self.runQueue()
        paused = self.store.get(rec["id"])
        self.assertEqual((paused["status"], paused["segmentsDone"], paused["progress"]), ("queued", 1, 33))

        self.later(downloads.QUIET - 1)
        self.assertIsNone(self.runQueue())  # not quiet for long enough yet
        self.later(1)
        second = FakeSession()
        self.nextSession = lambda: second
        self.runQueue()
        self.assertEqual(second.fetched, ["s1.ts", "s2.ts"])
        self.assertEqual(self.store.get(rec["id"])["status"], "done")
        self.assertEqual(self.remuxed[0][1], b"".join(n.encode() * 10 for n in ("s0.ts", "s1.ts", "s2.ts")))

    def test_a_pause_that_ends_the_session_under_it_is_still_a_pause(self):
        rec = self.movie()
        self.later()
        session = FakeSession()

        def pauseThenBreak(name):
            if name == "s1.ts":
                self.downloader.yieldPortal("p1")
                raise ondemandsession.Ended("stopped")

        session.onSegment = pauseThenBreak
        self.nextSession = lambda: session
        self.runQueue()
        paused = self.store.get(rec["id"])
        self.assertEqual((paused["status"], paused["segmentsDone"], paused["attempts"], paused["retryAt"]),
                         ("queued", 1, 0, None))

    def test_it_waits_while_anyone_streams_from_the_portal(self):
        rec = self.movie()
        self.later()
        self.streaming.add("p1")
        self.assertIsNone(self.runQueue())
        self.streaming.clear()
        self.later(downloads.QUIET - 1)
        self.assertIsNone(self.runQueue())  # quiet counts from the last time it was busy
        self.later(1)
        self.runQueue()
        self.assertEqual(self.store.get(rec["id"])["status"], "done")

    def test_an_eviction_waits_for_quiet_and_retries_later(self):
        rec = self.movie()
        self.later()
        session = FakeSession()
        session.breakAt = "s1.ts"
        self.nextSession = lambda: session
        self.runQueue()
        broken = self.store.get(rec["id"])
        self.assertEqual((broken["status"], broken["segmentsDone"], broken["attempts"]), ("queued", 1, 1))
        self.assertFalse(self.downloader.quiet("p1"))

    def test_it_fails_after_tries_that_get_no_further(self):
        rec = self.movie()

        def broken():
            session = FakeSession()
            session.breakAt = "s0.ts"
            return session

        self.nextSession = broken
        for _ in range(downloads.MAX_ATTEMPTS):
            self.later(downloads.QUIET + downloads.RETRY_AFTER * downloads.MAX_ATTEMPTS)
            self.runQueue()
        failed = self.store.get(rec["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("another device", failed["error"])
        again, queued = self.downloader.request("viewer", "p1", {"id": "5"}, "movie", "Heat", {}, {})
        self.assertEqual((again["status"], again["attempts"], queued), ("queued", 0, True))

    def test_a_different_stream_starts_over(self):
        rec = self.movie()
        self.store.update(rec["id"], segments=7, segmentsDone=4, bytes=40)
        self.later()
        self.runQueue()
        self.assertEqual(self.sessions[0].fetched, ["s0.ts", "s1.ts", "s2.ts"])
        self.assertEqual(len(self.remuxed[0][1]), 3 * 50)


class PlaylistTest(unittest.TestCase):
    def test_the_best_variant(self):
        self.assertEqual(downloads.bestVariant(MASTER), "high.m3u8")

    def test_resources(self):
        self.assertEqual(downloads.resources(media(2)), ["s0.ts", "s1.ts"])
        fmp4 = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4,\na.m4s\n#EXT-X-ENDLIST\n'
        self.assertEqual(downloads.resources(fmp4), ["init.mp4", "a.m4s"])
        plain = '#EXTM3U\n#EXT-X-KEY:METHOD=NONE\n#EXTINF:4,\na.ts\n#EXT-X-ENDLIST\n'
        self.assertEqual(downloads.resources(plain), ["a.ts"])
        for bad in ("#EXTM3U\n#EXTINF:4,\na.ts\n",
                    '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="k"\n#EXTINF:4,\na.ts\n#EXT-X-ENDLIST\n',
                    "#EXTM3U\n#EXT-X-BYTERANGE:10@0\n#EXTINF:4,\na.ts\n#EXT-X-ENDLIST\n"):
            with self.assertRaises(downloads.Unsupported):
                downloads.resources(bad)

    def test_an_unsupported_stream_fails(self):
        test = DownloaderTestCase("runQueue")
        test.setUp()
        try:
            test.nextSession = lambda: FakeSession(master="#EXTM3U\n#EXTINF:4,\nlive.ts\n")
            rec = test.movie()
            test.later()
            test.runQueue()
            self.assertEqual(test.store.get(rec["id"])["status"], "failed")
        finally:
            test.doCleanups()


if __name__ == "__main__":
    unittest.main()
