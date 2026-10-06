import time
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import stb
from tests.support import PORTAL, loadApp, portalConfig

URL = "http://portal.test/stalker_portal/server/load.php"
MAC = "00:1A:79:00:00:01"


def portalClock(seconds, timezone="Europe/London"):
    return datetime.fromtimestamp(seconds, ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S")


class RecordProfileTest(unittest.TestCase):
    def setUp(self):
        stb.profileLog.clear()
        self.addCleanup(stb.profileLog.clear)
        patcher = mock.patch.object(stb, "deviceCookies", return_value={"timezone": "America/Toronto"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, sentAt, previous):
        stb.recordProfile(URL, MAC, sentAt, {"keep_alive": portalClock(previous, "America/Toronto")})

    def others(self):
        return stb.profileLog[(URL, MAC)]["others"]

    def test_our_own_requests_are_not_others(self):
        t = 1_800_000_000
        self.record(t, t - 500)  # before we started watching: unknown, ignored
        self.record(t + 60, t)  # ours
        self.record(t + 400, t + 60)  # ours
        self.assertEqual(self.others(), [])

    def test_a_request_between_ours_is_someone_else(self):
        t = 1_800_000_000
        self.record(t, t - 500)
        self.record(t + 600, t + 300)  # previous request at t+300 wasn't ours
        self.assertEqual(self.others(), [t + 300])

    def test_portal_times_are_read_in_the_announced_time_zone(self):
        self.assertEqual(stb.portalTime("2026-10-06 16:24:57", "America/Toronto"), 1791318297)
        self.assertIsNone(stb.portalTime("never", "America/Toronto"))


class ActivityPageTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.client = self.app.app.test_client()
        stb.profileLog.clear()
        self.addCleanup(stb.profileLog.clear)
        self.url = self.app.getPortals()[PORTAL]["url"]

    def seed(self, watchdogAgo, others=()):
        now = time.time()
        stb.profileLog[(self.url, MAC)] = {
            "ours": [now - 3600, now - 60], "others": list(others), "timezone": "Europe/London", "checked": now - 60,
            "profile": {"last_watchdog": portalClock(now - watchdogAgo), "watchdog_timeout": "900",
                        "now_playing_content": "TV: <b>TSN 5 FHD</b> from 2026-10-02 11:51:42 am",
                        "now_playing_type": "1", "now_playing_start": portalClock(now - 7200)},
        }

    def activity(self):
        return self.client.get("/account/activity").get_json()[0]["macs"][0]

    def test_box_on_and_what_it_watches(self):
        self.seed(watchdogAgo=120, others=[time.time() - 1800])
        a = self.activity()
        self.assertTrue(a["boxOn"])
        self.assertEqual((a["boxWatchingType"], a["boxWatching"]), ("TV", "TSN 5 FHD"))
        self.assertEqual(len(a["otherLogins"]), 1)

    def test_box_off_when_its_check_ins_stopped(self):
        self.seed(watchdogAgo=86400)
        self.assertFalse(self.activity()["boxOn"])

    def test_not_checked_yet(self):
        self.assertIsNone(self.activity()["checked"])

    def test_check_now_asks_the_portal(self):
        with mock.patch.object(self.app.stb, "getProfile") as getProfile:
            self.client.post("/account/check")
        self.assertEqual(getProfile.call_args.kwargs, {"refresh": True})


if __name__ == "__main__":
    unittest.main()
