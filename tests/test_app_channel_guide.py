import time
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


def entry(start, stop, name, descr=""):
    return {"start_timestamp": str(int(start)), "stop_timestamp": str(int(stop)), "name": name, "descr": descr}


class ChannelGuideTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.client = self.app.app.test_client()
        now = time.time()
        self.short = {"2": [entry(now - 7200, now - 3600, "Finished"), entry(now + 600, now + 1200, "Later"),
                            entry(now - 60, now + 600, "On now", "About it")]}
        patcher = mock.patch.object(self.app.stb, "getShortEpg", return_value=self.short)
        self.getShortEpg = patcher.start()
        self.addCleanup(patcher.stop)

    def guide(self, channelId="2", portal=PORTAL):
        return self.client.get("/channel/guide", query_string={"portal": portal, "channelId": channelId})

    def test_upcoming_programmes_in_order(self):
        programmes = self.guide().get_json()["programmes"]
        self.assertEqual([p["title"] for p in programmes], ["On now", "Later"])
        self.assertEqual(programmes[0]["desc"], "About it")
        self.assertEqual(self.getShortEpg.call_args[0][3], ["2"])

    def test_kept_for_a_while(self):
        self.guide()
        self.guide()
        self.assertEqual(self.getShortEpg.call_count, 1)

    def test_falls_back_to_the_loaded_full_guide(self):
        self.getShortEpg.return_value = None
        now = int(time.time())
        self.app.guideCache["programmes"] = [(now - 60, now + 600, "From the full guide", "", PORTAL, "3")]
        self.assertEqual([p["title"] for p in self.guide("3").get_json()["programmes"]], ["From the full guide"])

    def test_no_guide(self):
        self.getShortEpg.return_value = None
        self.assertEqual(self.guide("3").get_json(), {"programmes": []})

    def test_unknown_portal(self):
        self.assertEqual(self.guide(portal="nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
