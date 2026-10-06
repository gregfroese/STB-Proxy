import time
import unittest
from unittest import mock

import stb

URL = "http://portal.test/stalker_portal/server/load.php"


def response(channels):
    r = mock.Mock()
    r.json.return_value = {"js": {"data": channels}}
    return r


class ChannelListCacheTest(unittest.TestCase):
    def setUp(self):
        stb.channelLists.clear()
        self.addCleanup(stb.channelLists.clear)
        patcher = mock.patch.object(stb.s, "get", return_value=response([{"id": "1"}]))
        self.get = patcher.start()
        self.addCleanup(patcher.stop)

    def fetch(self, mac="00:1A:79:00:00:01", **kwargs):
        return stb.getAllChannels(URL, mac, "token", **kwargs)

    def test_kept_for_a_day(self):
        self.assertEqual(self.fetch(), [{"id": "1"}])
        self.assertEqual(self.fetch(), [{"id": "1"}])
        self.assertEqual(self.get.call_count, 1)

    def test_refetched_when_stale_or_asked(self):
        self.fetch()
        self.fetch(refresh=True)
        self.assertEqual(self.get.call_count, 2)
        stb.channelLists[(URL, "00:1A:79:00:00:01")]["time"] = time.time() - stb.CHANNELS_TTL - 1
        self.fetch()
        self.assertEqual(self.get.call_count, 3)

    def test_failures_are_not_cached(self):
        self.get.return_value = response(None)
        self.assertIsNone(self.fetch())
        self.get.return_value = response([{"id": "1"}])
        self.assertEqual(self.fetch(), [{"id": "1"}])

    def test_each_mac_has_its_own_list(self):
        self.fetch(mac="00:1A:79:00:00:01")
        self.fetch(mac="00:1A:79:00:00:02")
        self.assertEqual(self.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
