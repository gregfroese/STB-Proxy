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


if __name__ == "__main__":
    unittest.main()
