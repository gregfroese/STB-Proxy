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


if __name__ == "__main__":
    unittest.main()
