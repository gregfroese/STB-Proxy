"""Import app.py against a throwaway config, with every portal call stubbed out."""
import importlib
import json
import os
import sys
import tempfile
from unittest import mock

PORTAL = "p1"

PORTAL_CHANNELS = [
    {"id": "1", "name": "One", "number": "101", "tv_genre_id": "9", "logo": ""},
    {"id": "2", "name": "Two", "number": "102", "tv_genre_id": "9", "logo": ""},
    {"id": "3", "name": "Three", "number": "103", "tv_genre_id": "9", "logo": ""},
]


def portalConfig(**overrides):
    portal = {
        "enabled": "true",
        "name": "Test portal",
        "url": "http://portal.test/stalker_portal/server/load.php",
        "macs": {"00:1A:79:00:00:01": "10.19.2026"},
        "streams per mac": "1",
        "proxy": "",
        "enabled channels": ["1"],
        "custom channel names": {},
        "custom channel numbers": {},
        "custom genres": {},
        "custom epg ids": {},
        "fallback channels": {},
        "channel blocks": {},
        "dead channels": [],
    }
    portal.update(overrides)
    return portal


def loadApp(testCase, config):
    tmp = tempfile.TemporaryDirectory()
    testCase.addCleanup(tmp.cleanup)
    path = os.path.join(tmp.name, "config.json")
    with open(path, "w") as f:
        json.dump(config, f)

    env = mock.patch.dict(os.environ, {"CONFIG": path, "HOST": "proxy.test:8001"})
    env.start()
    testCase.addCleanup(env.stop)

    sys.modules.pop("app", None)
    appModule = importlib.import_module("app")
    appModule.config = appModule.loadConfig()
    appModule.app.config["TESTING"] = True

    stubs = {
        "getToken": "token",
        "getProfile": {"status": 0},
        "getAllChannels": PORTAL_CHANNELS,
        "getGenreNames": {"9": "Sports"},
        "getEpg": None,
        "getShortEpg": {"1": [], "2": [], "3": []},
    }
    for name, value in stubs.items():
        patcher = mock.patch.object(appModule.stb, name, return_value=value)
        patcher.start()
        testCase.addCleanup(patcher.stop)
    return appModule
