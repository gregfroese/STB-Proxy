"""stb.py's On Demand catalogue calls (type=vod), against a faked HTTP session."""
import unittest
from unittest import mock

import stb

URL = "http://portal.test/stalker_portal/server/load.php"
MAC = "00:1A:79:00:00:01"


def response(js):
    r = mock.Mock()
    r.json.return_value = {"js": js}
    return r


class OnDemandCallsTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(stb.s, "get")
        self.get = patcher.start()
        self.addCleanup(patcher.stop)

    def params(self):
        return self.get.call_args.kwargs["params"]

    def test_categories_are_read_with_the_session_token(self):
        self.get.return_value = response([
            {"id": "*", "title": "All", "alias": "*"},
            {"id": "12", "title": "Action", "alias": "action", "censored": 0},
        ])
        categories = stb.getOnDemandCategories(URL, MAC, "token")
        self.assertEqual([c["id"] for c in categories], ["*", "12"])
        self.assertEqual(self.params()["type"], "vod")
        self.assertEqual(self.params()["action"], "get_categories")
        self.assertEqual(self.get.call_args.kwargs["headers"]["Authorization"], "Bearer token")
        self.assertEqual(self.get.call_args.kwargs["cookies"]["mac"], MAC)

    def test_a_page_of_all_items_newest_first(self):
        self.get.return_value = response({
            "total_items": "30", "max_page_items": 14, "cur_page": 0,
            "data": [{"id": "5", "name": "Five"}],
        })
        page = stb.getOnDemandPage(URL, MAC, "token", 2)
        self.assertEqual(page, {"total": 30, "pageSize": 14, "items": [{"id": "5", "name": "Five"}]})
        params = self.params()
        self.assertEqual((params["type"], params["action"]), ("vod", "get_ordered_list"))
        self.assertEqual((params["category"], params["sortby"], params["p"]), ("*", "added", 2))

    def test_failures_return_none(self):
        self.get.return_value = response(False)
        self.assertIsNone(stb.getOnDemandCategories(URL, MAC, "token"))
        self.assertIsNone(stb.getOnDemandPage(URL, MAC, "token", 1))
        self.get.side_effect = OSError("down")
        self.assertIsNone(stb.getOnDemandCategories(URL, MAC, "token"))
        self.assertIsNone(stb.getOnDemandPage(URL, MAC, "token", 1))


if __name__ == "__main__":
    unittest.main()
