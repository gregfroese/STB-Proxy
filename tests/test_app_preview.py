import threading
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig

CHANNELS = [
    {"id": "2", "name": "Two", "cmd": "ffrt http://localhost/ch/2"},
    {"id": "3", "name": "Three", "cmd": "ffrt http://localhost/ch/3"},
]


class FakeProcess:
    """Stands in for ffmpeg/ffprobe: streams bytes until killed."""

    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self.killed = threading.Event()
        self.stdout = self
        self.returncode = 0

    def read(self, n):
        return b"" if self.killed.wait(0.01) else b"x" * n

    def communicate(self):
        return b"", b""

    def poll(self):
        return -9 if self.killed.is_set() else None

    def kill(self):
        self.killed.set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.kill()


class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}, "settings": {"test streams": "true"}})
        self.client = self.app.app.test_client()
        self.processes = []

        def popen(cmd, **kwargs):
            process = FakeProcess(cmd)
            self.processes.append(process)
            return process

        for target, value in [
            (self.app.subprocess, {"Popen": popen}),
            (self.app.stb, {"getAllChannels": CHANNELS, "getLink": "http://stream.test/live"}),
        ]:
            for name, v in value.items():
                patcher = mock.patch.object(target, name, side_effect=v) if callable(v) else mock.patch.object(target, name, return_value=v)
                patcher.start()
                self.addCleanup(patcher.stop)
        patcher = mock.patch.object(self.app, "moveMac")
        self.moveMac = patcher.start()
        self.addCleanup(patcher.stop)

    def programs(self):
        return [p.cmd[0] for p in self.processes]

    def startStreaming(self, path):
        """Request a stream and keep reading it in the background, like a player would."""
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        chunks = iter(response.response)
        next(chunks)
        reader = threading.Thread(target=lambda: [None for _ in chunks], daemon=True)
        reader.start()
        return reader

    def test_previews_skip_the_stream_test(self):
        self.startStreaming("/play/{}/2?web=true".format(PORTAL))
        self.assertEqual(self.programs(), ["ffmpeg"])

    def test_previews_use_short_fragments_for_a_quick_start(self):
        self.startStreaming("/play/{}/2?web=true".format(PORTAL))
        cmd = self.processes[-1].cmd
        self.assertEqual(cmd[cmd.index("-frag_duration") + 1], "500000")
        self.assertIn("frag_keyframe", cmd[cmd.index("-movflags") + 1])

    def test_other_players_still_test_the_stream(self):
        self.startStreaming("/play/{}/2".format(PORTAL))
        self.assertEqual(self.programs(), ["ffprobe", "ffmpeg"])

    def test_new_preview_takes_over_the_viewers_last_one(self):
        reader = self.startStreaming("/play/{}/2?web=true".format(PORTAL))
        first = self.processes[-1]
        self.startStreaming("/play/{}/3?web=true".format(PORTAL))  # one stream per MAC: would be 503
        self.assertTrue(first.killed.is_set())
        reader.join(3)
        self.assertFalse(reader.is_alive())
        self.moveMac.assert_not_called()  # stopping a preview isn't a fault of the MAC
        self.assertEqual([o["channel id"] for o in self.app.occupied[PORTAL]], ["3"])

    def test_viewers_behind_one_proxy_are_told_apart(self):
        # Through a reverse proxy every browser has the proxy's IP; each sends its own ID.
        self.startStreaming("/play/{}/2?web=true&viewer=alice".format(PORTAL))
        alice = self.processes[-1]
        response = self.client.get("/play/{}/3?web=true&viewer=bob".format(PORTAL))
        self.assertEqual(response.status_code, 503)  # one stream per MAC, and it's alice's
        self.assertFalse(alice.killed.is_set())
        self.startStreaming("/play/{}/3?web=true&viewer=alice".format(PORTAL))
        self.assertTrue(alice.killed.is_set())

    def test_preview_never_stops_another_players_stream(self):
        self.startStreaming("/play/{}/2".format(PORTAL))  # e.g. Plex
        plex = self.processes[-1]
        response = self.client.get("/play/{}/3?web=true".format(PORTAL))
        self.assertEqual(response.status_code, 503)
        self.assertFalse(plex.killed.is_set())

    def test_preview_from_another_viewer_is_left_alone(self):
        self.startStreaming("/play/{}/2?web=true".format(PORTAL))
        other = self.processes[-1]
        response = self.client.get("/play/{}/3?web=true".format(PORTAL), environ_base={"REMOTE_ADDR": "10.0.0.9"})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(other.killed.is_set())


if __name__ == "__main__":
    unittest.main()
