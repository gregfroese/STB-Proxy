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
