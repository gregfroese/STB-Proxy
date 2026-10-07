import time
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig
from tests.test_app_preview import CHANNELS, FakeProcess


class StreamSharingTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}, "settings": {"test streams": "false"}})
        self.client = self.app.app.test_client()
        self.app.SHARE_GRACE = 0.3
        self.processes = []

        def popen(cmd, **kwargs):
            process = FakeProcess(cmd)
            self.processes.append(process)
            return process

        for target, name, kwargs in [
            (self.app.subprocess, "Popen", {"side_effect": popen}),
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
        for stream in list(self.app.sharedStreams.values()):
            stream.end()

    def open(self, channel, ip="10.0.0.1", web=False):
        path = "/play/{}/{}".format(PORTAL, channel) + ("?web=true" if web else "")
        return self.client.get(path, environ_base={"REMOTE_ADDR": ip})

    def read(self, response, chunks=3):
        it = iter(response.response)
        return b"".join(next(it) for _ in range(chunks))

    def entries(self):
        return self.app.occupied.get(PORTAL, [])

    def test_players_on_the_same_channel_share_one_stream(self):
        plex = self.open("2", ip="10.0.0.5")
        jellyfin = self.open("2", ip="10.0.0.6")
        self.assertTrue(self.read(plex) and self.read(jellyfin))
        self.assertEqual([p.cmd[0] for p in self.processes], ["ffmpeg"])
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.entries()[0]["viewers"], 2)

    def test_joining_needs_no_free_slot_but_another_channel_does(self):
        first = self.open("2")
        self.read(first)
        self.assertEqual(self.open("2", ip="10.0.0.9").status_code, 200)  # one stream per MAC, shared
        self.assertEqual(self.open("3", ip="10.0.0.9").status_code, 503)

    def test_one_viewer_leaving_keeps_it_for_the_other(self):
        a, b = self.open("2"), self.open("2", ip="10.0.0.6")
        self.read(a)
        a.close()
        time.sleep(0.5)
        self.assertTrue(self.read(b))
        self.assertFalse(self.processes[0].killed.is_set())

    def test_it_closes_shortly_after_the_last_viewer_leaves(self):
        a = self.open("2")
        self.read(a)
        a.close()
        for _ in range(50):
            if self.processes[0].killed.is_set():
                break
            time.sleep(0.05)
        self.assertTrue(self.processes[0].killed.is_set())
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.app.sharedStreams, {})
        self.moveMac.assert_not_called()  # closed on purpose, not the MAC's fault

    def test_a_quick_reconnect_reuses_the_stream(self):
        # Jellyfin opens a channel, closes it, and opens it again to play.
        a = self.open("2")
        self.read(a)
        a.close()
        b = self.open("2")
        self.assertTrue(self.read(b))
        self.assertEqual(len(self.processes), 1)

    def test_a_stream_that_never_starts_is_not_left_behind(self):
        with mock.patch.object(self.app.stb, "getLink", return_value=None):
            self.assertEqual(self.open("2").status_code, 503)
        self.assertEqual(self.app.sharedStreams, {})
        self.assertTrue(self.read(self.open("2")))  # the next try starts afresh

    def test_a_failing_stream_moves_the_mac(self):
        a = self.open("2")
        self.read(a)
        stream = self.app.sharedStreams[(PORTAL, "2")]
        with mock.patch.object(stream.process, "wait", return_value=1):
            stream.process.killed.set()  # ffmpeg stops on its own, with an error
            for _ in range(50):
                if stream.done:
                    break
                time.sleep(0.05)
        self.moveMac.assert_called_once()

    def test_browser_previews_are_not_shared(self):
        self.read(self.open("2"))
        self.assertEqual(self.open("2", web=True).status_code, 503)  # its own stream, and the MAC is busy


if __name__ == "__main__":
    unittest.main()
