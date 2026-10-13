import unittest

from tests.support import PORTAL, loadApp, portalConfig
from tests.test_app_tuners import TunerTestCase


class StreamsPageTest(unittest.TestCase):
    def setUp(self):
        cfg = {"portals": {PORTAL: portalConfig()}, "settings": {"hdhr tuners": "2"}}
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def test_page_renders(self):
        body = self.client.get("/streams").get_data(as_text=True)
        self.assertIn('id="streamOut"', body)
        self.assertIn("/streaming", body)

    def test_menu_links_to_it(self):
        self.assertIn('href="/streams"', self.client.get("/guide").get_data(as_text=True))

    def test_streaming_includes_the_account_and_client_ip(self):
        self.app.occupied = {
            PORTAL: [
                {
                    "mac": "00:1A:79:00:00:01",
                    "channel name": "One",
                    "client": "10.0.0.5",
                    "account": "katie",
                    "portal name": "Test portal",
                    "start time": 123.0,
                    "viewers": 1,
                    "kinds": ["client"],
                    "accounts": ["katie"],
                }
            ]
        }
        entry = self.client.get("/streaming").get_json()[PORTAL][0]
        self.assertEqual(entry["account"], "katie")
        self.assertEqual(entry["client"], "10.0.0.5")


class SharedStreamAccountsTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})

    def test_join_records_accounts_and_count_aggregates(self):
        stream = self.app.SharedStream(("p1", "1"))
        stream.entry = {}
        stream.join("10.0.0.5", "client", None, "katie")
        stream.join("10.0.0.6", "preview", ("b", "t0"), None)
        self.assertEqual(stream.entry["viewers"], 2)
        self.assertEqual(stream.entry["kinds"], ["client", "preview"])
        self.assertEqual(stream.entry["accounts"], ["katie"])


class StopStreamTest(TunerTestCase):
    def test_stopping_a_stream_ends_it_and_frees_the_tuner(self):
        self.play("2")
        self.assertEqual(self.open(), ["2"])

        response = self.client.post("/streams/stop", data={"portal": PORTAL, "channel": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.open(), [])
        self.assertEqual(self.app.occupied.get(PORTAL, []), [])

    def test_stopping_an_unknown_stream_is_404(self):
        response = self.client.post("/streams/stop", data={"portal": PORTAL, "channel": "9"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
