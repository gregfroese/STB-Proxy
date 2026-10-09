import json
import logging
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import recordings

LOG = logging.getLogger("test-recordings")


def record(**overrides):
    rec = {"id": "r1", "portal": "p1", "channelId": "2", "channelName": "Two", "title": "Two", "folder": "/tmp/x",
           "start": 1000.0, "stop": None, "ended": None, "status": "recording", "waiting": False, "parts": [],
           "gaps": [], "file": None, "size": 0, "updated": 1000.0, "error": None}
    rec.update(overrides)
    return rec


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "recordings.json")

    def test_recordings_are_kept_across_loads_newest_first(self):
        store = recordings.RecordingStore(self.path, LOG)
        store.add(record(id="old", start=1.0))
        store.add(record(id="new", start=2.0))
        store.update("old", status="done", gaps=[[1, 2]])
        again = recordings.RecordingStore(self.path, LOG)
        self.assertEqual([r["id"] for r in again.all()], ["new", "old"])
        self.assertEqual((again.get("old")["status"], again.get("old")["gaps"]), ("done", [[1, 2]]))
        self.assertIsNone(again.get("nope"))

    def test_copies_handed_out_dont_change_the_store(self):
        store = recordings.RecordingStore(self.path, LOG)
        store.add(record())
        store.get("r1")["gaps"].append([1, 2])
        self.assertEqual(store.get("r1")["gaps"], [])

    def test_remove(self):
        store = recordings.RecordingStore(self.path, LOG)
        store.add(record())
        self.assertEqual(store.remove("r1")["id"], "r1")
        self.assertIsNone(store.remove("r1"))
        self.assertEqual(recordings.RecordingStore(self.path, LOG).all(), [])

    def test_an_unreadable_list_is_kept_aside_not_lost(self):
        for garbage in ("{", "[]", '{"recordings": [1]}'):
            with open(self.path, "w") as f:
                f.write(garbage)
            store = recordings.RecordingStore(self.path, LOG)
            self.assertEqual(store.all(), [])
            with open(self.path + ".bad") as f:
                self.assertEqual(f.read(), garbage)


class NamesTest(unittest.TestCase):
    def test_names_are_safe_for_any_share(self):
        self.assertEqual(recordings.safeName('NHL: Oilers/Flames? "Live"'), "NHL_ Oilers_Flames_ _Live_")
        self.assertEqual(recordings.safeName(" .. "), "Recording")
        self.assertEqual(len(recordings.safeName("x" * 300)), 100)

    def test_path_by_title_and_local_time_and_unique(self):
        start = time.mktime((2026, 10, 8, 19, 5, 0, 0, 0, -1))
        taken = {os.path.join("/r", "Two", "Two - 2026-10-08 19.05.mp4"), os.path.join("/r", "Two", "Two - 2026-10-08 19.05 (2).mp4")}
        self.assertEqual(recordings.outputPath("/r", "Two", start, exists=lambda p: False),
                         os.path.join("/r", "Two", "Two - 2026-10-08 19.05.mp4"))
        self.assertEqual(recordings.outputPath("/r", "Two", start, exists=taken.__contains__),
                         os.path.join("/r", "Two", "Two - 2026-10-08 19.05 (3).mp4"))


class FakeResponse:
    """A /play answer: status, a JSON body, and chunks (a number, or endless) until closed."""

    def __init__(self, status=200, chunks=None, body=None, chunkSize=100):
        self.status_code = status
        self.body = body
        self.chunks = chunks
        self.chunkSize = chunkSize
        self.closed = threading.Event()

    def json(self):
        if self.body is None:
            raise ValueError("not JSON")
        return self.body

    def iter_content(self, n):
        sent = 0
        while not self.closed.is_set() and (self.chunks is None or sent < self.chunks):
            time.sleep(0.005)
            sent += 1
            yield b"x" * self.chunkSize

    def close(self):
        self.closed.set()


def joinParts(parts, out):
    with open(out, "wb") as f:
        for part in parts:
            with open(part, "rb") as p:
                f.write(p.read())


class RecorderTestCase(unittest.TestCase):
    """A recorder with a fake /play, a joining remux and plenty of space; no tests of its own."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = os.path.join(self.dir.name, "rec")
        self.store = recordings.RecordingStore(os.path.join(self.dir.name, "recordings.json"), LOG)
        self.responses = []
        self.urls = []
        self.free = 10 * 1024 ** 3
        for name, value in [("RETRY_SECONDS", 0.05), ("SAVE_EVERY", 0)]:
            patcher = mock.patch.object(recordings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def opener(self, url):
        self.urls.append(url)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    def recorder(self, remux=joinParts, folder=None):
        return recordings.Recorder(
            self.store, lambda: self.folder if folder is None else folder,
            lambda portal, channelId, id: "http://local/play/{}/{}?recording={}".format(portal, channelId, id),
            LOG, openStream=self.opener, remux=remux, freeSpace=lambda path: self.free)

    def waitUntilDone(self, recorder, id):
        for _ in range(1000):  # generous: a busy machine shouldn't fail a working recorder
            if not recorder.isRunning(id):
                return self.store.get(id)
            time.sleep(0.01)
        self.fail("still recording")



class RecorderTest(RecorderTestCase):
    def test_records_until_stopped_then_makes_an_mp4(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        self.assertEqual(self.urls, ["http://local/play/p1/2?recording=" + rec["id"]])
        time.sleep(0.1)
        self.assertTrue(recorder.stop(rec["id"]))
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "done")
        self.assertTrue(rec["file"].startswith(os.path.join(self.folder, "Two", "Two - ")))
        self.assertGreater(os.path.getsize(rec["file"]), 0)
        self.assertEqual(rec["size"], os.path.getsize(rec["file"]))
        self.assertEqual(rec["parts"], [])
        self.assertEqual(os.listdir(os.path.join(self.folder, ".partial")), [])
        self.assertFalse(recorder.stop(rec["id"]))  # not running any more

    def test_stops_at_its_stop_time(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two", stop=time.time() + 0.2)
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "done")
        self.assertLess(rec["ended"] - rec["start"], 1.5)

    def test_recording_is_off_without_a_folder(self):
        with self.assertRaisesRegex(recordings.RecordingError, "Recording is off"):
            self.recorder(folder="").start("p1", "2", "Two")

    def test_low_space_refuses_to_start(self):
        self.free = 500 * 1024 ** 2
        with self.assertRaisesRegex(recordings.RecordingError, "Less than 1 GB free"):
            self.recorder().start("p1", "2", "Two")
        self.assertEqual(self.store.all(), [])

    def test_no_free_tuner_or_a_dead_channel_says_why_and_records_nothing(self):
        self.responses = [FakeResponse(503, body={"error": recordings.TUNER_BUSY})]
        with self.assertRaisesRegex(recordings.RecordingError, "No free tuner"):
            self.recorder().start("p1", "2", "Two")
        self.responses = [FakeResponse(503)]
        with self.assertRaisesRegex(recordings.RecordingError, "didn't start"):
            self.recorder().start("p1", "2", "Two")
        self.assertEqual(self.store.all(), [])

    def test_a_lost_stream_is_reopened_and_the_gap_noted(self):
        self.responses = [FakeResponse(chunks=5), FakeResponse(503, body={"error": recordings.TUNER_BUSY}), FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.3)
        recorder.stop(rec["id"])
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "partial")
        self.assertEqual(len(rec["gaps"]), 1)
        self.assertLess(rec["gaps"][0][0], rec["gaps"][0][1])
        self.assertGreater(os.path.getsize(rec["file"]), 500)  # both parts joined
        self.assertEqual(len(self.urls), 3)

    def test_a_failed_remux_keeps_the_parts(self):
        def failing(parts, out):
            raise recordings.RemuxError("Invalid data found when processing input")

        self.responses = [FakeResponse()]
        recorder = self.recorder(remux=failing)
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.05)
        recorder.stop(rec["id"])
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "failed")
        self.assertIn("Invalid data", rec["error"])
        self.assertTrue(rec["parts"] and all(os.path.exists(p) for p in rec["parts"]))

    def test_low_disk_stops_with_what_it_has(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.05)
        self.free = 100 * 1024 ** 2
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "partial")
        self.assertIn("nearly full", rec["error"])
        self.assertTrue(os.path.exists(rec["file"]))

    def test_delete_removes_the_file_but_not_while_recording(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        self.assertFalse(recorder.delete(rec["id"]))
        time.sleep(0.05)  # record something
        recorder.stop(rec["id"])
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertTrue(recorder.delete(rec["id"]))
        self.assertFalse(os.path.exists(rec["file"]))
        self.assertFalse(os.path.exists(os.path.dirname(rec["file"])))  # the empty show folder too
        self.assertIsNone(self.store.get(rec["id"]))

    def test_resume_carries_on_or_finishes(self):
        partial = os.path.join(self.folder, ".partial")
        os.makedirs(partial)
        for id in ("going", "over"):
            with open(os.path.join(partial, id + ".1.ts"), "wb") as f:
                f.write(b"y" * 1000)
        now = time.time()
        self.store.add(record(id="going", folder=self.folder, start=now - 60, stop=now + 1, updated=now - 5,
                              parts=[os.path.join(partial, "going.1.ts")], size=1000))
        self.store.add(record(id="over", folder=self.folder, start=now - 600, stop=now - 60, updated=now - 120,
                              parts=[os.path.join(partial, "over.1.ts")], size=1000))
        self.store.add(record(id="old", status="done", folder=self.folder))
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        recorder.resume()
        over = self.store.get("over")
        self.assertEqual((over["status"], over["gaps"]), ("partial", [[now - 120, now - 60]]))
        self.assertTrue(recorder.isRunning("going"))
        going = self.waitUntilDone(recorder, "going")
        self.assertEqual(going["status"], "partial")
        self.assertEqual(going["gaps"][0][0], now - 5)
        self.assertGreater(os.path.getsize(going["file"]), 1000)  # the old part and the new one
        self.assertEqual(self.store.get("old")["status"], "done")  # left alone


def bytesUnder(folder):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, files in os.walk(folder) for f in files)


class RecorderReviewFixesTest(RecorderTestCase):
    def test_a_recording_leaves_room_for_its_mp4(self):
        # A disk that fills as the recording writes; the MP4 needs as much again. Chunks are
        # bigger than Python's file buffer, as real ones are, so the disk sees each at once.
        capacity = 200000
        limits = {"MIN_FREE_TO_START": 20000, "MIN_FREE_TO_CONTINUE": 5000, "REMUX_MARGIN": 0}
        for name, value in limits.items():
            patcher = mock.patch.object(recordings, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        free = lambda path: capacity - bytesUnder(self.folder)

        def remux(parts, out):
            size = sum(os.path.getsize(p) for p in parts)
            if free(None) < size:
                raise recordings.RemuxError("No space left on device")
            joinParts(parts, out)

        self.responses = [FakeResponse(chunkSize=9000)]
        recorder = recordings.Recorder(self.store, lambda: self.folder, lambda *a: "http://local/play", LOG,
                                       openStream=self.opener, remux=remux, freeSpace=free)
        rec = recorder.start("p1", "2", "Two")
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "partial")
        self.assertIn("nearly full", rec["error"])
        self.assertTrue(os.path.exists(rec["file"]))
        self.assertGreaterEqual(free(None), 5000)

    def test_not_enough_space_for_the_mp4_keeps_the_parts(self):
        calls = []
        self.responses = [FakeResponse()]
        recorder = self.recorder(remux=lambda parts, out: calls.append(out))
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.05)
        self.free = 1  # the disk filled up from elsewhere
        recorder.stop(rec["id"])
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual((rec["status"], calls), ("failed", []))
        self.assertIn("Not enough space", rec["error"])
        self.assertTrue(rec["parts"] and all(os.path.exists(p) for p in rec["parts"]))

    def test_a_failed_remux_leaves_no_broken_file(self):
        def halfWritten(parts, out):
            with open(out, "wb") as f:
                f.write(b"half")
            raise recordings.RemuxError("Conversion failed")

        self.responses = [FakeResponse()]
        recorder = self.recorder(remux=halfWritten)
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.05)
        recorder.stop(rec["id"])
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "failed")
        show = os.path.join(self.folder, "Two")
        self.assertEqual(os.listdir(show) if os.path.isdir(show) else [], [])

    def test_an_unexpected_error_finishing_doesnt_leave_it_running(self):
        def broken(parts, out):
            raise ValueError("surprise")

        self.responses = [FakeResponse()]
        recorder = self.recorder(remux=broken)
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.05)
        recorder.stop(rec["id"])
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(rec["status"], "failed")
        self.assertTrue(recorder.delete(rec["id"]))

    def test_a_stream_that_ends_at_once_is_not_reopened_in_a_loop(self):
        self.responses = [FakeResponse(chunks=3), FakeResponse(chunks=0)]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.5)
        recorder.stop(rec["id"])
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertLessEqual(len(self.urls), 15)  # about one try per RETRY_SECONDS, not hundreds
        self.assertEqual(len(rec["gaps"]), 1)
        self.assertEqual(os.listdir(os.path.join(self.folder, ".partial")), [])  # no empty parts left

    def test_a_stop_survives_a_restart(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.05)
        recorder.stop(rec["id"])
        self.assertTrue(self.store.get(rec["id"])["stopping"])
        self.waitUntilDone(recorder, rec["id"])
        partial = os.path.join(self.folder, ".partial")
        with open(os.path.join(partial, "s.1.ts"), "wb") as f:
            f.write(b"y" * 1000)
        self.store.add(record(id="s", folder=self.folder, start=time.time() - 60, stop=None, stopping=True,
                              parts=[os.path.join(partial, "s.1.ts")], size=1000))
        recorder.resume()
        self.assertFalse(recorder.isRunning("s"))
        self.assertEqual(self.store.get("s")["status"], "done")

    def test_one_recording_per_channel(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        recorder.start("p1", "2", "Two")
        with self.assertRaisesRegex(recordings.RecordingError, "Already recording"):
            recorder.start("p1", "2", "Two")

    def test_recordings_with_one_title_never_share_a_file(self):
        start = time.time()
        paths = [recordings.reservePath(self.folder, "Two", start) for _ in range(3)]
        self.assertEqual(len(set(paths)), 3)
        self.assertTrue(all(os.path.exists(p) for p in paths))


class WatchFromStartTest(RecorderTestCase):
    def watch(self, recorder, id, seconds):
        """Read follow(id) on a thread for a while; returns (bytes so far list, the generator, thread)."""
        got = []
        gen = recorder.follow(id)
        thread = threading.Thread(target=lambda: [got.append(len(b)) for b in gen], daemon=True)
        thread.start()
        time.sleep(seconds)
        return got, gen, thread

    def test_follows_a_growing_recording_to_its_end(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.1)
        got, gen, thread = self.watch(recorder, rec["id"], 0.2)
        recorder.stop(rec["id"])
        thread.join(5)
        self.assertFalse(thread.is_alive())  # it ends once the recording has
        rec = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(sum(got), os.path.getsize(rec["file"]))  # every byte, from the start

    def test_parts_are_kept_until_the_last_viewer_leaves(self):
        self.responses = [FakeResponse()]
        recorder = self.recorder()
        rec = recorder.start("p1", "2", "Two")
        time.sleep(0.05)
        gen = recorder.follow(rec["id"])
        next(gen)  # watching
        recorder.stop(rec["id"])
        done = self.waitUntilDone(recorder, rec["id"])
        self.assertEqual(done["status"], "done")
        partial = os.path.join(self.folder, ".partial")
        self.assertNotEqual(os.listdir(partial), [])  # still being watched
        gen.close()
        self.assertEqual(os.listdir(partial), [])

    def test_following_an_unknown_or_finished_recording_gives_nothing(self):
        recorder = self.recorder()
        self.assertEqual(list(recorder.follow("nope")), [])


class RemuxCommandTest(unittest.TestCase):
    def test_parts_are_joined_with_the_concat_list_into_an_mp4(self):
        seen = {}

        def run(cmd, **kwargs):
            seen["cmd"], seen["kwargs"] = cmd, kwargs
            with open(cmd[cmd.index("-i") + 1]) as f:
                seen["list"] = f.read()
            return mock.Mock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as d, mock.patch.object(recordings.subprocess, "run", side_effect=run):
            parts = [os.path.join(d, "a.1.ts"), os.path.join(d, "it's|2.ts")]
            recordings.defaultRemux(parts, os.path.join(d, "out.mp4.part"))
            self.assertEqual(os.listdir(d), [])  # the list is tidied away
        cmd = seen["cmd"]
        self.assertEqual(cmd[cmd.index("-f") + 1], "concat")
        self.assertEqual(cmd[cmd.index("-safe") + 1], "0")
        self.assertEqual(cmd[-3:], ["-f", "mp4", os.path.join(d, "out.mp4.part")])
        self.assertEqual(seen["list"], "file '{}'\nfile '{}'\n".format(parts[0], parts[1].replace("'", "'\\''")))
        self.assertEqual(seen["kwargs"].get("errors"), "replace")


if __name__ == "__main__":
    unittest.main()
