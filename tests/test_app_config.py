import json
import os
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class ConfigSafetyTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})

    def onDisk(self):
        with open(self.app.configFile) as f:
            return json.load(f)

    def test_unreadable_config_is_never_overwritten(self):
        with open(self.app.configFile, "w") as f:
            f.write('{"portals": {"p1": {"name": "half wri')
        with open(self.app.configFile) as f:
            before = f.read()
        with self.assertRaises(SystemExit):
            self.app.loadConfig()
        with open(self.app.configFile) as f:
            self.assertEqual(f.read(), before)

    def test_missing_config_starts_empty(self):
        os.remove(self.app.configFile)
        self.assertEqual(self.app.loadConfig()["portals"], {})
        self.assertTrue(os.path.exists(self.app.configFile))

    def test_saves_swap_in_a_complete_file(self):
        self.app.saveBlocks({"NHL": "true"})
        self.assertEqual(self.onDisk()["blocks"], {"NHL": "true"})
        self.assertFalse(os.path.exists(self.app.configFile + ".tmp"))

    def test_crash_while_writing_keeps_the_old_config(self):
        before = self.onDisk()

        def dieHalfway(data, f, **kwargs):
            f.write('{"portals": ')
            raise MemoryError

        with mock.patch.object(self.app.json, "dump", side_effect=dieHalfway):
            with self.assertRaises(MemoryError):
                self.app.saveBlocks({"NHL": "true"})
        self.assertEqual(self.onDisk(), before)
        self.app.loadConfig()  # still readable


class PlayChannelListTest(unittest.TestCase):
    def setUp(self):
        cfg = {"portals": {PORTAL: portalConfig()}, "settings": {"test streams": "false"}}
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def test_channel_missing_from_cached_list_refetches_it(self):
        getAllChannels = self.app.stb.getAllChannels
        self.client.get("/play/{}/4?web=true".format(PORTAL))
        self.assertEqual(getAllChannels.call_count, 2)
        self.assertEqual(getAllChannels.call_args.kwargs, {"refresh": True})

    def test_known_channel_uses_cached_list(self):
        channels = [{"id": "2", "name": "Two", "cmd": "ffrt http://localhost/ch/2"}]
        with mock.patch.object(self.app.stb, "getAllChannels", return_value=channels) as getAllChannels, \
                mock.patch.object(self.app.stb, "getLink", return_value=None):
            self.client.get("/play/{}/2?web=true".format(PORTAL))
        self.assertEqual(getAllChannels.call_count, 1)


class HeavyWorkTest(unittest.TestCase):
    def test_xmltv_and_guide_never_parse_the_bulk_epg_at_once(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        seen = []
        with mock.patch.object(app, "buildXmltv", side_effect=lambda: seen.append(app.guideLock.locked()) or ""):
            app.app.test_client().get("/xmltv")
        self.assertEqual(seen, [True])


if __name__ == "__main__":
    unittest.main()
