import json
import os
import time
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig
from tests.test_logos import CHANNELS, FEEDS, LOGOS

import logos

PORTAL_CHANNELS = [
    {"id": "1", "name": "TSN 1 FHD", "number": "101", "tv_genre_id": "9", "logo": "", "cmd": "ffrt http://localhost/ch/1"},
    {"id": "2", "name": "SPORTSNET ONE", "number": "102", "tv_genre_id": "9", "logo": "", "cmd": "ffrt http://localhost/ch/2"},
    {"id": "3", "name": "Mystery Channel", "number": "103", "tv_genre_id": "9", "logo": "", "cmd": "ffrt http://localhost/ch/3"},
    {"id": "4", "name": "Own Logo", "number": "104", "tv_genre_id": "9", "logo": "77.png", "cmd": "ffrt http://localhost/ch/4"},
]


class LogoTest(unittest.TestCase):
    def setUp(self):
        cfg = {"portals": {PORTAL: portalConfig(**{
            "enabled channels": ["1", "2", "3", "4"],
            "custom logos": {"3": "https://mine/mystery.png"},
        })}}
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        for name, value in {"getAllChannels": PORTAL_CHANNELS, "getEpg": {"1": [], "2": [], "3": [], "4": []}}.items():
            patcher = mock.patch.object(self.app.stb, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app.logoIndex.update(index=logos.buildIndex(CHANNELS, LOGOS, FEEDS), time=time.time())
        self.app.portalLogos.clear()

    def rows(self):
        return {r["channelId"]: r for r in self.client.get("/editor_data").get_json()["data"]}

    def test_yours_then_portals_then_matched(self):
        rows = self.rows()
        self.assertEqual(rows["1"]["logo"], "https://x/tsn1-ca.png")  # matched (Canada, from the group)
        self.assertEqual(rows["3"]["logo"], "https://mine/mystery.png")  # yours
        self.assertEqual(rows["3"]["autoLogo"], "")
        self.assertEqual(rows["4"]["logo"], "http://portal.test/stalker_portal/misc/logos/320/77.png")  # portal's

    def test_editor_saves_and_clears_your_logo(self):
        form = {k: "[]" for k in ("enabledEdits", "numberEdits", "nameEdits", "genreEdits", "epgEdits", "fallbackEdits")}
        form["logoEdits"] = json.dumps([{"portal": PORTAL, "channel id": "2", "logo": " https://mine/sn1.png "},
                                        {"portal": PORTAL, "channel id": "3", "logo": ""}])
        self.client.post("/editor/save", data=form)
        self.assertEqual(self.app.getPortals()[PORTAL]["custom logos"], {"2": "https://mine/sn1.png"})
        rows = self.rows()
        self.assertEqual(rows["2"]["logo"], "https://mine/sn1.png")
        self.assertEqual(rows["2"]["autoLogo"], "https://x/sn1.png")

    def test_playlist_and_xmltv_carry_logos(self):
        playlist = self.client.get("/playlist").get_data(as_text=True)
        self.assertIn('tvg-logo="https://x/sn1.png"', playlist)
        self.assertIn('tvg-logo="https://mine/mystery.png"', playlist)
        xml = self.client.get("/xmltv").get_data(as_text=True)
        self.assertIn('<icon src="https://x/sn1.png"', xml)

    def test_playlist_name_sort_survives_commas_in_logo_urls(self):
        self.app.getPortals()[PORTAL]["custom logos"] = {"1": "https://mine/a,b.png"}
        self.app.getSettings()["sort playlist by channel name"] = "true"
        playlist = self.client.get("/playlist").get_data(as_text=True)
        names = [line.rsplit('",', 1)[1] for line in playlist.splitlines() if line.startswith("#EXTINF")]
        self.assertEqual(names, sorted(names))

    def test_matching_can_be_switched_off(self):
        self.app.getSettings()["match logos"] = "false"
        rows = self.rows()
        self.assertEqual(rows["1"]["logo"], "")
        self.assertEqual(rows["3"]["logo"], "https://mine/mystery.png")  # yours still count


class LogoIndexTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.refresh = self.app.realRefreshLogoIndex

    def response(self, data):
        r = mock.Mock()
        r.json.return_value = data
        return r

    def test_downloads_builds_and_saves_the_index(self):
        responses = [self.response(CHANNELS), self.response(LOGOS), self.response(FEEDS)]
        with mock.patch.object(self.app.requests, "get", side_effect=responses) as get:
            self.refresh()
        self.assertEqual(get.call_count, 3)
        self.assertIn("tsn1", self.app.logoIndex["index"])
        with open(self.app.logoIndexFile()) as f:
            self.assertIn("tsn1", json.load(f))

    def test_recent_index_on_disk_is_used_without_downloading(self):
        with open(self.app.logoIndexFile(), "w") as f:
            json.dump({"saved": [["CA", "https://x/s.png"]]}, f)
        with mock.patch.object(self.app.requests, "get") as get:
            self.refresh()
        get.assert_not_called()
        self.assertEqual(self.app.logoIndex["index"], {"saved": [["CA", "https://x/s.png"]]})

    def test_failed_download_keeps_what_there_is(self):
        with open(self.app.logoIndexFile(), "w") as f:
            json.dump({"old": []}, f)
        old = time.time() - self.app.LOGO_INDEX_MAX_AGE - 10
        os.utime(self.app.logoIndexFile(), (old, old))
        with mock.patch.object(self.app.requests, "get", side_effect=OSError("offline")):
            self.refresh()
        self.assertEqual(self.app.logoIndex["index"], {"old": []})


if __name__ == "__main__":
    unittest.main()
