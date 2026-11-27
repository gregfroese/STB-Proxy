"""On Demand downloads: Movies and Episodes saved as MP4 files in the Movies and TV Shows
downloads folders, for Plex, Jellyfin or anything else that reads them. No Flask here; app.py starts them and serves
their state.

A download is queued, then fetched when its portal is quiet: nothing else has streamed from
it for QUIET seconds. The portal plays one session per MAC and the newest wins, so a
download gives way to anyone who starts watching (app.py calls yieldPortal before admitting
any viewer) and picks up again later from the segment it had got to. One download runs per
portal at a time.

Its HLS is read through an ondemandsession.Session (the same link handling and eviction
rules as playback), its segments appended to <folder>/.stb-proxy-partial/<id>.ts (a hidden
folder, which Plex and Jellyfin skip), then remuxed into the library beside it:

    <Movies folder>/<Name> (<Year>)/<Name> (<Year>).mp4
    <TV Shows folder>/<Series> (<Year>)/Season 02/<Series> (<Year>) - S02E05.mp4

The list lives in downloads.json beside config.json.
"""
import copy
import json
import os
import re
import threading
import time
import uuid

import ondemandsession
import recordings

QUIET = 180  # seconds a portal must have had no viewers before a download starts on it
TICK = 15  # seconds between looks at the queue
SAVE_EVERY = 10  # seconds between saving a running download's progress
MAX_ATTEMPTS = 5  # tries in a row that get no further before a download fails
RETRY_AFTER = 120  # seconds, times the attempt number, before trying a broken download again
MIN_FREE_TO_START = recordings.MIN_FREE_TO_START
MIN_FREE_TO_CONTINUE = recordings.MIN_FREE_TO_CONTINUE
REMUX_MARGIN = recordings.REMUX_MARGIN
PARTIAL = ".stb-proxy-partial"
STATUSES = ("queued", "downloading", "done", "failed")


class Unsupported(Exception):
    """A stream that can't be saved as it is; the message is for the user."""


class Stopped(Exception):
    """The download was asked to stop: it gave way to a viewer, or was cancelled."""


def bestVariant(master):
    """The URI of the highest-bandwidth variant of a master playlist, or None."""
    best, bandwidth, pending = None, -1, None
    for line in master.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            found = re.search(r"(?<![-A-Z])BANDWIDTH=(\d+)", line)
            pending = int(found.group(1)) if found else 0
        elif line and not line.startswith("#") and pending is not None:
            if pending > bandwidth:
                best, bandwidth = line, pending
            pending = None
    return best


def resources(media):
    """The URIs of a VOD media playlist, in the order to save them: its init section (if
    any), then every segment. Raises Unsupported for what a plain append can't save."""
    if "#EXT-X-ENDLIST" not in media:
        raise Unsupported("That's a live stream, not one STB-Proxy can download")
    uris = []
    for line in media.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-KEY") and not re.search(r"METHOD=NONE\b", line):
            raise Unsupported("That stream is encrypted, so STB-Proxy can't download it")
        if line.startswith("#EXT-X-BYTERANGE"):
            raise Unsupported("That stream's layout isn't one STB-Proxy can download yet")
        if line.startswith("#EXT-X-MAP"):
            found = re.search(r'URI="([^"]*)"', line)
            if found is None or "BYTERANGE" in line:
                raise Unsupported("That stream's layout isn't one STB-Proxy can download yet")
            if found.group(1) not in uris:
                uris.append(found.group(1))
        elif line and not line.startswith("#"):
            uris.append(line)
    if not uris:
        raise Unsupported("That stream is empty")
    return uris


def libraryPath(folder, rec):
    """Where a finished download goes, as Plex and Jellyfin name them (without " (2)")."""
    names = rec["names"]
    year = names.get("year")
    if rec["kind"] == "movie":
        name = recordings.safeName("{} ({})".format(names["name"], year) if year else names["name"])
        return os.path.join(folder, name, name + ".mp4")
    show = recordings.safeName("{} ({})".format(names["series"], year) if year else names["series"])
    season, episode = names.get("season"), names.get("episode")
    seasonFolder = "Season {:02d}".format(season) if isinstance(season, int) else \
        recordings.safeName(names.get("seasonName") or "Season")
    if isinstance(season, int) and isinstance(episode, int):
        file = "{} - S{:02d}E{:02d}".format(show, season, episode)
    else:
        file = "{} - {}".format(show, names.get("episodeName") or rec["key"]["episodeId"])
    return os.path.join(folder, show, seasonFolder, recordings.safeName(file) + ".mp4")


def reserveLibraryPath(folder, rec, exists=os.path.exists):
    """libraryPath, " (2)" etc. if taken, made at once as an empty file."""
    with recordings.pathLock:
        base = libraryPath(folder, rec)[:-len(".mp4")]
        path, n = base + ".mp4", 2
        while exists(path):
            path, n = "{} ({}).mp4".format(base, n), n + 1
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "x").close()
        return path


def identity(portal, key):
    """What makes two downloads the same: the portal and the item's ids."""
    return (portal,) + tuple(sorted(key.items()))


class DownloadStore:
    """downloads.json: every download, by id, saved whole and atomically on each change."""

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
                data = json.load(f)
            items = data["downloads"]
            if not isinstance(items, list) or not all(isinstance(d, dict) and "id" in d for d in items):
                raise ValueError("not a list of downloads")
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.log.error("Couldn't read {} ({}); keeping it as {}.bad".format(self.path, e, self.path))
            try:
                os.replace(self.path, self.path + ".bad")
            except OSError:
                pass
            return {}
        return {d["id"]: d for d in items}

    def save(self):
        tmp = "{}.{}.tmp".format(self.path, uuid.uuid4().hex[:8])
        with open(tmp, "w") as f:
            json.dump({"downloads": list(self.items.values())}, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def add(self, rec):
        with self.lock:
            self.items[rec["id"]] = copy.deepcopy(rec)
            self.save()

    def update(self, id, **fields):
        with self.lock:
            rec = self.items.get(id)
            if rec is None:
                return None
            rec.update(copy.deepcopy(fields))
            self.save()
            return copy.deepcopy(rec)

    def remove(self, id):
        with self.lock:
            rec = self.items.pop(id, None)
            if rec is not None:
                self.save()
            return rec

    def get(self, id):
        with self.lock:
            rec = self.items.get(id)
            return copy.deepcopy(rec) if rec is not None else None

    def all(self):
        """Oldest first: the order they run in."""
        with self.lock:
            return sorted((copy.deepcopy(d) for d in self.items.values()), key=lambda d: d["created"])


class Downloader:
    """Queues, runs, pauses and finishes downloads, one thread per running download.

    folder(kind) gives the downloads folder for "movie" or "episode" ("" when those are off). busy(portal)
    says whether anyone else streams from the portal. admit(rec, stillQuiet) takes a slot on
    the download's portal, atomically with the viewers' admission and only if stillQuiet()
    is still true then: (mac, release) or None. mint(rec, mac) returns the
    playback link, and openSession(rec, mac) a fresh ondemandsession.Session to read it.
    remux and freeSpace stand in for ffmpeg and the disk in tests.
    """

    def __init__(self, store, folder, busy, admit, mint, openSession, log, clock=time.time,
                 remux=recordings.defaultRemux, freeSpace=recordings.defaultFreeSpace):
        self.store = store
        self.folder = folder
        self.busy = busy
        self.admit = admit
        self.mint = mint
        self.openSession = openSession
        self.log = log
        self.clock = clock
        self.remux = remux
        self.freeSpace = freeSpace
        self.lock = threading.Lock()
        self.running = {}  # portal -> job: {"id", "stop": Event, "why", "session", "release", "thread"}
        self.lastBusy = {}  # portal -> when someone last streamed from it (or STB-Proxy started)
        self.started = clock()
        self.thread = None
        self.wakeUp = threading.Event()
        for rec in self.store.all():
            if rec["status"] == "downloading":  # STB-Proxy stopped under it
                self.store.update(rec["id"], status="queued")

    # The queue

    def list(self):
        return self.store.all()

    def get(self, id):
        return self.store.get(id)

    def find(self, portal, key):
        want = identity(portal, key)
        return next((d for d in self.store.all() if identity(d["portal"], d["key"]) == want), None)

    def request(self, account, portal, key, kind, title, names, play):
        """Queue an item, unless it's already queued, running or downloaded (then that one
        is returned as it is). A failed download is queued again, keeping what it has; a
        finished one whose file has gone is downloaded again. Returns (download, queued)."""
        now = self.clock()
        with self.lock:
            existing = self.find(portal, key)
            if existing is not None:
                if existing["status"] == "failed":
                    return self.store.update(existing["id"], status="queued", error=None, attempts=0,
                                             retryAt=None, updated=now), True
                if existing["status"] != "done" or (existing["file"] and os.path.exists(existing["file"])):
                    return existing, False
                self.store.remove(existing["id"])
            rec = {
                "id": uuid.uuid4().hex[:12], "account": account, "portal": portal, "key": dict(key),
                "kind": kind, "title": title, "names": dict(names), "play": play,
                "status": "queued", "progress": 0, "segments": None, "segmentsDone": 0, "bytes": 0,
                "file": None, "size": None, "error": None, "attempts": 0, "retryAt": None,
                "created": now, "updated": now, "finished": None,
            }
            self.store.add(rec)
        self.wakeUp.set()
        return rec, True

    def cancel(self, id):
        """Stop and forget a download that isn't finished, with what it had saved. False if
        there's no such download or it's finished (delete takes those)."""
        rec = self.store.get(id)
        if rec is None or rec["status"] == "done":
            return False
        self.stopJob(id, "cancelled")
        self.store.remove(id)
        self.removePartial(rec)
        self.log.info("Download({}) of {} cancelled".format(id, rec["title"]))
        return True

    def delete(self, id):
        """Forget any download, removing its file if it's finished (the operator's choice)."""
        rec = self.store.get(id)
        if rec is None:
            return False
        if rec["status"] != "done":
            return self.cancel(id)
        self.store.remove(id)
        if rec["file"]:
            try:
                os.remove(rec["file"])
            except FileNotFoundError:
                pass
            except OSError as e:
                self.log.error("Couldn't delete {} ({})".format(rec["file"], e))
        self.log.info("Download({}) of {} deleted".format(id, rec["title"]))
        return True

    def retry(self, id):
        """Queue a failed download again, keeping what it has."""
        rec = self.store.get(id)
        if rec is None or rec["status"] != "failed":
            return False
        self.store.update(id, status="queued", error=None, attempts=0, retryAt=None, updated=self.clock())
        self.wakeUp.set()
        return True

    # Giving way

    def yieldPortal(self, portal):
        """Someone is about to watch from the portal: stop its download now, freeing the slot
        before they're admitted. It's queued again, to go on once the portal is quiet."""
        self.lastBusy[portal] = self.clock()
        with self.lock:
            job = self.running.get(portal)
        if job is not None:
            self.log.info("Download({}) gives way to a viewer on Portal({})".format(job["id"], portal))
            self.stopJob(job["id"], "paused")

    def stopJob(self, id, why):
        with self.lock:
            job = next((j for j in self.running.values() if j["id"] == id), None)
        if job is None:
            return
        job["why"] = job["why"] or why
        job["stop"].set()
        job["release"]()  # the slot is free at once; the thread notices soon after
        session = job.get("session")
        if session is not None:
            session.end("stopped")

    def quiet(self, portal, now=None):
        now = self.clock() if now is None else now
        return now - self.lastBusy.get(portal, self.started) >= QUIET

    # Running

    def start(self):
        """Look at the queue every TICK seconds (or when woken) from a background thread."""
        with self.lock:
            if self.thread is not None:
                return
            self.thread = threading.Thread(target=self.loop, daemon=True)
            self.thread.start()

    def loop(self):
        while True:
            self.wakeUp.wait(TICK)
            self.wakeUp.clear()
            try:
                self.tick()
            except Exception as e:
                self.log.error("Downloads: {}".format(e))

    def tick(self):
        """Start the next download of each quiet portal that has none running."""
        now = self.clock()
        queued = [d for d in self.store.all() if d["status"] == "queued"]
        for portal in dict.fromkeys(d["portal"] for d in queued):
            if self.busy(portal):
                self.lastBusy[portal] = now
                continue
            with self.lock:
                if portal in self.running:
                    continue
            if not self.quiet(portal, now):
                continue
            rec = next((d for d in queued if d["portal"] == portal and (d["retryAt"] or 0) <= now
                        and self.folder(d["kind"])), None)  # a kind with no folder waits
            if rec is None:
                continue
            folder = self.folder(rec["kind"])
            try:
                free = self.freeSpace(folder)
            except OSError:
                self.fail(rec["id"], "Can't reach the downloads folder {}".format(folder))
                continue
            if free < MIN_FREE_TO_START:
                self.fail(rec["id"], "There isn't enough free space in the downloads folder")
                continue
            admitted = self.admit(rec, lambda: not self.busy(portal) and self.quiet(portal))
            if admitted is None:
                self.lastBusy[portal] = now
                continue
            mac, release = admitted
            job = {"id": rec["id"], "stop": threading.Event(), "why": None, "session": None,
                   "release": release, "mac": mac}
            with self.lock:
                self.running[portal] = job
            self.store.update(rec["id"], status="downloading", updated=now)
            job["thread"] = threading.Thread(target=self.run, args=(rec["id"], job, folder), daemon=True)
            job["thread"].start()

    def fail(self, id, message):
        self.log.info("Download({}) failed: {}".format(id, message))
        self.store.update(id, status="failed", error=message, updated=self.clock())

    def run(self, id, job, folder):
        rec = self.store.get(id)
        try:
            try:
                if rec is None:
                    raise Stopped()  # cancelled before it began
                self.log.info("Download({}) of {} starts at segment {}".format(
                    id, rec["title"], rec["segmentsDone"]))
                self.fetch(rec, job, folder)
            except Exception:
                if job["stop"].is_set():  # however it showed (say, the session ended under it)
                    raise Stopped()
                raise
            job["release"]()  # the portal is done with; making the MP4 needs no slot
            self.finish(id, folder)
        except Stopped:
            if job["why"] == "paused":
                self.store.update(id, status="queued", updated=self.clock())
        except Unsupported as e:
            self.fail(id, str(e))
        except ondemandsession.Denied:
            self.fail(id, "The portal won't play that")
        except ondemandsession.NotHls:
            self.fail(id, "That isn't a stream STB-Proxy can download yet")
        except recordings.RemuxError as e:
            self.fail(id, "Couldn't make the MP4 ({})".format(e))
        except Exception as e:  # the portal or its storage let us down: try again later
            self.broken(id, e, job.get("progressed", False))
        finally:
            job["release"]()
            session = job.get("session")
            if session is not None:
                session.end("stopped")
            with self.lock:
                for portal, running in list(self.running.items()):
                    if running is job:
                        del self.running[portal]
            self.wakeUp.set()

    def broken(self, id, error, progressed):
        rec = self.store.get(id)
        if rec is None:
            return
        if isinstance(error, ondemandsession.Ended) and error.reason == "evicted":
            # Another device took the MAC's session (the newest wins): it's busy, though
            # not through STB-Proxy. Wait for quiet again.
            self.lastBusy[rec["portal"]] = self.clock()
        attempts = 1 if progressed else rec["attempts"] + 1
        if attempts >= MAX_ATTEMPTS:
            self.fail(id, "The portal kept stopping the download ({})".format(describe(error)))
            return
        self.log.info("Download({}) broke off ({}); trying again later".format(id, describe(error)))
        self.store.update(id, status="queued", attempts=attempts,
                          retryAt=self.clock() + RETRY_AFTER * attempts, updated=self.clock())

    def partialPath(self, folder, id):
        return os.path.join(folder, PARTIAL, id + ".ts")

    def fetch(self, rec, job, folder):
        """Append the rest of the item's segments to its partial file. job["progressed"] says
        whether it saved any."""
        def check():
            if job["stop"].is_set():
                raise Stopped()

        check()
        session = self.openSession(rec, job["mac"])
        job["session"] = session
        session.open(self.mint(rec, job["mac"]))
        check()
        master = session.playlist(ondemandsession.MASTER)
        variant = bestVariant(master) if ondemandsession.isMaster(master) else None
        names = resources(session.playlist(variant) if variant else master)
        done, size = rec["segmentsDone"], rec["bytes"]
        if rec["segments"] != len(names):  # a different stream than last time: start over
            done, size = 0, 0
        path = self.partialPath(folder, rec["id"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        progressed, saved = False, (None, self.clock())

        def save():
            nonlocal saved
            if saved[0] != done:
                saved = (done, self.clock())
                self.store.update(rec["id"], segments=len(names), segmentsDone=done, bytes=size,
                                  progress=min(99, int(100 * done / len(names))),
                                  **({"attempts": 0} if progressed else {}), updated=saved[1])

        with open(path, "ab") as out:
            out.truncate(size)  # drop a segment that was cut off half way
            out.seek(size)
            try:
                for i in range(done, len(names)):
                    check()
                    if i % 20 == 0 and self.freeSpace(folder) < MIN_FREE_TO_CONTINUE:
                        raise Unsupported("The downloads folder is full")
                    status, headers, chunks = session.segment(names[i])
                    got = 0
                    for chunk in chunks:
                        out.write(chunk)
                        got += len(chunk)
                    check()
                    if session.reason is not None:
                        raise ondemandsession.Ended(session.reason)
                    expected = headers.get("Content-Length")
                    if status != 200 or (expected is not None and expected.isdigit() and int(expected) != got):
                        raise ondemandsession.Ended("failed")
                    out.flush()
                    done, size, progressed = i + 1, size + got, True
                    job["progressed"] = True
                    if self.clock() - saved[1] >= SAVE_EVERY:
                        save()
            finally:
                save()  # whatever stopped it, keep the segments it has

    def finish(self, id, folder):
        """Remux the partial file into the library and mark the download done."""
        rec = self.store.get(id)
        part = self.partialPath(folder, id)
        if self.freeSpace(folder) < rec["bytes"] + REMUX_MARGIN:
            raise Unsupported("There isn't enough free space in the downloads folder to finish it")
        out = reserveLibraryPath(folder, rec)
        try:
            self.remux([part], out)
        except Exception:
            try:
                os.remove(out)
            except OSError:
                pass
            raise
        self.removePartial(rec, folder)
        if self.store.get(id) is None:  # cancelled while the MP4 was being made
            os.remove(out)
            return
        size = os.path.getsize(out)
        self.store.update(id, status="done", progress=100, file=out, size=size, error=None,
                          finished=self.clock(), updated=self.clock())
        self.log.info("Download({}) of {} done: {}".format(id, rec["title"], out))

    def removePartial(self, rec, folder=None):
        id = rec["id"]
        folder = folder or self.folder(rec["kind"])
        if not folder:
            return
        try:
            os.remove(self.partialPath(folder, id))
        except FileNotFoundError:
            pass
        except OSError as e:
            self.log.error("Couldn't delete Download({})'s partial file ({})".format(id, e))


def describe(error):
    if isinstance(error, ondemandsession.Ended):
        return {"evicted": "another device took over the stream", "failed": "the stream broke off"}.get(
            error.reason, error.reason)
    return str(error) or type(error).__name__
