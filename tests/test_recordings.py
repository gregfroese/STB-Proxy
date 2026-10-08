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

    def __init__(self, status=200, chunks=None, body=None):
        self.status_code = status
        self.body = body
        self.chunks = chunks
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
            yield b"x" * 100

    def close(self):
        self.closed.set()


def joinParts(parts, out):
    with open(out, "wb") as f:
        for part in parts:
            with open(part, "rb") as p:
                f.write(p.read())


class RecorderTest(unittest.TestCase):
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
        for _ in range(400):
            if not recorder.isRunning(id):
                return self.store.get(id)
            time.sleep(0.01)
        self.fail("still recording")

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


if __name__ == "__main__":
    unittest.main()
