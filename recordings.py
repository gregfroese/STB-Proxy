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
