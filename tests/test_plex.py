import unittest
from unittest import mock

import requests

import plex

DVRS = {
    "MediaContainer": {
        "Dvr": [
            {"key": "7", "Device": [{"key": "3", "uri": "http://other:5004"}]},
            {"key": "2", "Device": [{"key": "1", "uri": "http://proxy.test:8001"}]},
        ]
    }
}

ENTRIES = [
    {"GuideNumber": "101", "GuideName": "One", "URL": "u1", "epgId": "p11"},
    {"GuideNumber": "102", "GuideName": "Two", "URL": "u2", "epgId": "custom.two"},
]


def response(status=200, json=None):
    r = mock.Mock(status_code=status)
    r.json.return_value = json
    return r


class PlexTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("plex.requests.request")
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def calls(self):
        return [(c.args[0], c.args[1]) for c in self.request.call_args_list]

    def test_find_dvr_by_tuner_uri(self):
        self.request.return_value = response(json=DVRS)
        self.assertEqual(plex.findDvr("http://plex.test:32400", "tok", "http://proxy.test:8001"), ("2", "1"))
        kwargs = self.request.call_args.kwargs
        self.assertEqual(kwargs["headers"], {"X-Plex-Token": "tok", "Accept": "application/json"})
        self.assertEqual(kwargs["timeout"], 30)

    def test_find_dvr_no_match(self):
        self.request.return_value = response(json=DVRS)
        with self.assertRaisesRegex(plex.PlexSyncError, "no Plex DVR uses this tuner"):
            plex.findDvr("http://plex.test:32400", "tok", "http://elsewhere:8001")

    def test_find_dvr_unexpected_reply(self):
        self.request.return_value = response(json={"unexpected": True})
        with self.assertRaisesRegex(plex.PlexSyncError, "unexpected reply"):
            plex.findDvr("http://plex.test:32400", "tok", "http://proxy.test:8001")

    def test_channel_map_params(self):
        self.assertEqual(
            plex.channelMapParams(ENTRIES),
            [
                ("channelMappingByKey[101]", "p11"),
                ("channelMapping[101]", "p11"),
                ("channelMappingByKey[102]", "custom.two"),
                ("channelMapping[102]", "custom.two"),
                ("channelsEnabled", "101,102"),
            ],
        )

    def test_sync_maps_then_reloads_guide(self):
        self.request.side_effect = [response(json=DVRS), response(), response()]
        message = plex.sync("http://plex.test:32400/", "tok", "http://proxy.test:8001", ENTRIES)
        self.assertEqual(message, "Plex updated: 2 channels enabled")
        self.assertEqual(
            self.calls(),
            [
                ("GET", "http://plex.test:32400/livetv/dvrs"),
                ("PUT", "http://plex.test:32400/media/grabbers/devices/1/channelmap"),
                ("POST", "http://plex.test:32400/livetv/dvrs/2/reloadGuide"),
            ],
        )
        self.assertEqual(self.request.call_args_list[1].kwargs["params"], plex.channelMapParams(ENTRIES))

    def test_refuses_empty_lineup(self):
        with self.assertRaisesRegex(plex.PlexSyncError, "no channels are available"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", [])
        self.request.assert_not_called()

    def test_connection_error_is_readable(self):
        self.request.side_effect = requests.ConnectionError("boom")
        with self.assertRaisesRegex(plex.PlexSyncError, "couldn't reach Plex at http://plex.test:32400"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)

    def test_connection_error_on_timeout(self):
        self.request.side_effect = requests.Timeout("slow")
        with self.assertRaisesRegex(plex.PlexSyncError, "couldn't reach Plex"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)

    def test_rejected_token(self):
        self.request.return_value = response(status=401)
        with self.assertRaisesRegex(plex.PlexSyncError, "Plex rejected the token"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)

    def test_other_http_error_names_status(self):
        self.request.side_effect = [response(json=DVRS), response(status=500)]
        with self.assertRaisesRegex(plex.PlexSyncError, "HTTP 500"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)


if __name__ == "__main__":
    unittest.main()
