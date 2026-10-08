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
