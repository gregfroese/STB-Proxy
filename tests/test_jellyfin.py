import json
import unittest
from unittest import mock

import jellyfin
from tests.support import PORTAL, loadApp, portalConfig

J = "http://jellyfin.test:8096"
STB = "http://proxy.test:8001"


def response(status=200, body=None, bom=False):
    r = mock.Mock()
    r.status_code = status
    text = json.dumps(body if body is not None else {})
    r.content = (("﻿" if bom else "") + text).encode("utf-8")
    return r


class FakeJellyfin:
    """Answers like Jellyfin's API and records what was sent."""

    def __init__(self, tuners=(), guides=(), taskState="Idle"):
        self.config = {"TunerHosts": list(tuners), "ListingProviders": list(guides)}
        self.taskState = taskState
        self.sent = []

    def __call__(self, method, url, json=None, params=None, headers=None, timeout=None):
        path = url[len(J):]
        self.sent.append((method, path, json))
        if "wrong" in headers["Authorization"]:
            return response(401)
        if (method, path) == ("GET", "/System/Configuration/livetv"):
            return response(body=self.config, bom=True)
        if (method, path) == ("POST", "/LiveTv/TunerHosts"):
            same = [i for i, t in enumerate(self.config["TunerHosts"]) if json.get("Id") and t.get("Id") == json["Id"]]
            if same:
                self.config["TunerHosts"][same[0]] = json
            else:
                self.config["TunerHosts"].append(dict(json, Id="new"))
            return response()
        if (method, path) == ("POST", "/LiveTv/ListingProviders"):
            self.config["ListingProviders"].append(json)
            return response()
        if (method, path) == ("GET", "/ScheduledTasks"):
            return response(body=[{"Key": "RefreshGuide", "Id": "abc", "State": self.taskState}], bom=True)
        if path == "/ScheduledTasks/Running/abc":
            return response(204)
        return response(404)


class JellyfinModuleTest(unittest.TestCase):
    def fake(self, **kwargs):
        fake = FakeJellyfin(**kwargs)
        patcher = mock.patch.object(jellyfin.requests, "request", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_setup_adds_a_tuner_and_guide_once(self):
        fake = self.fake()
        self.assertIn("added the tuner", jellyfin.setup(J, "key", STB))
        tuner = fake.config["TunerHosts"][0]
        self.assertEqual((tuner["Type"], tuner["Url"], tuner["TunerCount"]), ("m3u", STB + "/playlist", 0))
        self.assertEqual(fake.config["ListingProviders"][0]["Path"], STB + "/xmltv")
        self.assertIn(("POST", "/ScheduledTasks/Running/abc", None), fake.sent)  # loads them straight away
        refreshes = len([p for m, p, _ in fake.sent if m == "POST" and p.startswith("/ScheduledTasks/Running")])
        self.assertIn("already has", jellyfin.setup(J, "key", STB))
        self.assertEqual(len(fake.config["TunerHosts"]), 1)
        # pressing it again reloads Jellyfin's channels
        self.assertEqual(len([p for m, p, _ in fake.sent if m == "POST" and p.startswith("/ScheduledTasks/Running")]), refreshes + 1)

    def test_setup_lifts_a_stream_limit_on_an_existing_tuner(self):
        # A limit of 1 let a stream Jellyfin wrongly thought was open block all playback.
        existing = {"Id": "t1", "Type": "m3u", "Url": STB + "/playlist", "TunerCount": 1, "FriendlyName": "Mine", "IgnoreDts": True}
        fake = self.fake(tuners=[existing], guides=[{"Path": STB + "/xmltv"}])
        self.assertIn("stream limit to none", jellyfin.setup(J, "key", STB))
        self.assertEqual(fake.config["TunerHosts"], [dict(existing, TunerCount=0)])  # same tuner, other settings kept

    def test_status(self):
        self.fake(tuners=[{"Url": STB + "/playlist"}])
        self.assertEqual(jellyfin.status(J, "key", STB), {"tuner": True, "guide": False})

    def test_refresh_restarts_a_running_refresh(self):
        fake = self.fake(taskState="Running")
        jellyfin.refresh(J, "key")
        self.assertEqual([m for m, p, _ in fake.sent if p.startswith("/ScheduledTasks/Running")], ["DELETE", "POST"])

    def test_errors_say_what_went_wrong(self):
        self.fake()
        with self.assertRaisesRegex(jellyfin.JellyfinError, "rejected the API key"):
            jellyfin.refresh(J, "wrong")
        with mock.patch.object(jellyfin.requests, "request", side_effect=jellyfin.requests.ConnectionError()):
            with self.assertRaisesRegex(jellyfin.JellyfinError, "couldn't reach Jellyfin"):
                jellyfin.refresh(J, "key")


class JellyfinAppTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig(**{"channel blocks": {"2": ["NHL"]}})},
                                  "settings": {"jellyfin url": J, "jellyfin api key": "key"}})
        self.client = self.app.app.test_client()
        self.app.PLEX_RETRY_DELAYS = [60]
        timer = mock.patch.object(self.app.threading, "Timer")
        self.Timer = timer.start()
        self.addCleanup(timer.stop)
        refresh = mock.patch.object(self.app.jellyfin, "refresh", return_value="Jellyfin is refreshing its channels and guide")
        self.refresh = refresh.start()
        self.addCleanup(refresh.stop)

    def test_block_switch_refreshes_jellyfin(self):
        self.client.post("/blocks/toggle", data={"name": "NHL", "enabled": "true"})
        self.refresh.assert_called_once_with(J, "key")
        self.assertTrue(self.app.lastJellyfinSync["ok"])

    def test_both_servers_are_synced(self):
        self.app.getSettings().update({"plex url": "http://plex.test:32400", "plex token": "tok"})
        with mock.patch.object(self.app.plex, "sync", return_value="Plex updated: 1 channels enabled") as plexSync:
            category, message = self.app.syncPlex()
        plexSync.assert_called_once()
        self.refresh.assert_called_once()
        self.assertEqual(category, "success")
        self.assertIn("Plex updated", message)
        self.assertIn("Jellyfin is refreshing", message)

    def test_jellyfin_failure_is_retried(self):
        self.refresh.side_effect = self.app.jellyfin.JellyfinError("couldn't reach Jellyfin")
        category, _ = self.app.syncPlex()
        self.assertEqual(category, "danger")
        self.Timer.assert_called_once()
        self.assertIsNotNone(self.app.syncRetry["at"])
        self.assertIn("Trying again at", self.client.get("/blocks").get_data(as_text=True))

    def test_settings_keep_the_key_and_setup_uses_them(self):
        form = {k: v for k, v in self.app.getSettings().items() if k not in ("api token", "jellyfin api key")}
        self.client.post("/settings/save", data=form)
        self.assertEqual(self.app.getSettings()["jellyfin api key"], "key")
        with mock.patch.object(self.app.jellyfin, "setup", return_value="Added STB-Proxy to Jellyfin's Live TV") as setup:
            self.client.post("/settings/jellyfin-setup")
        self.assertEqual(setup.call_args.args, (J, "key", "http://proxy.test:8001"))
        self.assertIn("Added STB-Proxy", self.client.get("/settings").get_data(as_text=True))

    def test_api_reports_jellyfin(self):
        token = self.app.getSettings()["api token"]
        self.client.post("/api/sync", headers={"Authorization": "Bearer " + token})
        status = self.client.get("/api/jellyfin", headers={"Authorization": "Bearer " + token}).get_json()
        self.assertEqual((status["configured"], status["ok"]), (True, True))
        self.assertIn("jellyfin", self.client.get("/api/status", headers={"Authorization": "Bearer " + token}).get_json())


if __name__ == "__main__":
    unittest.main()
