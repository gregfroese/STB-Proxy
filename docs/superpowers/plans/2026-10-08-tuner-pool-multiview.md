# Tuner Pool and Multiview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one browser watch several channels at once on a new Multiview page, with all
portal connections ("tuners") shared through one pool where Plex and other players outrank
recordings, and recordings outrank browser previews.

**Architecture:**
- **`/play`** decides, per request, what kind of viewer is asking: preview (`web=true`),
  recording (`recording=<id>`), or client (anything else).
  - Previews are keyed by browser and tile (`viewer` + `tile` query parameters) instead of
    by browser and portal.
  - Before opening a new channel, `makeRoom()` enforces the tuners setting and the portal's
    streams per MAC. When it has to, it stops lower-priority streams, oldest first.
  - When a tile's preview is stopped or refused, it records why. The page reads that from
    `/preview/status`.
- **Multiview page** (`/multiview`): a CSS grid of nine permanent tiles, positioned with
  CSS `order`. Its state lives in localStorage, through a small, node-testable helper file
  (`static/multiview.js`).
- **Preview player** in the corner gets "Send to Multiview" and explains why a preview was
  refused.

**Tech Stack:** Python 3 / Flask (single `app.py`), unittest, Jinja templates, Bootstrap
5.0.1, jQuery 3.6 (from the DataTables bundle), Font Awesome 4.7, vanilla ES5-style
JavaScript, node (for JS tests and syntax checks).

**Spec:** `docs/superpowers/specs/2026-10-08-multiview-recording-design.md`. This plan is
PR 1 of 3 and covers spec sections 1 (tuner pool) and 3 (Multiview). Recording (section 2)
is PRs 2 and 3. The pool accepts `recording=<id>` so PR 2 only has to call `/play`.

## Global Constraints

- **Capacity:** the `hdhr tuners` setting is the number of distinct channels open at once,
  across all portals. A channel shared by several viewers counts once.
- **Priority:** Plex/Jellyfin/apps ("client") > recordings > browser previews.
  - A higher priority may stop a stream whose viewers are all lower priority.
  - Previews never stop anything.
  - A stream nobody is watching (lingering for a quick reconnect) counts as the lowest
    priority.
- **Refusals:** a request that can't get a tuner gets HTTP 503 with JSON
  `{"error": "All tuners are busy"}`.
- **Tile ids:** the corner preview player is tile `player`; Multiview tiles are `t0` to `t8`.
- **Redirect stream method:** streams it sends to clients aren't counted. Previews and
  recordings always use ffmpeg.
- **Copy:** user-visible text is plain and short, in the existing UI's voice. Commit
  messages and PR text never name the user's blocks, channels, portals, MACs, IPs or IDs
  (the fork is public).
- **Tests:** run them with `.venv/bin/python -m unittest ...` from the repo root. JS tests
  need `node`, and are skipped without it.
- **Commits:** every commit message ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **More tiles than tuners after a reload.** Excess tiles must settle on "No free tuner"
   once, not keep retrying and churning the portal. Pinned by
   `test_busy_and_stopped_tiles_are_not_retried_automatically` (Task 3).
2. **Closing a tile or the tab** must free its tuner at once, not after the linger grace.
   Pinned by `test_closing_a_tile_frees_its_tuner_at_once` (Task 2).
3. **The same channel in two tiles** (or a channel Plex is watching) must use one tuner.
   Pinned by `test_two_tiles_on_one_channel_share_a_tuner` (Task 2).
4. **Stale or corrupt localStorage** (garbage JSON, wrong shapes, storage that throws) must
   load the default layout, never break the page. Pinned by
   `test_garbage_or_unreadable_storage_gives_the_defaults` (Task 3).
5. **A Tuners setting of "0", "" or "abc"** must count as 1, never crash `/play`. Pinned by
   `test_a_bad_tuners_setting_counts_as_one` (Task 2).

---

### Task 1: Previews per tile, and the kind of each viewer

**Files:**
- Modify: `app.py` — the `previews` comment (around lines 61–63), `SharedStream.join` and
  `SharedStream.count`, `watchPreview`, `stopPreview`, and the start of `playChannel`
  through its stream branches (around lines 2030–2120)
- Create: `tests/test_app_tuners.py`

**Interfaces:**
- Produces:
  - `SharedStream.join(ip, kind="client", tile=None)`: `kind` is one of `"client"`,
    `"recording"` or `"preview"`; `tile` is a `(viewerId, tileId)` tuple for previews.
  - Each viewer dict has keys `queue`, `ip`, `kind` and `tile`.
  - `occupied` entries get `"kinds"`, a sorted list of the viewer kinds.
  - `watchPreview(stream, viewer, tile)` and `stopPreview(tile)`, where `tile` is
    `(viewerId, tileId)`. `previews` is keyed by that tuple.
  - `/play` accepts `tile=<id>` (default `player`) and `recording=<id>`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_tuners.py`:

```python
import threading
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig
from tests.test_app_preview import FakeProcess

CHANNELS = [{"id": i, "name": "Channel " + i, "cmd": "ffrt http://localhost/ch/" + i} for i in ("2", "3", "4", "5")]


class TunerTestCase(unittest.TestCase):
    """Two tuners, and a portal allowing two streams on its one MAC, unless a test changes them."""

    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{"streams per mac": "2"})},
            "settings": {"test streams": "false", "hdhr tuners": "2"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        self.app.SHARE_GRACE = 0.3
        for target, name, kwargs in [
            (self.app.subprocess, "Popen", {"side_effect": lambda cmd, **kw: FakeProcess(cmd)}),
            (self.app.stb, "getAllChannels", {"return_value": CHANNELS}),
            (self.app.stb, "getLink", {"return_value": "http://stream.test/live"}),
            (self.app, "moveMac", {}),
        ]:
            patcher = mock.patch.object(target, name, **kwargs)
            started = patcher.start()
            if name == "moveMac":
                self.moveMac = started
            self.addCleanup(patcher.stop)
        self.addCleanup(self.stopAll)

    def stopAll(self):
        for tile in list(self.app.previews):
            self.app.stopPreview(tile)
        for stream in list(self.app.sharedStreams.values()):
            stream.end()

    def play(self, channel, tile=None, viewer="browser1", ip="10.0.0.7", recording=None):
        """Request a channel and, if it plays, keep reading it in the background like a player."""
        query = []
        if tile is not None:
            query += ["web=true", "viewer=" + viewer, "tile=" + tile]
        if recording:
            query.append("recording=" + recording)
        path = "/play/{}/{}".format(PORTAL, channel) + ("?" + "&".join(query) if query else "")
        response = self.client.get(path, environ_base={"REMOTE_ADDR": ip})
        if response.status_code == 200:
            chunks = iter(response.response)
            next(chunks)
            threading.Thread(target=lambda: [None for _ in chunks], daemon=True).start()
        return response

    def open(self):
        """The channels with a stream open, sorted."""
        return sorted(key[1] for key, s in list(self.app.sharedStreams.items()) if not s.done)

    def entry(self, channel):
        return next(e for e in self.app.occupied.get(PORTAL, []) if e["channel id"] == channel)


class PreviewTilesTest(TunerTestCase):
    def test_one_browser_can_preview_in_several_tiles(self):
        self.assertEqual(self.play("2", tile="t0").status_code, 200)
        self.assertEqual(self.play("3", tile="t1").status_code, 200)
        self.assertEqual(self.open(), ["2", "3"])

    def test_a_tile_replaces_its_own_last_preview(self):
        self.play("2", tile="t0")
        self.play("3", tile="t0")
        self.assertEqual(self.open(), ["3"])
        self.moveMac.assert_not_called()

    def test_streams_list_who_is_watching(self):
        self.play("2", ip="10.0.0.5")
        self.play("2", tile="t0")
        streaming = self.client.get("/streaming").get_json()[PORTAL]
        self.assertEqual(len(streaming), 1)
        self.assertEqual((streaming[0]["viewers"], streaming[0]["kinds"]), (2, ["client", "preview"]))

    def test_recordings_always_go_through_ffmpeg(self):
        self.app.getSettings()["stream method"] = "redirect"
        response = self.play("2", recording="r1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.entry("2")["kinds"], ["recording"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_app_tuners -v`
Expected:
- `test_one_browser_can_preview_in_several_tiles` fails: the second preview stops the
  first, so `open()` is `["3"]`.
- `test_streams_list_who_is_watching` errors with `KeyError: 'kinds'`.
- `test_recordings_always_go_through_ffmpeg` fails with a 302 redirect.

- [ ] **Step 3: Implement**

In `app.py`, replace the comment above `previews = {}`:

```python
# The browser preview each tile is watching, by (viewer id, tile id), so a new channel in
# that tile can stop it at once instead of waiting for its connection to close. The preview
# player is tile "player"; Multiview's tiles are "t0" to "t8".
previews = {}
```

In `class SharedStream`, replace `join` and `count`:

```python
    def join(self, ip, kind="client", tile=None):
        """kind: "client" (Plex, Jellyfin, apps), "recording" or "preview"; tile: a preview's
        (viewer id, tile id)."""
        viewer = {"queue": queue.Queue(VIEWER_BACKLOG), "ip": ip, "kind": kind, "tile": tile}
        with self.lock:
            if self.done:
                return None
            self.viewers.append(viewer)
            self.idleSince = None
            self.count()
        return viewer
```

```python
    def count(self):
        if self.entry is not None:
            self.entry["viewers"] = len(self.viewers)
            self.entry["kinds"] = sorted({v["kind"] for v in self.viewers})
```

Replace `watchPreview`'s signature, docstring and the two `previews` lines:

```python
def watchPreview(stream, viewer, tile):
    """A browser preview of a shared stream, as fragmented MP4, in tile (viewer id, tile id).
    The tile's next preview stops it (see stopPreview), and the stream closes at once if
    nobody else watches."""
    preview = {
        "stop": threading.Event(),
        "process": None,
        "leave": lambda: stream.leave(viewer, linger=False),  # the next channel may need the connection now
    }
    previews[tile] = preview
```

At the end of its `finally:`:

```python
        if previews.get(tile) is preview:
            previews.pop(tile, None)
```

Replace `stopPreview`:

```python
def stopPreview(tile):
    """Stop the preview playing in tile, (viewer id, tile id), so its portal connection is free."""
    preview = previews.pop(tile, None)
    if not preview:
        return
    preview["stop"].set()
    process = preview["process"]
    if process:
        process.kill()
    # Here rather than waiting for the preview's response to notice: it may be stuck
    # sending to the browser.
    preview["leave"]()
```

In `playChannel`, replace from `web = request.args.get("web")` through the line
`firstViewer = shared.join(ip)` with:

```python
    web = request.args.get("web")
    recording = request.args.get("recording")
    kind = "preview" if web else "recording" if recording else "client"
    ip = request.remote_addr
    # Each browser sends its own ID: behind a reverse proxy every viewer has the proxy's IP.
    viewer = request.args.get("viewer") or ip
    tile = (viewer, request.args.get("tile") or "player") if web else None

    logger.info(
        "IP({}) requested Portal({}):Channel({})".format(ip, portalId, channelId)
    )

    if web:
        stopPreview(tile)

    channelName = None  # set once a MAC is free; the fallback search below reads it
    shared = None
    if web or recording or getSettings().get("stream method", "ffmpeg") == "ffmpeg":
        key = (portalId, channelId)
        with sharedStreamsLock:
            existing = sharedStreams.get(key)
            if existing is not None and not existing.done:
                joined = existing.join(ip, kind, tile)
                if joined:
                    logger.info("IP({}) shares the stream already open for Portal({}):Channel({})".format(ip, portalId, channelId))
                    if web:
                        return Response(watchPreview(existing, joined, tile), mimetype="application/octet-stream")
                    return Response(watchShared(existing, joined), mimetype="application/octet-stream")
            shared = SharedStream(key)
            sharedStreams[key] = shared
        flask.g.startingShare = shared
        firstViewer = shared.join(ip, kind, tile)
```

Further down in the MAC loop, replace the stream-starting block inside `if link:`:

```python
        if link:
            # Previews skip the test: the browser retries, then offers Mark dead, by itself.
            if web or getSettings().get("test streams", "true") == "false" or testStream():
                if web:
                    cmd = ffmpegCommand(link, proxy, realTime=False)
                    startShared(shared, cmd, portalId, portalName, mac, channelId, channelName, ip)
                    return Response(watchPreview(shared, firstViewer, tile), mimetype="application/octet-stream")

                else:
                    if recording or getSettings().get("stream method", "ffmpeg") == "ffmpeg":
                        cmd = ffmpegCommand(link, proxy)
                        startShared(shared, cmd, portalId, portalName, mac, channelId, channelName, ip)
                        return Response(watchShared(shared, firstViewer), mimetype="application/octet-stream")
                    else:
                        logger.info("Redirect sent")
                        return redirect(link)
```

- [ ] **Step 4: Run the new tests and the existing stream tests**

Run: `.venv/bin/python -m unittest tests.test_app_tuners tests.test_app_preview tests.test_app_sharing -v`
Expected: all pass. The existing preview tests send no `tile`, so they use tile `player`,
and a browser's new preview still replaces its last one.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app_tuners.py
git commit -m "Let one browser preview in several tiles, and track who watches each stream

Previews are keyed by browser and tile (?tile=, default \"player\") instead of
by browser and portal, so a page can play several channels at once. Each
viewer of a shared stream is a client, a recording (?recording=) or a
preview, and /streaming lists the kinds. Recordings always go through ffmpeg.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The tuner pool

**Files:**
- Modify: `app.py`:
  - add constants and state after `sharedStreamsLock = threading.Lock()`
  - add `SharedStream.priority`
  - add `tunerCount`, `portalHasFreeSlot`, `noteOutcome`, `stopForRoom` and `makeRoom`
    after `stopPreview`
  - add the admission check in `playChannel`
  - add an outcome reset in `watchPreview`
  - add the `/preview/status` route after the `/play` route
  - add `tuners` and `viewers` to `/api/status`
- Modify: `README.md`, the "Streams and portal connections" section and the API table
- Modify: `tests/test_app_tuners.py`

**Interfaces:**
- Consumes (from Task 1): `SharedStream.join(ip, kind, tile)`, the viewer dict keys `kind`
  and `tile`, and `stopPreview(tile)`.
- Produces:
  - `KIND_PRIORITY = {"preview": 0, "recording": 1, "client": 2}`
  - `TUNER_BUSY = "All tuners are busy"`
  - `tunerCount() -> int`, at least 1
  - `makeRoom(portalId, kind, starting) -> bool`
  - `previewOutcomes`, a dict from `(viewerId, tileId)` to `{"reason", "time"}`
  - `GET /preview/status?viewer=<id>&tile=<id>` returns `{"reason": "busy" | "client" | "recording" | null}`
  - `/play` answers a request that can't get a tuner with 503 and `{"error": "All tuners are busy"}`
  - `/api/status` gains `"tuners": {"total": int, "used": int}` and
    `"viewers": {"client": int, "recording": int, "preview": int}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app_tuners.py`, above `if __name__ == "__main__":`:

```python
class TunerPoolTest(TunerTestCase):
    def reason(self, tile, viewer="browser1"):
        return self.client.get("/preview/status?viewer={}&tile={}".format(viewer, tile)).get_json()["reason"]

    def test_a_preview_never_stops_anything_and_the_tile_is_told(self):
        self.play("2", tile="t0")
        self.play("3", tile="t1")
        response = self.play("4", tile="t2")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "All tuners are busy"})
        self.assertEqual(self.reason("t2"), "busy")
        self.assertEqual(self.open(), ["2", "3"])
        self.app.stopPreview(("browser1", "t1"))  # a tile closes
        self.assertEqual(self.play("4", tile="t2").status_code, 200)
        self.assertIsNone(self.reason("t2"))  # a good start clears it

    def test_a_player_stops_the_oldest_preview_and_the_tile_is_told(self):
        self.play("2", tile="t0")
        self.play("3", tile="t1")
        self.assertEqual(self.play("4", ip="10.0.0.5").status_code, 200)
        self.assertEqual(self.open(), ["3", "4"])
        self.assertEqual(self.reason("t0"), "client")
        self.assertIsNone(self.reason("t1"))
        self.assertNotIn(("browser1", "t0"), self.app.previews)
        self.moveMac.assert_not_called()  # stopped on purpose, not the MAC's fault

    def test_a_stream_a_player_shares_is_not_stopped_for_another_player(self):
        self.play("2", ip="10.0.0.5")  # Plex
        self.play("2", tile="t0")  # a preview of the same channel
        self.play("3", tile="t1")
        self.assertEqual(self.play("4", ip="10.0.0.6").status_code, 200)
        self.assertEqual(self.open(), ["2", "4"])
        self.assertIsNone(self.reason("t0"))
        self.assertEqual(self.reason("t1"), "client")

    def test_players_never_stop_each_other(self):
        self.play("2", ip="10.0.0.5")
        self.play("3", ip="10.0.0.6")
        response = self.play("4", ip="10.0.0.8")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.open(), ["2", "3"])

    def test_a_recording_stops_a_preview_but_not_a_player(self):
        self.play("2", ip="10.0.0.5")
        self.play("3", tile="t0")
        self.assertEqual(self.play("4", recording="r1").status_code, 200)
        self.assertEqual(self.open(), ["2", "4"])
        self.assertEqual(self.reason("t0"), "recording")
        self.assertEqual(self.play("5", recording="r2").status_code, 503)

    def test_two_tiles_on_one_channel_share_a_tuner(self):
        self.play("2", tile="t0")
        self.play("2", tile="t1")
        self.assertEqual(self.play("3", tile="t2").status_code, 200)
        self.assertEqual(self.open(), ["2", "3"])
        self.assertEqual(self.entry("2")["viewers"], 2)

    def test_watching_an_open_channel_needs_no_free_tuner(self):
        self.play("2", ip="10.0.0.5")
        self.play("3", ip="10.0.0.6")
        self.assertEqual(self.play("2", tile="t0").status_code, 200)
        self.assertEqual(self.entry("2")["kinds"], ["client", "preview"])

    def test_the_tuners_setting_caps_channels_even_when_the_portal_has_room(self):
        self.app.getSettings()["hdhr tuners"] = "1"
        self.play("2", ip="10.0.0.5")
        self.assertEqual(self.play("3", ip="10.0.0.6").status_code, 503)

    def test_the_portal_limit_applies_even_with_spare_tuners(self):
        self.app.getSettings()["hdhr tuners"] = "3"
        self.app.getPortals()[PORTAL]["streams per mac"] = "1"
        self.play("2", tile="t0")
        self.assertEqual(self.play("3", ip="10.0.0.5").status_code, 200)
        self.assertEqual(self.reason("t0"), "client")

    def test_a_bad_tuners_setting_counts_as_one(self):
        for value in ("0", "", "abc", None):
            self.app.getSettings()["hdhr tuners"] = value
            self.assertEqual(self.app.tunerCount(), 1)
        self.app.getSettings()["hdhr tuners"] = "abc"
        self.assertEqual(self.play("2", ip="10.0.0.5").status_code, 200)
        self.assertEqual(self.play("3", ip="10.0.0.6").status_code, 503)

    def test_closing_a_tile_frees_its_tuner_at_once(self):
        self.app.SHARE_GRACE = 60  # would linger a minute if it waited for the grace
        response = self.client.get("/play/{}/2?web=true&viewer=browser1&tile=t0".format(PORTAL))
        next(iter(response.response))
        response.close()
        self.assertEqual(self.open(), [])

    def test_a_player_takes_a_tuner_nobody_is_watching_but_a_preview_waits(self):
        self.app.SHARE_GRACE = 60  # a closed stream lingers for a quick reconnect
        idle = self.client.get("/play/{}/2".format(PORTAL), environ_base={"REMOTE_ADDR": "10.0.0.5"})
        next(iter(idle.response))
        idle.close()
        self.play("3", ip="10.0.0.6")
        self.assertEqual(self.play("4", tile="t0").status_code, 503)
        self.assertEqual(self.play("4", ip="10.0.0.8").status_code, 200)
        self.assertEqual(self.open(), ["3", "4"])

    def test_status_without_a_known_tile_is_null(self):
        self.assertIsNone(self.reason("t5", viewer="someone-else"))

    def test_api_status_reports_tuners_and_viewers(self):
        self.play("2", ip="10.0.0.5")
        self.play("2", tile="t0")
        status = self.client.get("/api/status", headers={"X-API-Key": self.app.getSettings()["api token"]}).get_json()
        self.assertEqual(status["tuners"], {"total": 2, "used": 1})
        self.assertEqual(status["viewers"], {"client": 1, "recording": 0, "preview": 1})
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_app_tuners.TunerPoolTest -v`
Expected:
- most fail with `404` for `/preview/status`, or with `AttributeError: ... has no attribute 'tunerCount'`;
- `test_players_never_stop_each_other` may already pass (the portal limit gives 503 today).

- [ ] **Step 3: Implement the pool**

In `app.py`, after `sharedStreamsLock = threading.Lock()`:

```python
# Each kind of viewer's claim on a tuner: a new channel may stop streams whose viewers all
# have a lower claim. Plex and other players come first, then recordings, then previews.
KIND_PRIORITY = {"preview": 0, "recording": 1, "client": 2}
TUNER_BUSY = "All tuners are busy"
# Why a tile's last preview ended or didn't start, by (viewer id, tile id), so the page can
# say: "busy" (no free tuner) or the kind of viewer that needed its tuner.
previewOutcomes = {}
OUTCOME_KEEP = 600  # seconds
admissionLock = threading.Lock()
```

In `class SharedStream`, after `count`:

```python
    def priority(self):
        """The highest claim among its viewers; a stream nobody watches has the lowest."""
        with self.lock:
            return max((KIND_PRIORITY[v["kind"]] for v in self.viewers), default=0)
```

After `stopPreview`:

```python
def tunerCount():
    """The Tuners setting: how many channels may be open at once, across all portals."""
    try:
        return max(1, int(getSettings()["hdhr tuners"]))
    except (KeyError, TypeError, ValueError):
        return 1


def portalHasFreeSlot(portalId):
    portal = getPortals()[portalId]
    perMac = int(portal.get("streams per mac"))
    if perMac == 0:
        return True
    entries = occupied.get(portalId, [])
    return any(sum(1 for e in entries if e["mac"] == mac) < perMac for mac in portal["macs"])


def noteOutcome(tile, reason):
    now = time.time()
    for key in [k for k, v in previewOutcomes.items() if now - v["time"] > OUTCOME_KEEP]:
        previewOutcomes.pop(key, None)
    previewOutcomes[tile] = {"reason": reason, "time": now}


def stopForRoom(stream, kind):
    """Stop stream so a viewer of this kind can have its tuner, telling its previews why."""
    logger.info("Stopping Portal({}):Channel({}) to free a tuner for a {}".format(stream.key[0], stream.key[1], kind))
    with stream.lock:
        tiles = [v["tile"] for v in stream.viewers if v["tile"]]
    for tile in tiles:
        noteOutcome(tile, kind)
        stopPreview(tile)
    stream.end()


def makeRoom(portalId, kind, starting):
    """Make sure a new channel for a viewer of this kind fits within the Tuners setting and
    the portal's streams per MAC, stopping streams with a lower claim, oldest first, if it
    doesn't. starting is the new channel's own shared stream. True if it fits."""
    with admissionLock:
        while True:
            with sharedStreamsLock:
                others = [s for s in sharedStreams.values() if s is not starting and not s.done]
            tunersFull = len(others) >= tunerCount()
            portalFull = not portalHasFreeSlot(portalId)
            if not tunersFull and not portalFull:
                return True
            victims = [
                s for s in others
                if s.process is not None and s.priority() < KIND_PRIORITY[kind]
                and (not portalFull or s.key[0] == portalId)
            ]
            if not victims:
                return False
            stopForRoom(min(victims, key=lambda s: s.entry["start time"]), kind)
```

In `playChannel`, directly after `firstViewer = shared.join(ip, kind, tile)` (inside the same
`if`):

```python
        if not makeRoom(portalId, kind, shared):
            logger.info("No free tuner for Portal({}):Channel({})".format(portalId, channelId))
            if tile:
                noteOutcome(tile, "busy")
            return flask.jsonify({"error": TUNER_BUSY}), 503
```

(The `/play` route's `finally` already ends a shared stream that never started.)

In `watchPreview`, as the first line of the body (before `preview = {`):

```python
    previewOutcomes.pop(tile, None)  # it's playing: nothing to explain
```

After the `/play` route function `channel(...)`, add:

```python
@app.route("/preview/status", methods=["GET"])
@authorise
def previewStatus():
    """Why a tile's last preview stopped or didn't start, if STB-Proxy knows."""
    tile = (request.args.get("viewer") or request.remote_addr, request.args.get("tile") or "player")
    outcome = previewOutcomes.get(tile)
    fresh = outcome is not None and time.time() - outcome["time"] < OUTCOME_KEEP
    return flask.jsonify({"reason": outcome["reason"] if fresh else None})
```

In `apiStatus()`, before `return flask.jsonify({`:

```python
    with sharedStreamsLock:
        streams = [s for s in sharedStreams.values() if not s.done]
    viewers = {kind: 0 for kind in KIND_PRIORITY}
    for stream in streams:
        with stream.lock:
            for v in stream.viewers:
                viewers[v["kind"]] += 1
```

and in its dict, after `"streams": ...,`:

```python
        "tuners": {"total": tunerCount(), "used": len(streams)},
        "viewers": viewers,
```

- [ ] **Step 4: Document it**

In `README.md`'s API table, change the `GET /api/status` row's description to:

```markdown
| `GET /api/status` | Lineup size, active streams, tuners in use, viewers by kind (client, recording, preview), blocks, last Plex sync, and whether anything else is using your MACs |
```

In `README.md`, add a paragraph at the end of "# Streams and portal connections" (after the
paragraph starting "Everything watching the same channel"):

```markdown
**Tuners** is also how many different channels STB-Proxy opens at once, across all portals. When they're all in use and something wants a new channel, STB-Proxy makes room by stopping a browser preview, oldest first: Plex, Jellyfin and other players come before previews. A preview never stops anything, and a stream that a player is also watching is never stopped. If nothing can make room, the request gets "All tuners are busy" (HTTP 503) and a preview says **No free tuner**.
```

- [ ] **Step 5: Run the stream tests, then everything**

Run: `.venv/bin/python -m unittest tests.test_app_tuners tests.test_app_preview tests.test_app_sharing -v`
Expected: all pass.
Run: `.venv/bin/python -m unittest 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add app.py README.md tests/test_app_tuners.py
git commit -m "Share the tuners between players, recordings and previews

The Tuners setting now caps how many channels are open at once. A new channel
that doesn't fit stops a stream with a lower claim, oldest first: players
before recordings before previews, and a stream someone more important also
watches is left alone. Otherwise /play answers 503 \"All tuners are busy\".
/preview/status tells a page why a tile's preview stopped or was refused, and
/api/status reports tuners in use and viewers by kind.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Multiview state and channel helpers (`static/multiview.js`)

**Files:**
- Create: `static/multiview.js`
- Create: `tests/test_multiview_state.py`

**Interfaces:**
- Produces a global `multiview` object in the browser; under node, `require` returns the
  same object. Members:
  - `TILES` (9), `LAYOUTS` (`{"1": 1, "2": 2, "4": 4, "9": 9, "big": 4}`)
  - `browserStorage()`: `localStorage`, or a no-op stand-in if the browser won't give it
  - `loadState(storage)` returns
    `{layout, order: [tile indexes in display order], tiles: [{portal, channelId}|null x 9], audio: tile index, big: percent}`
  - `saveState(storage, state)`
  - `shownCount(state)`: how many tiles the layout shows
  - `addChannel(storage, ch)` returns the state, already saved; `ch` is `{portal, channelId}`
  - `channelName(row)`
  - `channelChoices(channels, matches, limit)`: `matches(row)` returns a bool, or `matches` is null for all
  - `nextChannel(channels, current, step)` returns a row or null
  - `failureAction(reason, retried)` returns `"busy"`, `"client"`, `"recording"`, `"retry"` or `"failed"`
- Channel rows are `/editor_data` rows, plus `available` (added in Task 4).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multiview_state.py`:

```python
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "static", "multiview.js")


def row(channelId, number, name, available=True, dead=False, favourite=False):
    return {"portal": "p1", "channelId": channelId, "channelNumber": number, "customChannelNumber": "",
            "channelName": name, "customChannelName": "", "available": available, "dead": dead,
            "favourite": favourite}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MultiviewStateTest(unittest.TestCase):
    def run_js(self, body, saved=None, throws=False):
        """Run body under node with mv (the helpers) and storage (holding saved); print its result."""
        script = (
            "const mv = require(%s);"
            "const store = {};"
            "if (%s !== null) store[mv.KEY] = %s;"
            "const storage = %s ? {getItem() { throw new Error('no'); }, setItem() { throw new Error('no'); }}"
            "  : {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }};"
            "const result = (() => { %s })();"
            "console.log(JSON.stringify(result));"
        ) % (json.dumps(SCRIPT), json.dumps(saved), json.dumps(saved), "true" if throws else "false", body)
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_garbage_or_unreadable_storage_gives_the_defaults(self):
        defaults = self.run_js("return mv.loadState(storage);")
        self.assertEqual(defaults["layout"], "4")
        self.assertEqual(defaults["order"], list(range(9)))
        self.assertEqual(defaults["tiles"], [None] * 9)
        self.assertEqual((defaults["audio"], defaults["big"]), (0, 66))
        for saved in ("{", "[]", '"x"', json.dumps({"layout": "7", "order": list(range(9)), "tiles": [None] * 9}),
                      json.dumps({"layout": "4", "order": [0, 0, 1, 2, 3, 4, 5, 6, 7], "tiles": [None] * 9}),
                      json.dumps({"layout": "4", "order": list(range(9)), "tiles": [None] * 3})):
            self.assertEqual(self.run_js("return mv.loadState(storage);", saved=saved), defaults, saved)
        self.assertEqual(self.run_js("return mv.loadState(storage);", throws=True), defaults)
        self.assertEqual(self.run_js("mv.saveState(storage, mv.loadState(storage)); return 1;", throws=True), 1)

    def test_a_saved_state_comes_back_cleaned(self):
        saved = json.dumps({"layout": "big", "order": [3, 0, 1, 2, 4, 5, 6, 7, 8],
                            "tiles": [{"portal": "p1", "channelId": 2}, {"portal": "p1"}] + [None] * 7,
                            "audio": 3, "big": 99})
        state = self.run_js("return mv.loadState(storage);", saved=saved)
        self.assertEqual(state["layout"], "big")
        self.assertEqual(state["order"][0], 3)
        self.assertEqual(state["tiles"][:2], [{"portal": "p1", "channelId": "2"}, None])
        self.assertEqual((state["audio"], state["big"]), (3, 66))

    def test_add_fills_the_first_empty_tile_shown_and_gives_it_sound(self):
        state = self.run_js(
            "mv.addChannel(storage, {portal: 'p1', channelId: '2'});"
            "mv.addChannel(storage, {portal: 'p1', channelId: '3'});"
            "return mv.loadState(storage);")
        self.assertEqual(state["tiles"][:3], [{"portal": "p1", "channelId": "2"}, {"portal": "p1", "channelId": "3"}, None])
        self.assertEqual(state["audio"], 1)

    def test_add_grows_the_layout_when_every_tile_shown_is_full(self):
        saved = json.dumps({"layout": "1", "order": list(range(9)),
                            "tiles": [{"portal": "p1", "channelId": "2"}] + [None] * 8, "audio": 0, "big": 66})
        state = self.run_js("return mv.addChannel(storage, {portal: 'p1', channelId: '3'});", saved=saved)
        self.assertEqual((state["layout"], state["tiles"][1]), ("2", {"portal": "p1", "channelId": "3"}))

    def test_add_replaces_the_tile_with_sound_when_all_nine_are_full(self):
        saved = json.dumps({"layout": "9", "order": list(range(9)),
                            "tiles": [{"portal": "p1", "channelId": str(i)} for i in range(9)], "audio": 4, "big": 66})
        state = self.run_js("return mv.addChannel(storage, {portal: 'p1', channelId: '99'});", saved=saved)
        self.assertEqual(state["tiles"][4], {"portal": "p1", "channelId": "99"})

    def test_choices_put_favourites_then_the_lineup_first_by_number(self):
        channels = [row("a", "30", "Zed"), row("b", "10", "Other", available=False),
                    row("c", "20", "Fav", favourite=True), row("d", "5", "Early")]
        names = self.run_js("return mv.channelChoices(%s, null, 50).map(mv.channelName);" % json.dumps(channels))
        self.assertEqual(names, ["Fav", "Early", "Zed", "Other"])
        some = self.run_js("return mv.channelChoices(%s, r => r.channelName != 'Zed', 2).map(mv.channelName);"
                           % json.dumps(channels))
        self.assertEqual(some, ["Fav", "Early"])

    def test_next_channel_moves_through_the_lineup_and_wraps(self):
        channels = [row("a", "1", "One"), row("b", "2", "Two", dead=True), row("c", "3", "Three"),
                    row("d", "4", "Four", available=False)]
        step = "return mv.nextChannel(%s, {portal: 'p1', channelId: '%s'}, %d).channelId;"
        self.assertEqual(self.run_js(step % (json.dumps(channels), "a", 1)), "c")  # skips dead
        self.assertEqual(self.run_js(step % (json.dumps(channels), "c", 1)), "a")  # wraps, skips not in lineup
        self.assertEqual(self.run_js(step % (json.dumps(channels), "a", -1)), "c")
        self.assertEqual(self.run_js(step % (json.dumps(channels), "d", 1)), "a")  # from outside the lineup

    def test_busy_and_stopped_tiles_are_not_retried_automatically(self):
        actions = self.run_js(
            "return [[null, false], [null, true], ['busy', false], ['client', false], ['recording', true]]"
            ".map(a => mv.failureAction(a[0], a[1]));")
        self.assertEqual(actions, ["retry", "failed", "busy", "client", "recording"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_multiview_state -v`
Expected: every test errors with `CalledProcessError` (node can't find `static/multiview.js`).

- [ ] **Step 3: Implement `static/multiview.js`**

```javascript
// Multiview's tiles and layout, kept in this browser, and helpers for picking channels.
// Shared by the Multiview page and the preview player's "Send to Multiview" (also loaded by
// tests under node).
//
// State: {layout, order, tiles, audio, big}
//   layout - "1", "2", "4", "9" or "big" (one big tile and three small)
//   order  - the nine tile indexes in the order they're shown; the first is the big one
//   tiles  - by tile index: {portal, channelId}, or null for an empty tile
//   audio  - the tile index whose sound plays
//   big    - the big tile's share of the width, in percent
(function (root) {
    var KEY = "stbMultiview";
    var TILES = 9;
    var LAYOUTS = { "1": 1, "2": 2, "4": 4, "9": 9, "big": 4 };
    var BIGGER = { "1": "2", "2": "4", "4": "9", "big": "9" };

    function defaultState() {
        var order = [];
        var tiles = [];
        for (var i = 0; i < TILES; i++) {
            order.push(i);
            tiles.push(null);
        }
        return { layout: "4", order: order, tiles: tiles, audio: 0, big: 66 };
    }

    function isTileIndex(n) {
        return typeof n == "number" && n % 1 == 0 && n >= 0 && n < TILES;
    }

    function browserStorage() {
        try {
            if (root.localStorage) {
                return root.localStorage;
            }
        } catch (e) { }
        return { getItem: function () { return null; }, setItem: function () { } };
    }

    function loadState(storage) {
        var state = defaultState();
        var saved;
        try {
            saved = JSON.parse(storage.getItem(KEY) || "null");
        } catch (e) {
            return state;
        }
        if (!saved || typeof saved != "object" || !LAYOUTS.hasOwnProperty(saved.layout) ||
            !Array.isArray(saved.tiles) || saved.tiles.length != TILES || !Array.isArray(saved.order)) {
            return state;
        }
        var order = saved.order.map(Number);
        if (order.slice().sort(function (a, b) { return a - b; }).join() != state.order.join()) {
            return state;
        }
        state.layout = saved.layout;
        state.order = order;
        state.tiles = saved.tiles.map(function (t) {
            return t && t.portal && t.channelId ? { portal: String(t.portal), channelId: String(t.channelId) } : null;
        });
        state.audio = isTileIndex(saved.audio) ? saved.audio : 0;
        state.big = typeof saved.big == "number" && saved.big >= 30 && saved.big <= 85 ? saved.big : 66;
        return state;
    }

    function saveState(storage, state) {
        try {
            storage.setItem(KEY, JSON.stringify(state));
        } catch (e) { }
    }

    function shownCount(state) {
        return LAYOUTS[state.layout];
    }

    function firstEmptyTile(state) {
        for (var pos = 0; pos < shownCount(state); pos++) {
            if (!state.tiles[state.order[pos]]) {
                return state.order[pos];
            }
        }
        return null;
    }

    // Put a channel in the first empty tile on show, growing the layout if they're all full,
    // and give it the sound.
    function addChannel(storage, ch) {
        var state = loadState(storage);
        var tile = firstEmptyTile(state);
        while (tile === null && BIGGER[state.layout]) {
            state.layout = BIGGER[state.layout];
            tile = firstEmptyTile(state);
        }
        if (tile === null) {
            tile = state.audio;  // all nine are full: replace the one being listened to
        }
        state.tiles[tile] = { portal: String(ch.portal), channelId: String(ch.channelId) };
        state.audio = tile;
        saveState(storage, state);
        return state;
    }

    function channelName(row) {
        return row.customChannelName || row.channelName;
    }

    function channelNumber(row) {
        return (row.customChannelNumber || row.channelNumber) * 1 || 0;
    }

    function byNumber(a, b) {
        return channelNumber(a) - channelNumber(b) || channelName(a).localeCompare(channelName(b));
    }

    // Channels for the picker: favourites, then the lineup, each by number.
    function channelChoices(channels, matches, limit) {
        return channels
            .filter(function (row) { return !matches || matches(row); })
            .sort(function (a, b) {
                return (b.favourite - a.favourite) || (b.available - a.available) || byNumber(a, b);
            })
            .slice(0, limit);
    }

    // Channel up/down: the lineup's working channels, by number, wrapping round.
    function nextChannel(channels, current, step) {
        var lineup = channels.filter(function (row) { return row.available && !row.dead; }).sort(byNumber);
        if (!lineup.length) {
            return null;
        }
        var index = -1;
        for (var i = 0; i < lineup.length; i++) {
            if (lineup[i].portal == current.portal && lineup[i].channelId == current.channelId) {
                index = i;
            }
        }
        if (index == -1) {
            return lineup[step > 0 ? 0 : lineup.length - 1];
        }
        return lineup[(index + step + lineup.length) % lineup.length];
    }

    // What a tile does when its preview fails. reason is from /preview/status. A busy portal
    // gets one automatic retry; no free tuner, or a tuner taken back, waits for Try again,
    // so a page with more tiles than tuners doesn't keep asking.
    function failureAction(reason, retried) {
        if (reason == "busy" || reason == "client" || reason == "recording") {
            return reason;
        }
        return retried ? "failed" : "retry";
    }

    var api = {
        KEY: KEY,
        TILES: TILES,
        LAYOUTS: LAYOUTS,
        browserStorage: browserStorage,
        loadState: loadState,
        saveState: saveState,
        shownCount: shownCount,
        addChannel: addChannel,
        channelName: channelName,
        channelChoices: channelChoices,
        nextChannel: nextChannel,
        failureAction: failureAction,
    };
    root.multiview = api;
    if (typeof module !== "undefined") {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : this);
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_multiview_state -v`
Expected: all 8 pass.

- [ ] **Step 5: Commit**

```bash
git add static/multiview.js tests/test_multiview_state.py
git commit -m "Add Multiview's saved layout and channel helpers

Kept in the browser and checked on load, so stale or broken saved state falls
back to an empty 2x2. Also picks channels for the picker, channel up/down
through the lineup, and what a tile does when its preview fails: no free
tuner waits for Try again instead of retrying on its own.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The Multiview page

**Files:**
- Modify: `app.py`:
  - add `"available"` to `/editor_data` rows (around lines 770–840)
  - add a `/multiview` route after the `/guide` route
- Modify: `templates/base.html`, adding a nav item after Guide
- Create: `templates/multiview.html`
- Modify: `tests/test_templates.py`, adding a JS syntax test
- Create: `tests/test_app_multiview.py`
- Modify: `README.md`, adding a "# Multiview" section after "# Preview player"

**Interfaces:**
- Consumes:
  - `tunerCount()` (Task 2)
  - `multiview.*` (Task 3)
  - `parseChannelQuery(text, "prefix")` from `static/channel-filter.js`, which returns a
    function `(name) -> bool`, or null for an empty query
  - `GET /channel/guide?portal=&channelId=` returning `{programmes: [{start, stop, title, desc}]}`
  - `POST /channel/dead` with form `portal`, `channelId`, `dead=true`
  - `GET /preview/status` (Task 2)
- Produces:
  - `GET /multiview`
  - `/editor_data` rows with `"available": bool` (in the lineup: enabled or in a block
    that's on, and not dead)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_multiview.py`:

```python
import unittest

from tests.support import PORTAL, loadApp, portalConfig


class MultiviewPageTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{
                "enabled channels": ["1"],
                "channel blocks": {"2": ["NHL"], "3": ["Movies"]},
            })},
            "blocks": {"NHL": "true", "Movies": "false"},
            "settings": {"hdhr tuners": "2"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def test_page_renders_with_layouts_and_the_tuner_count(self):
        body = self.client.get("/multiview").get_data(as_text=True)
        self.assertIn('id="multiviewGrid"', body)
        for layout in ("1", "2", "4", "9", "big"):
            self.assertIn('data-layout="{}"'.format(layout), body)
        self.assertIn("2 tuners", body)
        self.assertIn("multiview.js", body)

    def test_menu_links_to_it(self):
        self.assertIn('href="/multiview"', self.client.get("/guide").get_data(as_text=True))

    def test_editor_data_says_which_channels_are_in_the_lineup(self):
        rows = {r["channelId"]: r for r in self.client.get("/editor_data").get_json()["data"]}
        self.assertEqual({c: rows[c]["available"] for c in rows}, {"1": True, "2": True, "3": False})


if __name__ == "__main__":
    unittest.main()
```

In `tests/test_templates.py`, add to `TemplateScriptTest`:

```python
    def test_multiview_script_is_valid_javascript(self):
        self.assertValidJavaScript("multiview.html")

    def test_multiview_helpers_are_valid_javascript(self):
        result = subprocess.run(["node", "--check", os.path.join(ROOT, "static", "multiview.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_app_multiview tests.test_templates -v`
Expected:
- the page tests fail with 404 or with the nav link missing;
- `test_editor_data_says_which_channels_are_in_the_lineup` errors with `KeyError: 'available'`;
- `test_multiview_script_is_valid_javascript` errors because the template doesn't exist.

- [ ] **Step 3: Add `available` to `/editor_data` and the route**

In `editor_data()`, after `favouriteChannels = portals[portal].get("favourite channels", [])`:

```python
            available = availability.availableChannels(portals[portal], getBlocks())
```

In the row dict appended to `channels`, after `"favourite": channelId in favouriteChannels,`:

```python
                            "available": channelId in available,
```

After the `/guide` route function:

```python
@app.route("/multiview", methods=["GET"])
@authorise
def multiview():
    return render_template("multiview.html", tuners=tunerCount())
```

In `templates/base.html`, after the Guide `<li class="nav-item">…</li>`:

```html
                    <li class="nav-item">
                        <a class="nav-link" href="/multiview"><i class="fa fa-th"></i> Multiview</a>
                    </li>
```

- [ ] **Step 4: Create `templates/multiview.html`**

```html
{% extends "base.html" %}
{% block content %}

<style>
    #multiviewGrid {
        position: relative;
        display: grid;
        gap: 4px;
        height: calc(100vh - 190px);
        min-height: 320px;
        background-color: #000;
    }
    #multiviewGrid:fullscreen {
        height: 100vh;
    }
    #multiviewGrid[data-layout="1"] { grid-template-columns: 1fr; }
    #multiviewGrid[data-layout="2"] { grid-template-columns: 1fr 1fr; }
    #multiviewGrid[data-layout="4"] { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
    #multiviewGrid[data-layout="9"] { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr); }
    #multiviewGrid[data-layout="big"] { grid-template-columns: var(--big, 66%) 1fr; grid-template-rows: repeat(3, 1fr); }
    #multiviewGrid[data-layout="big"] .tile.first { grid-row: 1 / span 3; }
    .tile {
        position: relative;
        min-width: 0;
        min-height: 0;
        overflow: hidden;
        background-color: #111;
        border: 2px solid transparent;
    }
    .tile.has-audio {
        border-color: #ffc107;
    }
    .tile video {
        display: block;
        width: 100%;
        height: 100%;
        object-fit: contain;
        background-color: #000;
    }
    .tile-header {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 4px;
        background: linear-gradient(rgba(0, 0, 0, 0.85), rgba(0, 0, 0, 0));
    }
    .tile-progress {
        position: absolute;
        left: 0;
        right: 0;
        bottom: 0;
        height: 3px;
        background-color: rgba(255, 255, 255, 0.15);
    }
    .tile-progress div {
        height: 100%;
        width: 0;
        background-color: #0d6efd;
    }
    .tile-message {
        position: absolute;
        inset: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 1rem;
        text-align: center;
        background-color: rgba(0, 0, 0, 0.6);
    }
    .tile.empty .tile-message {
        background-color: transparent;
    }
    .channel-logo {
        width: 48px;
        height: 28px;
        object-fit: contain;
        flex-shrink: 0;
        padding: 2px;
        border-radius: 3px;
        background-color: #f8f9fa;
    }
    #mvDivider {
        position: absolute;
        top: 0;
        bottom: 0;
        left: var(--big, 66%);
        width: 12px;
        margin-left: -8px;
        cursor: col-resize;
        z-index: 2;
        touch-action: none;
    }
    #mvDivider:hover {
        background-color: rgba(255, 193, 7, 0.4);
    }
    /* On a phone, tiles stack, each 16:9. */
    @media (max-width: 575.98px) {
        #multiviewGrid[data-layout] { grid-template-columns: 1fr; grid-template-rows: none; height: auto; }
        #multiviewGrid[data-layout="big"] .tile.first { grid-row: auto; }
        .tile { aspect-ratio: 16 / 9; }
        #mvDivider { display: none !important; }
    }
</style>

<div class="container-fluid text-light px-lg-5">
    <div class="d-flex flex-wrap align-items-center mb-2">
        <h4 class="mb-0 me-3">Multiview</h4>
        <div class="btn-group btn-group-sm me-3 my-1" role="group" aria-label="Layout">
            <button type="button" class="btn btn-outline-light layout-button" data-layout="1" onclick="setLayout('1')" title="One tile">1</button>
            <button type="button" class="btn btn-outline-light layout-button" data-layout="2" onclick="setLayout('2')" title="Two side by side">2</button>
            <button type="button" class="btn btn-outline-light layout-button" data-layout="4" onclick="setLayout('4')" title="2 &times; 2">4</button>
            <button type="button" class="btn btn-outline-light layout-button" data-layout="9" onclick="setLayout('9')" title="3 &times; 3">9</button>
            <button type="button" class="btn btn-outline-light layout-button" data-layout="big" onclick="setLayout('big')"
                title="One big, three small" aria-label="One big, three small"><i class="fa fa-th-large"></i></button>
        </div>
        <span class="small text-muted me-auto my-1">{{ tuners }} tuner{{ "s" if tuners != 1 }}: tiles on the same channel, or on a channel Plex is watching, share one.
            <span id="soundHint" class="text-warning">Click a tile for sound.</span></span>
        <button type="button" class="btn btn-sm btn-outline-light my-1" onclick="toggleFullWindow()"
            title="Full window (F)" aria-label="Full window"><i class="fa fa-expand"></i></button>
    </div>
    <div id="mvError" class="alert alert-danger d-none">Couldn't load channels from the portals. <a href="/multiview">Reload</a> to try again.</div>
    <div id="multiviewGrid" data-layout="4">
        <div id="mvDivider" class="d-none" title="Drag to resize"></div>
    </div>
</div>

<div class="modal fade" id="channelPicker" tabindex="-1" aria-labelledby="pickerTitle" aria-hidden="true">
    <div class="modal-dialog modal-dialog-scrollable">
        <div class="modal-content bg-dark text-light">
            <div class="modal-header">
                <h5 class="modal-title" id="pickerTitle">Choose a channel</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <input type="search" class="form-control mb-2" id="pickerQuery" placeholder="Channel name or number" autocomplete="off">
                <div id="pickerResults" class="list-group"></div>
            </div>
        </div>
    </div>
</div>

<script src="{{ url_for('static', filename='channel-filter.js') }}"></script>
<script src="{{ url_for('static', filename='multiview.js') }}"></script>
<script>
    var storage = multiview.browserStorage();
    var state = multiview.loadState(storage);
    var grid = document.getElementById("multiviewGrid");
    var divider = document.getElementById("mvDivider");
    var tiles = [];
    var channels = null;
    var loading = null;
    var guides = {};
    var GUIDE_KEEP_MS = 600000;
    var soundUnlocked = false;
    var picker = null;
    var pickerTile = null;
    var pickerRows = [];
    var MESSAGES = {
        busy: "No free tuner. Close a tile, or wait for Plex to finish.",
        client: "Plex or another player needed this tuner.",
        recording: "A recording needed this tuner.",
    };

    // The same browser id the preview player sends, so the server keeps this browser's tiles apart.
    var viewerId = (function () {
        var id = null;
        try {
            id = localStorage.getItem("stbViewer");
        } catch (e) { }
        if (!id) {
            id = Math.random().toString(36).slice(2) + Date.now().toString(36);
            try {
                localStorage.setItem("stbViewer", id);
            } catch (e) { }
        }
        return id;
    })();

    function escapeAttr(s) {
        return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function save() {
        multiview.saveState(storage, state);
    }

    function channelKey(ch) {
        return ch.portal + '/' + ch.channelId;
    }

    function loadChannels() {
        if (!loading) {
            loading = $.getJSON("/editor_data").then(function (res) {
                channels = res.data;
                return channels;
            });
            loading.fail(function () {
                loading = null;
            });
        }
        return loading;
    }

    function rowFor(ch) {
        if (!channels || !ch) {
            return null;
        }
        for (var i = 0; i < channels.length; i++) {
            if (channels[i].portal == ch.portal && channels[i].channelId == ch.channelId) {
                return channels[i];
            }
        }
        return null;
    }

    function isShown(i) {
        return state.order.indexOf(i) < multiview.shownCount(state);
    }

    function buildTiles() {
        for (var i = 0; i < multiview.TILES; i++) {
            var el = document.createElement("div");
            el.className = "tile";
            el.innerHTML =
                '<video playsinline muted autoplay></video>' +
                '<div class="tile-header">' +
                '<img class="channel-logo d-none" alt="" onerror="this.classList.add(\'d-none\')">' +
                '<div class="text-truncate me-auto"><div class="fw-bold text-truncate tile-name"></div>' +
                '<div class="small text-truncate tile-now"></div></div>' +
                '<button type="button" class="btn btn-sm btn-outline-light tile-audio" title="Sound from this tile" aria-label="Sound from this tile"><i class="fa fa-volume-off"></i></button>' +
                '<button type="button" class="btn btn-sm btn-outline-light tile-big" title="Make big" aria-label="Make big"><i class="fa fa-arrows-alt"></i></button>' +
                '<button type="button" class="btn btn-sm btn-outline-light tile-swap" title="Change channel" aria-label="Change channel"><i class="fa fa-exchange"></i></button>' +
                '<button type="button" class="btn btn-sm btn-outline-light tile-close" title="Close" aria-label="Close"><i class="fa fa-times"></i></button>' +
                '</div>' +
                '<div class="tile-progress"><div></div></div>' +
                '<div class="tile-message d-none"></div>';
            grid.appendChild(el);
            var tile = { el: el, video: el.querySelector("video"), seq: 0, timer: null, retried: false, playingKey: null };
            tile.video.volume = 0.25;
            tiles.push(tile);
            wireTile(i);
        }
    }

    function wireTile(i) {
        var t = tiles[i];
        t.el.querySelector(".tile-audio").addEventListener("click", function (e) {
            e.stopPropagation();
            unlockSound();
            setAudio(i);
        });
        t.el.querySelector(".tile-big").addEventListener("click", function (e) {
            e.stopPropagation();
            makeBig(i);
        });
        t.el.querySelector(".tile-swap").addEventListener("click", function (e) {
            e.stopPropagation();
            openPicker(i);
        });
        t.el.querySelector(".tile-close").addEventListener("click", function (e) {
            e.stopPropagation();
            closeTile(i);
        });
        t.el.addEventListener("click", function () {
            unlockSound();
            if (state.tiles[i]) {
                setAudio(i);
            }
        });
        t.video.addEventListener("playing", function () {
            clearTimeout(t.timer);
            t.retried = false;
            showMessage(i, "");
        });
        t.video.addEventListener("error", function () {
            if (t.video.getAttribute("src")) {
                tileFailed(i);
            }
        });
    }

    function showMessage(i, html) {
        var box = tiles[i].el.querySelector(".tile-message");
        box.innerHTML = html;
        box.classList.toggle("d-none", !html);
    }

    function retryButton(i) {
        return '<button type="button" class="btn btn-sm btn-outline-warning mt-2" onclick="retryTile(' + i + ')">Try again</button>';
    }

    function renderTile(i) {
        var t = tiles[i];
        var ch = state.tiles[i];
        var row = rowFor(ch);
        var position = state.order.indexOf(i);
        t.el.style.order = position;
        t.el.classList.toggle("first", position == 0);
        t.el.classList.toggle("d-none", !isShown(i));
        t.el.classList.toggle("empty", !ch);
        t.el.querySelector(".tile-header").classList.toggle("d-none", !ch);
        t.el.querySelector(".tile-name").textContent = row ? multiview.channelName(row) : "";
        var logo = t.el.querySelector(".channel-logo");
        logo.classList.toggle("d-none", !(row && row.logo));
        if (row && row.logo) {
            logo.src = row.logo;
        }
        if (!ch) {
            t.el.querySelector(".tile-now").textContent = "";
            t.el.querySelector(".tile-progress div").style.width = "0";
            showMessage(i, '<button type="button" class="btn btn-outline-light" onclick="openPicker(' + i + ')">' +
                '<i class="fa fa-plus"></i> Add channel</button>');
        } else if (!channels) {
            showMessage(i, '<i class="fa fa-spinner fa-spin"></i>');
        } else if (!row) {
            showMessage(i, 'This channel isn\'t on an enabled portal any more.' +
                '<button type="button" class="btn btn-sm btn-outline-light mt-2" onclick="closeTile(' + i + ')">Remove</button>');
        }
    }

    function render() {
        grid.setAttribute("data-layout", state.layout);
        grid.style.setProperty("--big", state.big + "%");
        divider.classList.toggle("d-none", state.layout != "big");
        document.querySelectorAll(".layout-button").forEach(function (b) {
            b.classList.toggle("active", b.getAttribute("data-layout") == state.layout);
        });
        for (var i = 0; i < multiview.TILES; i++) {
            renderTile(i);
            var row = rowFor(state.tiles[i]);
            var want = isShown(i) && row ? channelKey(row) : null;
            if (want != tiles[i].playingKey) {
                stopTile(i);
                if (want) {
                    startTile(i, 0);
                }
            }
        }
        applyAudio();
    }

    function startTile(i, delay) {
        var t = tiles[i];
        var row = rowFor(state.tiles[i]);
        if (!row) {
            return;
        }
        var seq = ++t.seq;
        clearTimeout(t.timer);
        t.playingKey = channelKey(row);
        setTimeout(function () {
            if (seq != t.seq) {
                return;  // the tile changed or closed meanwhile
            }
            t.video.src = row.link + "&viewer=" + encodeURIComponent(viewerId) + "&tile=t" + i;
            t.video.play().catch(function () { });
            t.timer = setTimeout(function () { tileFailed(i); }, 15000);
        }, delay);
        refreshGuide(i);
    }

    // Dropping the source closes the stream, which frees its tuner at once.
    function dropSource(t) {
        t.seq++;
        clearTimeout(t.timer);
        t.video.pause();
        t.video.removeAttribute("src");
        t.video.load();
    }

    function stopTile(i) {
        dropSource(tiles[i]);
        tiles[i].playingKey = null;
    }

    function tileFailed(i) {
        var t = tiles[i];
        clearTimeout(t.timer);
        if (!t.playingKey) {
            return;
        }
        var seq = t.seq;
        $.getJSON("/preview/status", { viewer: viewerId, tile: "t" + i })
            .then(function (res) { return res.reason; }, function () { return $.Deferred().resolve(null); })
            .done(function (reason) {
                if (seq != t.seq) {
                    return;
                }
                var action = multiview.failureAction(reason, t.retried);
                dropSource(t);
                if (action == "retry") {
                    t.retried = true;
                    showMessage(i, "Portal busy, trying again...");
                    startTile(i, 3000);
                } else if (action == "failed") {
                    showMessage(i, "This channel didn't play. The portal may just be busy: try again in a few seconds before marking it dead." +
                        '<div>' + retryButton(i) + ' <button type="button" class="btn btn-sm btn-danger mt-2" onclick="markDead(' + i + ')">Mark dead</button></div>');
                } else {
                    showMessage(i, MESSAGES[action] + retryButton(i));
                }
            });
    }

    function retryTile(i) {
        tiles[i].retried = false;
        showMessage(i, "");
        startTile(i, 0);
    }

    function markDead(i) {
        var ch = state.tiles[i];
        $.post("/channel/dead", { portal: ch.portal, channelId: ch.channelId, dead: "true" })
            .done(function () {
                var row = rowFor(ch);
                if (row) {
                    row.dead = true;
                }
                showMessage(i, 'Marked dead.<button type="button" class="btn btn-sm btn-outline-light mt-2" onclick="closeTile(' + i + ')">Close tile</button>');
            })
            .fail(function () {
                showMessage(i, "Couldn't mark it dead. Try again." + retryButton(i));
            });
    }

    function setChannel(i, row) {
        state.tiles[i] = { portal: row.portal, channelId: row.channelId };
        save();
        tiles[i].retried = false;
        showMessage(i, "");
        stopTile(i);
        renderTile(i);
        startTile(i, 0);
        applyAudio();
    }

    function closeTile(i) {
        stopTile(i);
        state.tiles[i] = null;
        save();
        renderTile(i);
        applyAudio();
    }

    function unlockSound() {
        if (!soundUnlocked) {
            soundUnlocked = true;
            document.getElementById("soundHint").classList.add("d-none");
            applyAudio();
        }
    }

    // One tile plays sound. Browsers only allow sound after a click, so until then all are muted.
    function applyAudio() {
        tiles.forEach(function (t, i) {
            var selected = i == state.audio && !!state.tiles[i];
            t.video.muted = !(soundUnlocked && selected);
            t.el.classList.toggle("has-audio", selected);
            t.el.querySelector(".tile-audio i").className = "fa " + (selected && soundUnlocked ? "fa-volume-up" : "fa-volume-off");
        });
    }

    function setAudio(i) {
        state.audio = i;
        save();
        applyAudio();
    }

    function makeBig(i) {
        state.order = [i].concat(state.order.filter(function (x) { return x != i; }));
        state.layout = "big";
        save();
        render();
    }

    function setLayout(layout) {
        state.layout = layout;
        save();
        render();
    }

    function changeChannel(step) {
        var i = state.audio;
        if (!channels || !state.tiles[i] || !isShown(i)) {
            return;
        }
        var next = multiview.nextChannel(channels, state.tiles[i], step);
        if (next) {
            setChannel(i, next);
        }
    }

    // ---- The channel picker
    function openPicker(i) {
        pickerTile = i;
        if (!picker) {
            picker = new bootstrap.Modal(document.getElementById("channelPicker"));
        }
        document.getElementById("pickerQuery").value = "";
        renderPicker();
        picker.show();
    }

    document.getElementById("channelPicker").addEventListener("shown.bs.modal", function () {
        document.getElementById("pickerQuery").focus();
    });

    function renderPicker() {
        var results = document.getElementById("pickerResults");
        if (!channels) {
            results.innerHTML = '<p class="text-muted mb-0"><i class="fa fa-spinner fa-spin"></i> Loading channels...</p>';
            loadChannels().done(renderPicker);
            return;
        }
        var text = document.getElementById("pickerQuery").value.trim();
        var nameMatches = parseChannelQuery(text, "prefix");
        var matches = nameMatches ? function (row) {
            return nameMatches(multiview.channelName(row)) || String(row.customChannelNumber || row.channelNumber) == text;
        } : null;
        pickerRows = multiview.channelChoices(channels, matches, 50);
        if (!pickerRows.length) {
            results.innerHTML = '<p class="text-muted mb-0">No channels match.</p>';
            return;
        }
        results.innerHTML = pickerRows.map(function (row, k) {
            return '<button type="button" class="list-group-item list-group-item-action bg-dark text-light d-flex align-items-center" onclick="pick(' + k + ')">' +
                (row.logo ? '<img class="channel-logo" loading="lazy" alt="" src="' + escapeAttr(row.logo) + '" onerror="this.style.visibility=\'hidden\'">'
                    : '<span class="channel-logo d-inline-block" style="background: none;"></span>') +
                '<span class="ms-2 me-2 text-muted">' + escapeAttr(row.customChannelNumber || row.channelNumber) + '</span>' +
                '<span class="me-auto">' + escapeAttr(multiview.channelName(row)) + '</span>' +
                (row.favourite ? '<i class="fa fa-star text-warning ms-1"></i>' : '') +
                (row.dead ? '<span class="badge bg-danger ms-1">dead</span>' : '') +
                (row.available ? '' : '<span class="badge bg-secondary ms-1">not in lineup</span>') +
                '</button>';
        }).join("");
    }

    function pick(k) {
        var row = pickerRows[k];
        picker.hide();
        if (row && pickerTile !== null) {
            unlockSound();
            setChannel(pickerTile, row);
            setAudio(pickerTile);
        }
    }

    document.getElementById("pickerQuery").addEventListener("input", renderPicker);
    document.getElementById("pickerQuery").addEventListener("keydown", function (event) {
        if (event.key == "Enter" && pickerRows.length) {
            pick(0);
        }
    });

    // ---- What's on, per tile
    function refreshGuide(i) {
        var ch = state.tiles[i];
        if (!ch) {
            return;
        }
        var key = channelKey(ch);
        var cached = guides[key];
        if (cached && Date.now() - cached.time < GUIDE_KEEP_MS) {
            showGuide(i, key, cached.programmes);
            return;
        }
        $.getJSON("/channel/guide", { portal: ch.portal, channelId: ch.channelId }).done(function (res) {
            guides[key] = { time: Date.now(), programmes: res.programmes };
            showGuide(i, key, res.programmes);
        });
    }

    function showGuide(i, key, programmes) {
        if (!state.tiles[i] || channelKey(state.tiles[i]) != key) {
            return;
        }
        var now = Date.now() / 1000;
        var current = null;
        programmes.forEach(function (p) {
            if (p.start <= now && p.stop > now) {
                current = p;
            }
        });
        var line = tiles[i].el.querySelector(".tile-now");
        line.textContent = current ? current.title : "";
        line.title = line.textContent;
        tiles[i].el.querySelector(".tile-progress div").style.width =
            current ? Math.round((now - current.start) / (current.stop - current.start) * 100) + "%" : "0";
    }

    setInterval(function () {
        for (var i = 0; i < multiview.TILES; i++) {
            if (isShown(i)) {
                refreshGuide(i);
            }
        }
    }, 60000);

    // ---- Full window, keys and the big tile's divider
    function toggleFullWindow() {
        if (document.fullscreenElement == grid) {
            document.exitFullscreen();
        } else if (grid.requestFullscreen) {
            grid.requestFullscreen();
        }
    }

    document.addEventListener("keydown", function (event) {
        if (event.target.matches("input, textarea, select") || document.querySelector(".modal.show")) {
            return;
        }
        if (event.key == "f" || event.key == "F") {
            toggleFullWindow();
        } else if (event.key == "PageUp") {
            changeChannel(1);
        } else if (event.key == "PageDown") {
            changeChannel(-1);
        } else {
            return;
        }
        event.preventDefault();
    });

    var dragging = false;
    divider.addEventListener("pointerdown", function (event) {
        dragging = true;
        divider.setPointerCapture(event.pointerId);
    });
    divider.addEventListener("pointermove", function (event) {
        if (!dragging) {
            return;
        }
        var rect = grid.getBoundingClientRect();
        state.big = Math.round(Math.min(85, Math.max(30, (event.clientX - rect.left) / rect.width * 100)));
        grid.style.setProperty("--big", state.big + "%");
    });
    divider.addEventListener("pointerup", function () {
        dragging = false;
        save();
    });

    buildTiles();
    render();
    loadChannels()
        .done(render)
        .fail(function () {
            document.getElementById("mvError").classList.remove("d-none");
        });
</script>

{% endblock %}
```

- [ ] **Step 5: Document it**

In `README.md`, add after the "# Preview player" section, before "# Channel logos":

```markdown
# Multiview

- **Multiview** (in the menu) plays several channels at once. Pick a layout: 1, 2 side by side, 2 × 2, 3 × 3, or one big tile with three small ones (drag the line between them to resize).
- Click **Add channel** in an empty tile and search by name or number. Favourites come first, then channels in your lineup.
- One tile plays sound, outlined in yellow: click a tile (or its 🔈 button) to hear it. **Page Up / Page Down** changes that tile's channel, through your lineup.
- ⤢ makes a tile the big one, ⇄ changes its channel, and ✕ closes it, which frees its tuner straight away. **F** fills the window.
- Each different channel needs a tuner (see Streams and portal connections). Tiles on the same channel, or on a channel Plex is watching, share one. With more tiles than tuners, the extra tiles say **No free tuner**. If Plex needs a tuner a tile is using, the tile stops and says so. **Try again** once a tuner is free.
- Your browser remembers the tiles and layout, and opens them again next time.
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_app_multiview tests.test_templates tests.test_app_editor -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/base.html templates/multiview.html tests/test_app_multiview.py tests/test_templates.py README.md
git commit -m "Add Multiview: several channels at once in a grid

Layouts of 1, 2, 2x2 and 3x3 tiles, or one big tile with three small ones and
a draggable divider. Tiles pick channels from a search with favourites and the
lineup first, show what's on, and explain when there's no free tuner or Plex
took theirs back. One tile plays sound; Page Up/Down changes its channel.
/editor_data now says which channels are in the lineup.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The preview player: Send to Multiview, and why a preview stopped

**Files:**
- Modify: `templates/_player.html`:
  - add a header button after the full-screen button
  - add a span inside `#previewProblem`
  - load `multiview.js`
  - change `startStream`, `previewFailed` and `retryPreview`
  - add `sendToMultiview`
- Modify: `tests/test_templates.py`, the `PreviewPromptTest` class
- Modify: `README.md`, the "# Preview player" section

**Interfaces:**
- Consumes:
  - `multiview.addChannel(storage, ch)`, `multiview.browserStorage()` and
    `multiview.failureAction(reason, retried)` (Task 3)
  - `GET /preview/status` (Task 2)
- Produces: nothing new for other tasks.

- [ ] **Step 1: Write the failing tests**

In `tests/test_templates.py`, add to `PreviewPromptTest`:

```python
    def test_previews_say_which_tile_they_play_in(self):
        self.assertIn('"&tile=player"', self.script)

    def test_a_refused_or_stopped_preview_says_why(self):
        self.assertIn("/preview/status", self.script)
        self.assertIn('id="previewProblemText"', self.html)

    def test_send_to_multiview(self):
        self.assertIn('id="multiviewButton"', self.html)
        self.assertIn("function sendToMultiview", self.script)
        self.assertIn("multiview.js", self.html)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m unittest tests.test_templates.PreviewPromptTest -v`
Expected: the three new tests fail with `AssertionError: ... not found`.

- [ ] **Step 3: Implement**

In `templates/_player.html`, after the `#fullscreenButton` button:

```html
        <button type="button" class="btn btn-sm btn-outline-light ms-1" id="multiviewButton"
            onclick="sendToMultiview()" title="Send to Multiview" aria-label="Send to Multiview"><i class="fa fa-th"></i></button>
```

Replace the `#previewProblem` span:

```html
            <span id="previewProblem" class="me-auto small text-warning d-none"><span id="previewProblemText"></span>
                <button type="button" class="btn btn-sm btn-outline-warning ms-1" id="retryPreview" onclick="retryPreview()">Try again</button>
            </span>
```

Directly before the template's main `<script>` (the one starting `var player = document.getElementById("player");`):

```html
<script src="{{ url_for('static', filename='multiview.js') }}"></script>
```

In `startStream`, change the `player.src` line to:

```javascript
            player.src = currentLink + "&viewer=" + encodeURIComponent(viewerId) + "&tile=player";
```

Replace `previewFailed` and `retryPreview`:

```javascript
    var PROBLEMS = {
        failed: "This channel didn't play. The portal may just be busy: try again in a few seconds before marking it dead.",
        busy: "No free tuner: they're all in use (Plex, Multiview or another browser). Try again when one frees up.",
        client: "Plex or another player needed this tuner.",
        recording: "A recording needed this tuner.",
    };

    function previewFailed() {
        clearTimeout(previewTimer);
        if (!currentChannel) {
            return;
        }
        var row = rowFor(currentChannel);
        if (!row || row.dead) {
            return;
        }
        var seq = streamSeq;
        $.getJSON("/preview/status", { viewer: viewerId, tile: "player" })
            .then(function (res) { return res.reason; }, function () { return $.Deferred().resolve(null); })
            .done(function (reason) {
                if (seq != streamSeq) {
                    return;  // another channel was picked meanwhile
                }
                var action = multiview.failureAction(reason, retried);
                if (action == "retry") {
                    // Usually the portal connection is still busy with the last stream: try once more.
                    retried = true;
                    stopStream();
                    document.getElementById("deadStatus").textContent = BUSY_MESSAGE;
                    startStream(3000);
                    return;
                }
                stopStream();
                document.getElementById("deadStatus").textContent = "";
                document.getElementById("previewProblemText").textContent = PROBLEMS[action];
                document.getElementById("previewProblem").classList.remove("d-none");
                setMinimised(false);
            });
    }

    function retryPreview() {
        document.getElementById("previewProblem").classList.add("d-none");
        retried = false;
        stopStream();
        startStream(0);
    }

    // Move the channel playing here to Multiview, which opens with it in a tile.
    function sendToMultiview() {
        if (!currentChannel) {
            return;
        }
        var ch = currentChannel;
        closePlayer();  // frees its tuner for the tile
        multiview.addChannel(multiview.browserStorage(), ch);
        location.href = "/multiview";
    }
```

- [ ] **Step 4: Document it**

In `README.md`'s "# Preview player" section, add after the "Picking another channel stops
the one playing straight away" bullet:

```markdown
- **Send to Multiview** (▦) moves the channel to a Multiview tile, so you can watch it alongside others.
- If the preview can't get a tuner, or Plex needs the one it's using, the player says so instead of suggesting the channel is dead.
```

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m unittest 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 6: Browser check against a throwaway local config**

Create the config in the session's scratchpad directory (`S` below). Use a portal on a `.invalid` host and generic channels, so
nothing touches the real portal:

```bash
S=/tmp/claude-1000/-code-stb-proxy/<session id>/scratchpad   # the scratchpad path from the session's environment
.venv/bin/python - <<EOF
import json
json.dump({"portals": {"p1": {"enabled": "true", "name": "Test", "url": "http://portal.invalid/server/load.php",
           "macs": {"00:1A:79:00:00:01": ""}, "enabled channels": [], "channel blocks": {}}},
           "settings": {"hdhr tuners": "2"}}, open("$S/config.json", "w"))
EOF
CONFIG=$S/config.json HOST=localhost:8001 .venv/bin/python app.py
```

The portal is unreachable, so `/editor_data` returns no channels, and tiles and the picker
can't play. Check the layout instead, in a browser at `http://localhost:8001/multiview`:

- **Layouts:** each layout button rearranges the grid. "big" shows the divider, and dragging
  it resizes the big tile; the size survives a reload.
- **Empty tiles:** they show "Add channel", and the picker opens and says "No channels match".
- **Reload:** the layout comes back.
- **Phone width:** at 375 px wide, tiles stack and there's no horizontal scroll.
- **Saved channels with no portal:** in devtools, put a saved channel in localStorage
  (`multiview.addChannel(multiview.browserStorage(), {portal: "p1", channelId: "1"})`),
  then reload. The tile shows "This channel isn't on an enabled portal any more" with
  Remove, not a spinner.

Stop the server. Delete `.playwright-mcp/` screenshots if any were made.

Real playback is checked after deploying: only when `/streaming` shows nothing playing,
open two tiles and confirm both play. Then open a third, and confirm it says "No free tuner".

- [ ] **Step 7: Commit**

```bash
git add templates/_player.html tests/test_templates.py README.md
git commit -m "Send a preview to Multiview, and say why a preview stopped

The preview player gets a Send to Multiview button. When a preview fails it
asks the server why: no free tuner, or a player or recording needing the
tuner, gets that message and Try again instead of the dead-channel prompt.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## After the tasks

Run `.venv/bin/python -m unittest`, then ask the user before pushing, deploying to the
container (back up config first, check `/streaming` first) and merging the PR. Recording
(spec section 2) gets its own plan as PR 2.
