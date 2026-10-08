# Record Now Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a channel on demand (from a Multiview tile or the preview player), until
stopped or for a chosen time, into a recordings folder. A Recordings page lists running
and finished recordings, and finished ones can be played in the browser, downloaded or
deleted.

**Architecture:**
- **`recordings.py`** (new module) has two parts.
  - `RecordingStore` keeps every recording in `recordings.json`, beside `config.json`, and
    saves the whole file atomically on each change.
  - `Recorder` runs each recording on its own thread.
- **Reading the stream.** A recording reads its channel from STB-Proxy's own
  `/play/<portal>/<channel>?recording=<id>` over local HTTP, just like Plex does. That
  way it shares streams and tuners through PR 1's pool, which ranks it as a "recording"
  viewer. The recorder writes the bytes as they arrive into `.ts` parts under
  `<folder>/.partial/`, and starts a new part each time the stream has to be reopened.
- **Finishing.** When a recording ends, one ffmpeg run joins the parts into an MP4, with
  video copied and audio converted to AAC.
- **Wiring in `app.py`:** a setting, JSON routes and a resume step at startup.
- **Pages:**
  - a Recordings page;
  - a shared "Record" menu (`templates/_record_modal.html`, `static/recordings.js`),
    used by Multiview tiles and the preview player.

**Tech Stack:** Python 3 / Flask 2.2 (single `app.py`), `requests` (already a
dependency), ffmpeg (already required), unittest, Jinja, Bootstrap 5.0.1, jQuery 3.6,
Font Awesome 4.7, ES5-style JavaScript, node (for JS tests).

**Spec:** `docs/superpowers/specs/2026-10-08-multiview-recording-design.md`, section 2.
This plan is PR 2 of 3. Scheduling, both from the guide and as a manual slot, plus the
padding settings and the Scheduled tab, are PR 3.

**Spec refinement:**
- **What the spec says:** each recording runs one ffmpeg that reads `/play` and writes
  `.ts`.
- **What this plan does:** read `/play` with `requests` and write the bytes straight to
  `.ts` parts. ffmpeg runs once, at the end, to join the parts and convert the audio.
- **Why:**
  - The recorder can see `/play`'s answer: 503 "All tuners are busy" versus a portal
    failure.
  - No ffmpeg process runs for the whole recording, which saves memory on the 1 GB
    container.
  - Reconnects become new parts that the final step joins, instead of appending to a
    single file.
- The resulting files and statuses are the same as in the spec.

## Global Constraints

- **Statuses:** a recording is one of `recording`, `done`, `partial` or `failed`.
  `scheduled`, `missed` and `cancelled` come with PR 3.
  - **While recording:** `waiting: true` means it's waiting for a tuner.
  - **`partial`:** it has gaps, or it stopped for a disk problem.
  - **`failed`:** nothing was recorded, or the MP4 couldn't be made. The parts are kept in
    that case.
- **File path:** `<folder>/<Title>/<Title> - YYYY-MM-DD HH.MM.mp4` in local time, with
  ` (2)`, ` (3)` and so on if the name is taken. The title is the channel name for record now.
- **Disk limits:**
  - starting needs at least 1 GB free in the folder (`MIN_FREE_TO_START`);
  - a running recording stops, keeping what it has, below 300 MB (`MIN_FREE_TO_CONTINUE`).
- **The `recordings folder` setting:** empty means recording is off. Then the Record
  buttons are hidden and `/recordings/start` refuses.
- **Recording URL:** `http://127.0.0.1:8001/play/<portal>/<channel>?recording=<id>`.
  Port 8001 is the port `app.py` serves on.
- **Busy text:** `TUNER_BUSY = "All tuners are busy"` lives in `recordings.py`, and
  `app.py` uses `recordings.TUNER_BUSY`.
- **Line endings:** `templates/settings.html`, `templates/base.html` and
  `templates/_player.html` use CRLF and must stay CRLF. When editing them with a script,
  open the file with `newline=''` and insert `\r\n`.
- **Copy:** plain and short. Commit and PR text never names the user's blocks, channels,
  portals, MACs, IPs or IDs.
- **Commits:** every commit message ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Tests:** run them with `.venv/bin/python -m unittest ...` from the repo root.

## Review Focus

1. **The disk fills during a recording.** In production the folder starts as `/tmp`, on
   the container's 3 GB root disk, and a full disk would break config writes. The
   recording must stop at 300 MB free and keep what it has. Pinned by
   `test_low_disk_stops_with_what_it_has` (Task 2).
2. **STB-Proxy restarts mid-recording** (every deploy does this). The recording must carry
   on afterwards with the gap noted, not be lost. Pinned by
   `test_resume_carries_on_or_finishes` (Task 2).
3. **The portal drops the stream mid-recording.** It must be reopened, the parts joined,
   and the recording marked partial. Pinned by
   `test_a_lost_stream_is_reopened_and_the_gap_noted` (Task 2).
4. **The final ffmpeg fails.** The parts must be kept and the recording marked failed
   with a message, never silently deleted. Pinned by
   `test_a_failed_remux_keeps_the_parts` (Task 2).
5. **A crafted id on the file, stop or delete routes** must not reach files the recorder
   didn't write. Pinned by `test_file_route_only_serves_known_recordings` (Task 3).

---

### Task 1: The recordings list and file names

**Files:**
- Create: `recordings.py`
- Create: `tests/test_recordings.py`

**Interfaces:**
- Produces:
  - `recordings.TUNER_BUSY`
  - `recordings.RecordingError(Exception)` and `recordings.RemuxError(Exception)`
  - `safeName(text) -> str`
  - `outputPath(folder, title, start, exists=os.path.exists) -> str`
  - `RecordingStore(path, log)` with `add(rec)`, `update(id, **fields)`, `remove(id) -> rec|None`,
    `get(id) -> rec|None` (a deep copy) and `all() -> [rec]` (newest first)
- A recording dict has these keys:
  - `id`, `portal`, `channelId`, `channelName`, `title`, `folder`
  - `start`, `stop` (epoch seconds or None), `ended`
  - `status`, `waiting`, `parts` (absolute paths), `gaps` (`[[from, to], ...]`), `file`
    (absolute path or None)
  - `size`, `updated`, `error`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recordings.py`:

```python
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
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_recordings -v`
Expected: an ERROR, `ModuleNotFoundError: No module named 'recordings'`.

- [ ] **Step 3: Implement `recordings.py` (the store and the names)**

```python
"""Recordings: the list of them (recordings.json, beside config.json) and the recorder.

A recording reads its channel from STB-Proxy's own /play, as Plex would, so it shares
streams and tuners with everything else: it's a "recording" viewer, which may take a tuner
from a browser preview but never from a player. It writes the stream as it comes into .ts
parts in <folder>/.partial (a new part each time the stream had to be reopened), and when
it ends, joins them into one MP4 with AAC audio, which browsers, Plex and Jellyfin play.
"""
import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

import requests

TUNER_BUSY = "All tuners are busy"  # /play's answer when no tuner is free
MIN_FREE_TO_START = 1024 ** 3  # bytes free in the folder needed to start a recording
MIN_FREE_TO_CONTINUE = 300 * 1024 ** 2  # below this a recording stops, keeping what it has
RETRY_SECONDS = 30  # between tries to get a lost channel back
SAVE_EVERY = 15  # seconds between saving a recording's progress
CHUNK = 65536


class RecordingError(Exception):
    """A recording that can't start; the message is for the user."""


class RemuxError(Exception):
    pass


def safeName(text):
    """text as a file or folder name: no path separators, nor characters SMB shares refuse."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(text))[:100].strip(" .")
    return name or "Recording"


def outputPath(folder, title, start, exists=os.path.exists):
    """<folder>/<Title>/<Title> - YYYY-MM-DD HH.MM.mp4 (local time), " (2)" etc. if taken."""
    name = safeName(title)
    stamp = time.strftime("%Y-%m-%d %H.%M", time.localtime(start))
    base = os.path.join(folder, name, "{} - {}".format(name, stamp))
    path, n = base + ".mp4", 2
    while exists(path):
        path, n = "{} ({}).mp4".format(base, n), n + 1
    return path


class RecordingStore:
    """recordings.json: every recording, by id, saved whole and atomically on each change."""

    def __init__(self, path, log):
        self.path = path
        self.log = log
        self.lock = threading.Lock()
        self.items = self.load()

    def load(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path) as f:
                return {r["id"]: r for r in json.load(f)["recordings"]}
        except (OSError, ValueError, KeyError, TypeError) as e:
            bad = self.path + ".bad"
            self.log.error("Can't read {} ({}). Kept it as {} and started a new list.".format(self.path, e, bad))
            try:
                os.replace(self.path, bad)
            except OSError:
                pass
            return {}

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"recordings": list(self.items.values())}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def add(self, rec):
        with self.lock:
            self.items[rec["id"]] = copy.deepcopy(rec)
            self.save()

    def update(self, id, **fields):
        with self.lock:
            if id in self.items:
                self.items[id].update(copy.deepcopy(fields))
                self.save()

    def remove(self, id):
        with self.lock:
            rec = self.items.pop(id, None)
            if rec is not None:
                self.save()
            return rec

    def get(self, id):
        with self.lock:
            return copy.deepcopy(self.items.get(id))

    def all(self):
        """Newest first."""
        with self.lock:
            return sorted(copy.deepcopy(list(self.items.values())), key=lambda r: r["start"], reverse=True)
```

Also add to `.gitignore`, after the `config.json` line:

```
recordings.json
recordings.json.bad
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_recordings -v`
Expected: all 6 pass.

- [ ] **Step 5: Commit**

```bash
git add recordings.py tests/test_recordings.py .gitignore
git commit -m "Add the recordings list and recording file names

recordings.json beside config.json keeps every recording, saved atomically; an
unreadable one is kept aside as .bad. Files are named Title/Title - date
time.mp4, safe for SMB shares and never overwriting.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The recorder

**Files:**
- Modify: `recordings.py`, adding `defaultOpen`, `defaultRemux`, `defaultFreeSpace` and
  `class Recorder` at the end
- Modify: `tests/test_recordings.py`, adding `RecorderTest`

**Interfaces:**
- Consumes (Task 1): `RecordingStore`, `outputPath`, `RecordingError`, `RemuxError` and
  `TUNER_BUSY`.
- Produces `Recorder(store, folder, playUrl, log, openStream=defaultOpen, remux=defaultRemux, freeSpace=defaultFreeSpace)`:
  - `folder()` returns the folder setting ("" means off).
  - `playUrl(portal, channelId, id)` returns a URL.
  - `openStream(url)` returns a response with `.status_code`, `.json()`,
    `.iter_content(n)` and `.close()`.
  - `remux(parts, out)` raises `RemuxError` on failure.
  - `freeSpace(folder)` returns bytes.
  - Methods:
    - `start(portal, channelId, channelName, title=None, stop=None) -> rec`, or raises `RecordingError`
    - `stop(id) -> bool`, `isRunning(id) -> bool`, `delete(id) -> bool`
      (False while it's running), `resume()`, `list() -> [rec]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_recordings.py`, above `if __name__ == "__main__":`:

```python
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
        self.store.add(record(id="going", folder=self.folder, start=now - 60, stop=now + 0.3, updated=now - 5,
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
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_recordings.RecorderTest -v`
Expected: every test ERRORs with `AttributeError: module 'recordings' has no attribute 'Recorder'`.

- [ ] **Step 3: Implement the recorder**

Append to `recordings.py`:

```python
def defaultOpen(url):
    return requests.get(url, stream=True, timeout=(10, 60))


def defaultRemux(parts, out):
    """Join .ts parts into one MP4: video as it is, audio as AAC (browsers can't play AC3)."""
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", "concat:" + "|".join(parts),
           "-map", "0:v?", "-map", "0:a?", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", out]
    try:
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3 * 3600)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RemuxError("ffmpeg didn't run: {}".format(type(e).__name__))
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        raise RemuxError(lines[-1] if lines else "ffmpeg failed ({})".format(result.returncode))


def defaultFreeSpace(folder):
    return shutil.disk_usage(folder).free


class Recorder:
    """Starts, stops and finishes recordings, each on its own thread.

    folder() gives the recordings folder setting ("" when recording is off), and
    playUrl(portal, channelId, id) the /play address a recording reads from. openStream,
    remux and freeSpace stand in for the network, ffmpeg and the disk in tests.
    """

    def __init__(self, store, folder, playUrl, log, openStream=defaultOpen, remux=defaultRemux, freeSpace=defaultFreeSpace):
        self.store = store
        self.folder = folder
        self.playUrl = playUrl
        self.log = log
        self.openStream = openStream
        self.remux = remux
        self.freeSpace = freeSpace
        self.running = {}  # id -> {"stop": Event, "response": the open stream or None}
        self.lock = threading.Lock()

    def list(self):
        return self.store.all()

    def start(self, portal, channelId, channelName, title=None, stop=None):
        """Record a channel now, until stop (epoch seconds) or until stopped. Returns the
        recording, or raises RecordingError with a message for the user."""
        folder = self.folder()
        if not folder:
            raise RecordingError("Recording is off: choose a recordings folder in Settings.")
        try:
            os.makedirs(os.path.join(folder, ".partial"), exist_ok=True)
            free = self.freeSpace(folder)
        except OSError as e:
            raise RecordingError("Can't write to the recordings folder {} ({}).".format(folder, e.strerror or e))
        if free < MIN_FREE_TO_START:
            raise RecordingError("Less than 1 GB free in {}.".format(folder))
        now = time.time()
        rec = {
            "id": uuid.uuid4().hex[:12], "portal": portal, "channelId": channelId,
            "channelName": channelName, "title": title or channelName, "folder": folder,
            "start": now, "stop": stop, "ended": None, "status": "recording", "waiting": False,
            "parts": [], "gaps": [], "file": None, "size": 0, "updated": now, "error": None,
        }
        response, problem = self.open(rec)
        if response is None:
            raise RecordingError(problem)
        self.store.add(rec)
        self.launch(rec["id"], response)
        self.log.info("Recording({}) of {} started".format(rec["id"], rec["title"]))
        return self.store.get(rec["id"])

    def open(self, rec):
        """Open the channel from /play: (response, None), or (None, why not)."""
        try:
            response = self.openStream(self.playUrl(rec["portal"], rec["channelId"], rec["id"]))
        except (requests.RequestException, OSError) as e:
            return None, "STB-Proxy didn't answer ({}).".format(type(e).__name__)
        if response.status_code == 200:
            return response, None
        try:
            body = response.json()
            busy = isinstance(body, dict) and body.get("error") == TUNER_BUSY
        except ValueError:
            busy = False
        response.close()
        if busy:
            return None, "No free tuner: Plex or other recordings are using them all."
        return None, "The channel didn't start: the portal may be busy, or the channel dead."

    def launch(self, id, response, gapFrom=None):
        job = {"stop": threading.Event(), "response": None}
        with self.lock:
            self.running[id] = job
        stop = self.store.get(id)["stop"]
        if stop is not None:
            timer = threading.Timer(max(0, stop - time.time()), self.stop, [id])
            timer.daemon = True
            timer.start()
        threading.Thread(target=self.run, args=(id, job, response, gapFrom), daemon=True).start()

    def isRunning(self, id):
        with self.lock:
            return id in self.running

    def stop(self, id):
        """Stop a running recording; it keeps what it has. False if it isn't running."""
        with self.lock:
            job = self.running.get(id)
        if not job:
            return False
        job["stop"].set()
        response = job["response"]
        if response is not None:
            response.close()  # wakes a read waiting on the stream
        return True

    def pastStop(self, rec):
        return rec["stop"] is not None and time.time() >= rec["stop"]

    def run(self, id, job, response, gapFrom):
        try:
            while True:
                rec = self.store.get(id)
                if response is None:
                    if job["stop"].is_set() or self.pastStop(rec):
                        break
                    response, problem = self.open(rec)
                    if response is None:
                        self.store.update(id, waiting=True, error=problem)
                        job["stop"].wait(RETRY_SECONDS)
                        continue
                if gapFrom is not None:
                    self.store.update(id, gaps=rec["gaps"] + [[gapFrom, time.time()]])
                    gapFrom = None
                self.store.update(id, waiting=False, error=None)
                job["response"] = response
                endedEarly = self.copy(self.store.get(id), job, response)
                job["response"] = None
                response.close()
                response = None
                if not endedEarly:
                    break
                gapFrom = time.time()
                self.log.info("Recording({}) lost its stream; getting it back".format(id))
            if gapFrom is not None:
                rec = self.store.get(id)
                self.store.update(id, gaps=rec["gaps"] + [[gapFrom, time.time()]])
        finally:
            self.finish(id)
            with self.lock:
                self.running.pop(id, None)

    def copy(self, rec, job, response):
        """Write the stream to a new part until stopped, the stop time, or a disk problem.
        True if the stream ended before any of those (so it should be reopened)."""
        id = rec["id"]
        part = os.path.join(rec["folder"], ".partial", "{}.{}.ts".format(id, len(rec["parts"]) + 1))
        self.store.update(id, parts=rec["parts"] + [part])
        written = 0
        lastSave = time.time()
        try:
            with open(part, "ab") as f:
                chunks = response.iter_content(CHUNK)
                while not (job["stop"].is_set() or self.pastStop(rec)):
                    try:
                        chunk = next(chunks, None)
                    except Exception as e:  # the stream broke, or stop() closed it
                        if not job["stop"].is_set():
                            self.log.info("Recording({}) stream error: {}".format(id, type(e).__name__))
                        break
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    if time.time() - lastSave >= SAVE_EVERY:
                        lastSave = time.time()
                        self.store.update(id, size=rec["size"] + written, updated=lastSave)
                        if self.freeSpace(rec["folder"]) < MIN_FREE_TO_CONTINUE:
                            self.store.update(id, error="Stopped: the recordings folder is nearly full.")
                            job["stop"].set()
        except OSError as e:
            self.store.update(id, error="Stopped: couldn't write to the recordings folder ({}).".format(e.strerror or e))
            job["stop"].set()
        self.store.update(id, size=rec["size"] + written, updated=time.time())
        return not (job["stop"].is_set() or self.pastStop(rec))

    def finish(self, id):
        """Join a recording's parts into its MP4 and say how it went."""
        rec = self.store.get(id)
        parts = [p for p in rec["parts"] if os.path.exists(p) and os.path.getsize(p) > 0]
        fields = {"ended": time.time(), "waiting": False}
        if not parts:
            fields.update(status="failed", error=rec["error"] or "Nothing was recorded.")
        else:
            out = outputPath(rec["folder"], rec["title"], rec["start"])
            try:
                os.makedirs(os.path.dirname(out), exist_ok=True)
                self.remux(parts, out)
            except (RemuxError, OSError) as e:
                fields.update(status="failed", error="Couldn't make the MP4 ({}). The recorded parts are kept.".format(e))
            else:
                for part in rec["parts"]:
                    try:
                        os.remove(part)
                    except OSError:
                        pass
                fields.update(status="partial" if rec["gaps"] or rec["error"] else "done",
                              file=out, size=os.path.getsize(out), parts=[])
        self.store.update(id, **fields)
        self.log.info("Recording({}) finished: {}".format(id, fields.get("status")))

    def delete(self, id):
        """Delete a finished recording, its file and any kept parts. False while it's running."""
        if self.isRunning(id):
            return False
        rec = self.store.remove(id)
        if rec:
            for path in ([rec["file"]] if rec.get("file") else []) + rec.get("parts", []):
                try:
                    os.remove(path)
                except OSError:
                    pass
            if rec.get("file"):
                try:
                    os.rmdir(os.path.dirname(rec["file"]))  # the show's folder, if now empty
                except OSError:
                    pass
        return True

    def resume(self):
        """After a restart: carry on recordings whose time isn't up; finish the others."""
        for rec in self.store.all():
            if rec["status"] != "recording":
                continue
            gapFrom = rec.get("updated") or rec["start"]
            if rec["stop"] is None or rec["stop"] > time.time():
                self.log.info("Recording({}) carries on after a restart".format(rec["id"]))
                self.launch(rec["id"], None, gapFrom=gapFrom)
            else:
                self.store.update(rec["id"], gaps=rec["gaps"] + [[gapFrom, max(gapFrom, rec["stop"])]])
                self.finish(rec["id"])
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_recordings -v`
Expected: all 16 pass.

- [ ] **Step 5: Commit**

```bash
git add recordings.py tests/test_recordings.py
git commit -m "Add the recorder

Each recording reads its channel from STB-Proxy's own /play, like a player, so
it shares streams and tuners. It writes .ts parts, reopening a lost stream
and noting the gap, and joins them into an MP4 with AAC audio at the end. It
won't start without 1 GB free, stops at 300 MB free keeping what it has,
keeps the parts if the MP4 can't be made, and carries on after a restart.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Recording in the app: setting, routes and resume

**Files:**
- Modify: `app.py`:
  - add `import recordings` and `import shutil`
  - set `TUNER_BUSY = recordings.TUNER_BUSY`
  - add `"recordings folder": ""` to `defaultSettings`
  - add `getRecorder()` and `recordingUrl()` after `saveBlocks`
  - add the `/recordings/...` routes after the `/multiview` route
  - strip the folder in `/settings/save`
  - call `getRecorder().resume()` in `__main__`
- Modify: `Dockerfile`, adding `COPY /recordings.py /app/recordings.py` after the logos line
- Modify: `templates/settings.html` (CRLF), adding a Recording section before Plex
- Create: `tests/test_app_recordings.py`

**Interfaces:**
- Consumes (Task 2): `Recorder` and `RecordingStore`.
- Produces:
  - `getRecorder() -> recordings.Recorder`
  - `recordingUrl(portal, channelId, id) -> str`
  - `GET /recordings/list` returns `{"recordings": [rec], "folder": str, "free": int|null}`
  - `POST /recordings/start` takes JSON `{portal, channelId, name, minutes?, until?}`.
    It returns the recording; 400 for bad times, 404 for an unknown portal, 503
    `{"error"}` when it can't start.
  - `POST /recordings/<id>/stop` returns `{"stopping": true}`, or 404.
  - `POST /recordings/<id>/delete` returns `{"deleted": true}`, 404 or 409.
  - `GET /recordings/<id>/file[?download=1]` returns the MP4 with range support, or 404.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_recordings.py`:

```python
import os
import tempfile
import time
import unittest

import recordings
from tests.support import PORTAL, loadApp, portalConfig
from tests.test_recordings import LOG, FakeResponse, joinParts


class RecordingRoutesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = os.path.join(self.dir.name, "rec")
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}, "settings": {"recordings folder": self.folder}})
        self.client = self.app.app.test_client()
        self.responses = [FakeResponse()]
        store = recordings.RecordingStore(os.path.join(self.dir.name, "recordings.json"), LOG)
        self.app.recorder = recordings.Recorder(
            store, lambda: self.app.getSettings()["recordings folder"], self.app.recordingUrl, LOG,
            openStream=lambda url: self.responses[0], remux=joinParts, freeSpace=lambda path: 10 * 1024 ** 3)
        self.addCleanup(lambda: [self.app.recorder.stop(r["id"]) for r in store.all()])

    def start(self, **body):
        return self.client.post("/recordings/start", json=dict({"portal": PORTAL, "channelId": "2", "name": "Two"}, **body))

    def finished(self, id):
        for _ in range(300):
            if not self.app.recorder.isRunning(id):
                return
            time.sleep(0.01)

    def test_recordings_read_from_play_like_a_player(self):
        self.assertEqual(self.app.recordingUrl("p1", "2", "abc"), "http://127.0.0.1:8001/play/p1/2?recording=abc")
        self.assertEqual(self.app.TUNER_BUSY, recordings.TUNER_BUSY)

    def test_start_list_stop_play_and_delete(self):
        rec = self.start(minutes=30).get_json()
        self.assertEqual((rec["title"], rec["status"]), ("Two", "recording"))
        self.assertAlmostEqual(rec["stop"], time.time() + 1800, delta=5)
        listed = self.client.get("/recordings/list").get_json()
        self.assertEqual([r["id"] for r in listed["recordings"]], [rec["id"]])
        self.assertEqual((listed["folder"], listed["free"] > 0), (self.folder, True))
        self.assertEqual(self.client.post("/recordings/{}/delete".format(rec["id"])).status_code, 409)  # still recording
        self.assertEqual(self.client.post("/recordings/{}/stop".format(rec["id"])).get_json(), {"stopping": True})
        self.finished(rec["id"])
        played = self.client.get("/recordings/{}/file".format(rec["id"]), headers={"Range": "bytes=0-9"})
        self.assertEqual((played.status_code, played.mimetype, len(played.data)), (206, "video/mp4", 10))
        played.close()
        download = self.client.get("/recordings/{}/file?download=1".format(rec["id"]))
        self.assertIn("attachment", download.headers["Content-Disposition"])
        download.close()
        self.assertEqual(self.client.post("/recordings/{}/delete".format(rec["id"])).get_json(), {"deleted": True})
        self.assertEqual(self.client.get("/recordings/list").get_json()["recordings"], [])

    def test_until_a_programme_ends(self):
        rec = self.start(until=time.time() + 600).get_json()
        self.assertAlmostEqual(rec["stop"], time.time() + 600, delta=5)
        self.assertEqual(self.start(until=time.time() - 5).status_code, 400)  # already over
        self.assertEqual(self.start(minutes=-1).status_code, 400)
        self.assertEqual(self.start(minutes="soon").status_code, 400)

    def test_refusals_say_why(self):
        self.responses = [FakeResponse(503, body={"error": recordings.TUNER_BUSY})]
        response = self.start()
        self.assertEqual(response.status_code, 503)
        self.assertIn("No free tuner", response.get_json()["error"])
        self.assertEqual(self.client.post("/recordings/start", json={"portal": "nope", "channelId": "2"}).status_code, 404)
        self.app.getSettings()["recordings folder"] = ""
        self.assertIn("Recording is off", self.start().get_json()["error"])

    def test_file_route_only_serves_known_recordings(self):
        for path in ("/recordings/nope/file", "/recordings/..%2F..%2Fconfig.json/file", "/recordings/nope/stop",
                     "/recordings/nope/delete"):
            method = self.client.get if path.endswith("file") else self.client.post
            self.assertEqual(method(path).status_code, 404, path)

    def test_the_folder_setting_is_saved_trimmed(self):
        form = {k: v for k, v in self.app.getSettings().items() if k != "api token"}
        form["recordings folder"] = "  /mnt/recordings  "
        self.client.post("/settings/save", data=form)
        self.assertEqual(self.app.getSettings()["recordings folder"], "/mnt/recordings")
        self.assertIn('name="recordings folder"', self.client.get("/settings").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_app_recordings -v`
Expected: the tests ERROR with `AttributeError: module 'app' has no attribute 'recordingUrl'`, or with 404s.

- [ ] **Step 3: Implement**

In `app.py`:

- Add `import recordings` after `import logos`, and `import shutil` after `import os`.
- Replace `TUNER_BUSY = "All tuners are busy"` with `TUNER_BUSY = recordings.TUNER_BUSY`.
- Add `"recordings folder": "",` to `defaultSettings`, after `"jellyfin api key": "",`.

After `saveBlocks`:

```python
# The recorder, made on first use so tests can load the app against their own config.
recorder = None
recorderLock = threading.Lock()


def recordingUrl(portal, channelId, id):
    # A recording reads from /play like Plex does, so it shares streams and tuners.
    return "http://127.0.0.1:8001/play/{}/{}?recording={}".format(portal, channelId, id)


def getRecorder():
    global recorder
    with recorderLock:
        if recorder is None:
            store = recordings.RecordingStore(
                os.path.join(os.path.dirname(os.path.abspath(configFile)), "recordings.json"), logger)
            recorder = recordings.Recorder(
                store, lambda: getSettings().get("recordings folder", "").strip(), recordingUrl, logger)
        return recorder
```

In `save()` (`/settings/save`), before `saveSettings(settings)`:

```python
    settings["recordings folder"] = request.form.get("recordings folder", "").strip()
```

After the `/multiview` route:

```python
@app.route("/recordings/list", methods=["GET"])
@authorise
def recordingsList():
    folder = getSettings().get("recordings folder", "").strip()
    free = None
    if folder:
        try:
            free = shutil.disk_usage(folder).free
        except OSError:
            pass
    return flask.jsonify({"recordings": getRecorder().list(), "folder": folder, "free": free})


@app.route("/recordings/start", methods=["POST"])
@authorise
def recordingsStart():
    """Record a channel now. JSON: {portal, channelId, name, minutes?} or {..., until?}."""
    data = request.get_json(force=True, silent=True) or {}
    portal = str(data.get("portal", ""))
    channelId = str(data.get("channelId", ""))
    if portal not in getPortals() or not channelId:
        return flask.jsonify({"error": "Unknown channel"}), 404
    name = str(data.get("name") or channelId)[:100]
    stop = None
    try:
        if data.get("minutes") is not None:
            minutes = float(data["minutes"])
            if not 0 < minutes <= 24 * 60:
                raise ValueError
            stop = time.time() + minutes * 60
        elif data.get("until") is not None:
            stop = float(data["until"])
            if not time.time() < stop <= time.time() + 24 * 3600:
                raise ValueError
    except (TypeError, ValueError):
        return flask.jsonify({"error": "Record for up to 24 hours, ending in the future"}), 400
    try:
        rec = getRecorder().start(portal, channelId, name, stop=stop)
    except recordings.RecordingError as e:
        return flask.jsonify({"error": str(e)}), 503
    return flask.jsonify(rec)


@app.route("/recordings/<id>/stop", methods=["POST"])
@authorise
def recordingsStop(id):
    if not getRecorder().stop(id):
        return flask.jsonify({"error": "That recording isn't running"}), 404
    return flask.jsonify({"stopping": True})


@app.route("/recordings/<id>/delete", methods=["POST"])
@authorise
def recordingsDelete(id):
    rec = getRecorder().store.get(id)
    if not rec:
        return flask.jsonify({"error": "No such recording"}), 404
    if not getRecorder().delete(id):
        return flask.jsonify({"error": "Stop it before deleting it"}), 409
    logger.info("Recording({}) deleted".format(id))
    return flask.jsonify({"deleted": True})


@app.route("/recordings/<id>/file", methods=["GET"])
@authorise
def recordingsFile(id):
    # Only a file the recorder wrote: the path comes from the recording, never the request.
    rec = getRecorder().store.get(id)
    if not rec or not rec.get("file") or not os.path.isfile(rec["file"]):
        return flask.jsonify({"error": "No such recording"}), 404
    return flask.send_file(rec["file"], mimetype="video/mp4", conditional=True,
                           as_attachment=request.args.get("download") == "1",
                           download_name=os.path.basename(rec["file"]))
```

In `if __name__ == "__main__":`, right after `config = loadConfig()`:

```python
    getRecorder().resume()  # carry on recordings that were running when STB-Proxy stopped
```

In `Dockerfile`, after `COPY /logos.py /app/logos.py`:

```
COPY /recordings.py /app/recordings.py
```

In `templates/settings.html` (keep CRLF), before the `<h4>Plex</h4>` line:

```html
    <h4>Recording</h4>
    <hr>
    <div class="p-sm-3">

        <h6>Recordings folder:</h6>
        <div class="col-md-6">
            <input form="save" type="text" name="recordings folder" id="recordings folder" class="form-control"
                value="{{ settings['recordings folder'] }}" placeholder="/mnt/recordings">
        </div>
        <span class="text-muted">Where recordings are saved: a folder STB-Proxy can write to, such as a mounted share. Empty turns recording off. Starting a recording needs 1 GB free there, and a recording stops when less than 300 MB is left.</span>

    </div>

    <br>

```

- [ ] **Step 4: Run the tests, then everything**

Run: `.venv/bin/python -m unittest tests.test_app_recordings -v`
Expected: all 6 pass.
Run: `.venv/bin/python -m unittest 2>&1 | tail -3`
Expected: `OK`. That includes `test_dockerfile_copies_every_local_module_app_imports`.

- [ ] **Step 5: Commit**

```bash
git add app.py Dockerfile templates/settings.html tests/test_app_recordings.py
git commit -m "Record channels from the app: setting, routes, resume

A recordings folder setting (empty: recording off), JSON routes to start a
recording now (until stopped, for some minutes, or until a time), list, stop,
delete and play or download it, and recordings carry on after a restart.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The Recordings page

**Files:**
- Create: `static/recordings.js`, with the formatting and record-menu helpers (the record
  helpers are used in Task 5)
- Create: `templates/recordings.html`
- Modify: `app.py`, adding a `/recordings` page route before `/recordings/list`
- Modify: `templates/base.html` (CRLF), adding a nav item after Multiview
- Create: `tests/test_recordings_js.py`
- Modify: `tests/test_templates.py`, `tests/test_app_recordings.py`
- Modify: `README.md`, adding a "# Recording" section after "# Multiview"

**Interfaces:**
- Consumes (Task 3): `GET /recordings/list`, `POST /recordings/<id>/stop`,
  `POST /recordings/<id>/delete` and `GET /recordings/<id>/file`.
- Produces a browser global `stbRecordings` (or `require` under node) with:
  - `formatSize(bytes) -> str`
  - `formatDuration(seconds) -> str`
  - `recordOptions(now, programme) -> [{label, minutes?, until?}]`, where `programme` is
    `{title, stop}` or null
  - `recordingChannels(recordings) -> {"portal/channelId": id}` for those with status `recording`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recordings_js.py`:

```python
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "static", "recordings.js")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RecordingsScriptTest(unittest.TestCase):
    def run_js(self, body):
        script = "const r = require(%s); console.log(JSON.stringify((() => { %s })()));" % (json.dumps(SCRIPT), body)
        return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)

    def test_sizes_and_durations_read_naturally(self):
        self.assertEqual(self.run_js("return [0, 900, 1536 * 1024, 3.5 * 1024 ** 3].map(r.formatSize);"),
                         ["0 KB", "1 KB", "1.5 MB", "3.5 GB"])
        self.assertEqual(self.run_js("return [0, 59, 61, 3600, 5430].map(r.formatDuration);"),
                         ["0:00", "0:59", "1:01", "1:00:00", "1:30:30"])

    def test_record_options_offer_the_programme_on_now(self):
        options = self.run_js("return r.recordOptions(1000, {title: 'Game', stop: 4600});")
        self.assertEqual([o["label"] for o in options],
                         ["Until I stop it", "Until Game ends", "30 minutes", "1 hour", "2 hours"])
        self.assertEqual((options[1]["until"], options[2]["minutes"]), (4600, 30))
        self.assertEqual(len(self.run_js("return r.recordOptions(1000, {title: 'Over', stop: 900});")), 4)
        self.assertEqual(len(self.run_js("return r.recordOptions(1000, null);")), 4)

    def test_which_channels_are_recording(self):
        recs = [{"id": "a", "portal": "p1", "channelId": "2", "status": "recording"},
                {"id": "b", "portal": "p1", "channelId": "3", "status": "done"}]
        self.assertEqual(self.run_js("return r.recordingChannels(%s);" % json.dumps(recs)), {"p1/2": "a"})


if __name__ == "__main__":
    unittest.main()
```

In `tests/test_templates.py`, add to `TemplateScriptTest`:

```python
    def test_recordings_script_is_valid_javascript(self):
        self.assertValidJavaScript("recordings.html")
```

In `tests/test_app_recordings.py`, add to `RecordingRoutesTest`:

```python
    def test_recordings_page_and_menu(self):
        body = self.client.get("/recordings").get_data(as_text=True)
        self.assertIn('id="nowList"', body)
        self.assertIn('id="doneList"', body)
        self.assertIn("recordings.js", body)
        self.assertIn('href="/recordings"', self.client.get("/guide").get_data(as_text=True))
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_recordings_js tests.test_templates tests.test_app_recordings -v`
Expected:
- the node tests ERROR (no `static/recordings.js`);
- `test_recordings_script_is_valid_javascript` ERRORs (no template);
- `test_recordings_page_and_menu` FAILs with a 404 body.

- [ ] **Step 3: Implement `static/recordings.js`**

```javascript
// Recording helpers for the Recordings page, the preview player and Multiview (also loaded
// by tests under node).
(function (root) {
    function formatSize(bytes) {
        if (bytes >= Math.pow(1024, 3)) {
            return (bytes / Math.pow(1024, 3)).toFixed(1).replace(/\.0$/, "") + " GB";
        }
        if (bytes >= 1024 * 1024) {
            return (bytes / 1024 / 1024).toFixed(1).replace(/\.0$/, "") + " MB";
        }
        return Math.round(bytes / 1024) + " KB";
    }

    function formatDuration(seconds) {
        seconds = Math.max(0, Math.round(seconds));
        var h = Math.floor(seconds / 3600);
        var m = Math.floor(seconds % 3600 / 60);
        var s = seconds % 60;
        var mm = h ? (m < 10 ? "0" : "") + m : String(m);
        return (h ? h + ":" : "") + mm + ":" + (s < 10 ? "0" : "") + s;
    }

    // How long to record: until stopped, until the programme on now ends (if known), or a while.
    function recordOptions(now, programme) {
        var options = [{ label: "Until I stop it" }];
        if (programme && programme.stop > now) {
            options.push({ label: "Until " + programme.title + " ends", until: programme.stop });
        }
        options.push({ label: "30 minutes", minutes: 30 });
        options.push({ label: "1 hour", minutes: 60 });
        options.push({ label: "2 hours", minutes: 120 });
        return options;
    }

    // "portal/channelId" -> recording id, for every channel being recorded now.
    function recordingChannels(recordings) {
        var keys = {};
        recordings.forEach(function (rec) {
            if (rec.status == "recording") {
                keys[rec.portal + "/" + rec.channelId] = rec.id;
            }
        });
        return keys;
    }

    var api = {
        formatSize: formatSize,
        formatDuration: formatDuration,
        recordOptions: recordOptions,
        recordingChannels: recordingChannels,
    };
    root.stbRecordings = api;
    if (typeof module !== "undefined") {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : this);
```

- [ ] **Step 4: The page, its route and the menu item**

In `app.py`, before the `/recordings/list` route:

```python
@app.route("/recordings", methods=["GET"])
@authorise
def recordingsPage():
    return render_template("recordings.html", folder=getSettings().get("recordings folder", "").strip())
```

In `templates/base.html` (keep CRLF), after the Multiview `<li class="nav-item">…</li>`:

```html
                    <li class="nav-item">
                        <a class="nav-link" href="/recordings"><i class="fa fa-circle text-danger"></i> Recordings</a>
                    </li>
```

Create `templates/recordings.html`:

```html
{% extends "base.html" %}
{% block content %}

<style>
    .nav-tabs .nav-link.active {
        background-color: #2c3034;
        border-color: #495057 #495057 #2c3034;
        color: #f8f9fa;
    }
    .nav-tabs {
        border-bottom-color: #495057;
    }
</style>

<div class="container text-light p-lg-5">
    <div class="d-flex align-items-center flex-wrap mb-2">
        <h4 class="mb-0 me-3">Recordings</h4>
        <span class="small text-muted" id="freeSpace"></span>
    </div>

    {% if not folder %}
    <div class="alert alert-secondary">Recording is off. Choose a recordings folder in <a href="/settings">Settings</a>,
        then record from a Multiview tile or the preview player (<i class="fa fa-circle text-danger"></i>).</div>
    {% endif %}
    <div id="listError" class="alert alert-danger d-none">Couldn't load the recordings. Retrying...</div>

    <ul class="nav nav-tabs mb-3" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#nowTab" type="button" role="tab">
                <i class="fa fa-circle text-danger"></i> Recording now <span class="badge bg-secondary" id="nowCount">0</span></button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#doneTab" type="button" role="tab">
                <i class="fa fa-film"></i> Recorded <span class="badge bg-secondary" id="doneCount">0</span></button>
        </li>
    </ul>

    <div class="tab-content">
        <div class="tab-pane fade show active" id="nowTab" role="tabpanel"><div id="nowList"></div></div>
        <div class="tab-pane fade" id="doneTab" role="tabpanel"><div id="doneList"></div></div>
    </div>
</div>

<div class="modal fade" id="playModal" tabindex="-1" aria-labelledby="playTitle" aria-hidden="true">
    <div class="modal-dialog modal-xl">
        <div class="modal-content bg-dark text-light">
            <div class="modal-header">
                <h5 class="modal-title text-truncate" id="playTitle">Recording</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <video id="playVideo" class="d-block w-100 bg-black" controls playsinline></video>
        </div>
    </div>
</div>

<script src="{{ url_for('static', filename='recordings.js') }}"></script>
<script>
    var all = [];
    var playModal = null;

    function escapeAttr(s) {
        return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function when(seconds) {
        var d = new Date(seconds * 1000);
        return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) + " " +
            d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }

    function load() {
        $.getJSON("/recordings/list")
            .done(function (res) {
                document.getElementById("listError").classList.add("d-none");
                all = res.recordings;
                document.getElementById("freeSpace").textContent = res.folder
                    ? res.folder + (res.free !== null ? ": " + stbRecordings.formatSize(res.free) + " free" : ": can't be read")
                    : "";
                render();
            })
            .fail(function () {
                document.getElementById("listError").classList.remove("d-none");
            });
    }

    function render() {
        var now = all.filter(function (r) { return r.status == "recording"; });
        var done = all.filter(function (r) { return r.status != "recording"; });
        document.getElementById("nowCount").textContent = now.length;
        document.getElementById("doneCount").textContent = done.length;
        document.getElementById("nowList").innerHTML = now.length ? table(
            ["Channel", "Started", "Recorded", "Size", "Until", ""],
            now.map(function (r) {
                return [escapeAttr(r.title), when(r.start), stbRecordings.formatDuration(Date.now() / 1000 - r.start),
                    stbRecordings.formatSize(r.size),
                    (r.stop ? when(r.stop) : "Stopped by hand") +
                    (r.waiting ? '<div class="small text-warning">' + escapeAttr(r.error || "Waiting for the channel") + '</div>' : ''),
                    '<button type="button" class="btn btn-sm btn-danger" onclick="stopRecording(\'' + r.id + '\')"><i class="fa fa-stop"></i> Stop</button>'];
            })) : '<p class="text-muted">Nothing is recording. Record from a Multiview tile or the preview player (<i class="fa fa-circle text-danger"></i>).</p>';
        document.getElementById("doneList").innerHTML = done.length ? table(
            ["Title", "Recorded", "Length", "Size", "", ""],
            done.map(function (r) {
                var badge = r.status == "done" ? "" : '<span class="badge ' + (r.status == "partial" ? "bg-warning text-dark" : "bg-danger") + ' ms-1">' +
                    r.status + (r.gaps.length ? ": " + r.gaps.length + " gap" + (r.gaps.length > 1 ? "s" : "") : "") + '</span>';
                return [escapeAttr(r.title) + badge + (r.error ? '<div class="small text-muted">' + escapeAttr(r.error) + '</div>' : ''),
                    when(r.start), stbRecordings.formatDuration((r.ended || r.start) - r.start), stbRecordings.formatSize(r.size),
                    r.file ? '<button type="button" class="btn btn-sm btn-success me-1" onclick="playRecording(\'' + r.id + '\')"><i class="fa fa-play"></i></button>' +
                        '<a class="btn btn-sm btn-outline-light" title="Download" href="/recordings/' + r.id + '/file?download=1"><i class="fa fa-download"></i></a>' : '',
                    '<button type="button" class="btn btn-sm btn-outline-danger" title="Delete" onclick="deleteRecording(\'' + r.id + '\')"><i class="fa fa-trash"></i></button>'];
            })) : '<p class="text-muted">No recordings yet.</p>';
    }

    function table(headings, rows) {
        return '<div class="table-responsive"><table class="table table-dark table-striped align-middle"><thead><tr>' +
            headings.map(function (h) { return '<th>' + h + '</th>'; }).join("") + '</tr></thead><tbody>' +
            rows.map(function (cells) { return '<tr>' + cells.map(function (c) { return '<td>' + c + '</td>'; }).join("") + '</tr>'; }).join("") +
            '</tbody></table></div>';
    }

    function find(id) {
        return all.filter(function (r) { return r.id == id; })[0];
    }

    function stopRecording(id) {
        var r = find(id);
        if (r && confirm("Stop recording " + r.title + "? What's recorded so far is kept.")) {
            $.post("/recordings/" + id + "/stop").always(function () { setTimeout(load, 1000); });
        }
    }

    function deleteRecording(id) {
        var r = find(id);
        if (r && confirm("Delete " + r.title + " (" + when(r.start) + ")? This can't be undone.")) {
            $.post("/recordings/" + id + "/delete")
                .fail(function (xhr) { alert((xhr.responseJSON && xhr.responseJSON.error) || "Couldn't delete it."); })
                .always(load);
        }
    }

    function playRecording(id) {
        var r = find(id);
        document.getElementById("playTitle").textContent = r.title + " · " + when(r.start);
        var video = document.getElementById("playVideo");
        video.src = "/recordings/" + id + "/file";
        if (!playModal) {
            playModal = new bootstrap.Modal(document.getElementById("playModal"));
            document.getElementById("playModal").addEventListener("hidden.bs.modal", function () {
                video.pause();
                video.removeAttribute("src");
                video.load();
            });
        }
        playModal.show();
        video.play().catch(function () { });
    }

    load();
    setInterval(load, 10000);
</script>

{% endblock %}
```

- [ ] **Step 5: Document it**

In `README.md`, add after the "# Multiview" section, before "# Channel logos":

```markdown
# Recording

- Set **Recordings folder** in Settings → Recording to a folder STB-Proxy can write to, such as a mounted share. Empty turns recording off.
- Record from a Multiview tile or the preview player with the red ⏺ button. Choose how long: until you stop it, until the programme on now ends, or 30 minutes, 1 hour or 2 hours.
- A recording shares the channel with anything else watching it, so watching what you record uses no extra tuner. It can take a tuner from a browser preview, never from Plex or another player.
- **Recordings** (in the menu) lists what's recording now, with **Stop**, and what's recorded. You can play recordings in the browser, download them or delete them. Files are saved as `Title/Title - date time.mp4`, so Plex or Jellyfin can use the folder as a library.
- If the portal drops the stream, the recording reopens it and carries on, and the recording is marked **partial**, with the gaps noted. It also carries on after STB-Proxy restarts.
- Starting a recording needs 1 GB free in the folder, and a recording stops, keeping what it has, when less than 300 MB is left.
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_recordings_js tests.test_templates tests.test_app_recordings -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app.py static/recordings.js templates/recordings.html templates/base.html tests/test_recordings_js.py tests/test_templates.py tests/test_app_recordings.py README.md
git commit -m "Add the Recordings page

Lists what's recording now, with Stop, and what's recorded, with play in the
browser, download and delete, plus free space in the recordings folder.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Record buttons in Multiview and the preview player

**Files:**
- Create: `templates/_record_modal.html`, the "how long" menu and start/stop calls
- Modify:
  - `templates/multiview.html`: a ⏺ button per tile, polling which channels are recording,
    and including the menu
  - `templates/_player.html` (CRLF): a ⏺ button in the header, and including the menu
  - `tests/test_templates.py`
- Then a browser check, and a live check on the container

**Interfaces:**
- Consumes:
  - `stbRecordings.recordOptions` and `stbRecordings.recordingChannels` (Task 4)
  - `POST /recordings/start`, `POST /recordings/<id>/stop` and `GET /recordings/list` (Task 3)
- Produces these globals from `_record_modal.html`:
  - `openRecordMenu(ch, name, programme, done)`
  - `stopRecording(id, done)` is defined only on pages that include the modal. Note: the
    Recordings page has its own `stopRecording(id)` and doesn't include the modal.

- [ ] **Step 1: Write the failing tests**

In `tests/test_templates.py`, add to `TemplateScriptTest`:

```python
    def test_record_menu_script_is_valid_javascript(self):
        self.assertValidJavaScript("_record_modal.html")

    def test_tiles_and_player_can_record(self):
        mv = inlineScripts("multiview.html")
        self.assertIn("openRecordMenu(", mv)
        self.assertIn("stbRecordings.recordingChannels(", mv)
        player = inlineScripts("_player.html")
        self.assertIn("openRecordMenu(", player)
        for template in ("multiview.html", "_player.html"):
            with open(os.path.join(ROOT, "templates", template)) as f:
                self.assertIn('{% include "_record_modal.html" %}', f.read())
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_templates -v`
Expected: the two new tests FAIL or ERROR, because there's no `_record_modal.html` and no `openRecordMenu`.

- [ ] **Step 3: Create `templates/_record_modal.html`**

```html
<!-- Record a channel now: how long. Included by the preview player and Multiview. -->
<div class="modal fade" id="recordModal" tabindex="-1" aria-labelledby="recordTitle" aria-hidden="true">
    <div class="modal-dialog modal-sm">
        <div class="modal-content bg-dark text-light">
            <div class="modal-header">
                <h5 class="modal-title text-truncate" id="recordTitle">Record</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <div id="recordOptions" class="list-group"></div>
                <div id="recordStatus" class="small mt-2"></div>
            </div>
        </div>
    </div>
</div>

<script src="{{ url_for('static', filename='recordings.js') }}"></script>
<script>
    var recordModal = null;

    // Ask how long to record ch ({portal, channelId}), named name. programme is the one on
    // now ({title, stop}) or null. done(rec) runs once it has started.
    function openRecordMenu(ch, name, programme, done) {
        document.getElementById("recordTitle").textContent = "Record " + name;
        var status = document.getElementById("recordStatus");
        status.textContent = "";
        var box = document.getElementById("recordOptions");
        box.innerHTML = "";
        stbRecordings.recordOptions(Date.now() / 1000, programme).forEach(function (option) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "list-group-item list-group-item-action bg-dark text-light";
            button.textContent = option.label;
            button.addEventListener("click", function () {
                status.className = "small mt-2 text-muted";
                status.textContent = "Starting...";
                $.ajax({
                    url: "/recordings/start", method: "POST", contentType: "application/json",
                    data: JSON.stringify({ portal: ch.portal, channelId: ch.channelId, name: name, minutes: option.minutes, until: option.until }),
                })
                    .done(function (rec) {
                        recordModal.hide();
                        if (done) {
                            done(rec);
                        }
                    })
                    .fail(function (xhr) {
                        status.className = "small mt-2 text-danger";
                        status.textContent = (xhr.responseJSON && xhr.responseJSON.error) || "Couldn't start recording. Try again.";
                    });
            });
            box.appendChild(button);
        });
        if (!recordModal) {
            recordModal = new bootstrap.Modal(document.getElementById("recordModal"));
        }
        recordModal.show();
    }

    function stopRecording(id, done) {
        $.post("/recordings/" + encodeURIComponent(id) + "/stop").always(function () {
            if (done) {
                done();
            }
        });
    }
</script>
```

- [ ] **Step 4: Multiview tiles**

In `templates/multiview.html`:

- Right after the channel picker modal (just before the `<!-- Blocks that are on, for the picker's Blocks tab. -->` comment), add:

```html
{% include "_record_modal.html" %}
```

- In `buildTiles`, add a record button as the first header button, before `tile-audio`:

```javascript
                '<button type="button" class="btn btn-sm btn-outline-light tile-record d-none" title="Record" aria-label="Record"><i class="fa fa-circle text-danger"></i></button>' +
```

- In `wireTile`, add:

```javascript
        t.el.querySelector(".tile-record").addEventListener("click", function (e) {
            e.stopPropagation();
            recordClicked(i);
        });
```

- In `showGuide`, after `var line = ...` is set, keep the programme on now for the record menu:

```javascript
        tiles[i].programme = current;
```

- Add after `setAudio`:

```javascript
    // ---- Recording: which channels are recording, and each tile's record button
    var recordingKeys = {};
    var recordingOn = false;

    function refreshRecordings() {
        $.getJSON("/recordings/list").done(function (res) {
            recordingOn = !!res.folder;
            recordingKeys = stbRecordings.recordingChannels(res.recordings);
            for (var i = 0; i < multiview.TILES; i++) {
                showRecordButton(i);
            }
        });
    }

    function showRecordButton(i) {
        var button = tiles[i].el.querySelector(".tile-record");
        var ch = state.tiles[i];
        var recording = ch && recordingKeys[channelKey(ch)];
        button.classList.toggle("d-none", !recordingOn || !ch);
        button.classList.toggle("btn-danger", !!recording);
        button.classList.toggle("btn-outline-light", !recording);
        button.title = recording ? "Recording: click to stop" : "Record";
        button.setAttribute("aria-label", button.title);
        button.querySelector("i").className = "fa " + (recording ? "fa-stop" : "fa-circle text-danger");
    }

    function recordClicked(i) {
        var ch = state.tiles[i];
        var row = rowFor(ch);
        if (!ch || !row) {
            return;
        }
        var id = recordingKeys[channelKey(ch)];
        if (id) {
            if (confirm("Stop recording " + multiview.channelName(row) + "? What's recorded so far is kept.")) {
                stopRecording(id, refreshRecordings);
            }
            return;
        }
        openRecordMenu(ch, multiview.channelName(row), tiles[i].programme || null, refreshRecordings);
    }

    setInterval(refreshRecordings, 15000);
```

- At the end of `renderTile`, add `showRecordButton(i);`.
- At the end of the script, after `loadChannels()...`, add `refreshRecordings();`.

- [ ] **Step 5: The preview player**

In `templates/_player.html` (keep CRLF):

- Before the `#multiviewButton` button in the header:

```html
        <button type="button" class="btn btn-sm btn-outline-light ms-1 d-none" id="recordButton"
            onclick="recordClicked()" title="Record" aria-label="Record"><i class="fa fa-circle text-danger"></i></button>
```

- After the closing `</div>` of the `#channelGuideModal` modal, before `<script src=...multiview.js`:

```html
{% include "_record_modal.html" %}
```

- In the main script, after `sendToMultiview`:

```javascript
    // ---- Recording what's playing
    var playerRecording = null;  // the recording id of the channel playing, if it's being recorded
    var playerRecordingOn = false;

    function refreshPlayerRecording() {
        var ch = currentChannel;
        $.getJSON("/recordings/list").done(function (res) {
            playerRecordingOn = !!res.folder;
            playerRecording = ch ? stbRecordings.recordingChannels(res.recordings)[channelKey(ch)] || null : null;
            var button = document.getElementById("recordButton");
            button.classList.toggle("d-none", !playerRecordingOn || !currentChannel);
            button.classList.toggle("btn-danger", !!playerRecording);
            button.classList.toggle("btn-outline-light", !playerRecording);
            button.title = playerRecording ? "Recording: click to stop" : "Record";
            button.querySelector("i").className = "fa " + (playerRecording ? "fa-stop" : "fa-circle text-danger");
        });
    }

    function programmeOnNow(ch) {
        var cached = guides[channelKey(ch)];
        var now = Date.now() / 1000;
        var current = null;
        (cached ? cached.programmes : []).forEach(function (p) {
            if (p.start <= now && p.stop > now) {
                current = p;
            }
        });
        return current;
    }

    function recordClicked() {
        if (!currentChannel) {
            return;
        }
        if (playerRecording) {
            if (confirm("Stop recording " + title.textContent + "? What's recorded so far is kept.")) {
                stopRecording(playerRecording, refreshPlayerRecording);
            }
            return;
        }
        openRecordMenu(currentChannel, title.textContent, programmeOnNow(currentChannel), refreshPlayerRecording);
    }

    setInterval(function () {
        if (currentChannel) {
            refreshPlayerRecording();
        }
    }, 15000);
```

- In `playChannel(ch)`, after `markPlaying();`, add `refreshPlayerRecording();`.

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/python -m unittest 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 7: Browser check (local test config)**

Make a scratchpad config with `"recordings folder": "<scratchpad>/rec"` and a `.invalid`
portal. Run the app as in the earlier plans. Check:

- **`/recordings`** shows the folder and its free space, with both tabs empty.
- **Folder setting:** with it empty, `/recordings` says recording is off. Multiview tiles
  and the player show no ⏺ button.
- **Multiview:** with a stand-in channel in a tile (as in the earlier browser checks),
  the ⏺ button opens the menu with the options.
  - **Choosing "30 minutes"** shows the server's refusal ("The channel didn't start..."),
    because the portal is unreachable.
- **Phone width:** at 375 px, the Recordings tables scroll inside themselves and the page
  doesn't scroll sideways.

- [ ] **Step 8: Commit**

```bash
git add templates/_record_modal.html templates/multiview.html templates/_player.html tests/test_templates.py
git commit -m "Record from Multiview tiles and the preview player

A red record button on each tile and in the player asks how long: until
stopped, until the programme on now ends, or 30 minutes to 2 hours. While a
channel records, its button stops the recording.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## After the tasks

1. **Before deploying,** ask the user. Then, only when `/streaming` is empty: back up the
   config, deploy, and set the user's `recordings folder` setting to `/tmp/stb-recordings`,
   as the user asked on 2026-10-08. The folder is on the container's 3 GB root disk.
2. **Live check:** record one lineup channel for 1 minute ("30 minutes", then Stop after
   a minute). Then check:
   - the MP4 plays in the browser from `/recordings`;
   - while it records, `/streaming` shows one stream with the kinds `["recording"]`;
   - opening the same channel in Multiview adds no stream, and the kinds become
     `["preview", "recording"]`;
   - deleting it removes the file.
3. **Merging:** PR on the fork, then merge, if the user says so.
