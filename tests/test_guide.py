import unittest

import guide

NOW = 1000


def entry(start, stop, name, descr=""):
    return {"start_timestamp": str(start), "stop_timestamp": str(stop), "name": name, "descr": descr}


class ProgrammesTest(unittest.TestCase):
    def test_keeps_what_has_not_finished(self):
        epg = {
            "1": [entry(500, 900, "Over"), entry(900, 1100, "On now", "x" * 500), entry(1100, 1200, "Later")],
            "2": None,
            "3": [entry("bad", 1200, "Broken"), entry(1100, 1200, "  ")],
        }
        self.assertEqual(
            guide.programmes("p", epg, NOW),
            [(900, 1100, "On now", "x" * guide.DESC_LENGTH, "p", "1"), (1100, 1200, "Later", "", "p", "1")],
        )


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.programmes = [
            (1500, 1600, "Oilers at Flames", "NHL hockey", "p", "2"),
            (900, 1100, "Hockey Night", "Leafs vs Habs", "p", "1"),
            (1200, 1300, "News", "Tonight's headlines", "p", "3"),
            (500, 900, "Old hockey", "", "p", "1"),
        ]

    def titles(self, *args, **kwargs):
        matches, total = guide.search(self.programmes, *args, **kwargs)
        return [m[2] for m in matches], total

    def test_matches_every_word_in_title_or_description_case_insensitively(self):
        self.assertEqual(self.titles("HOCKEY", NOW), (["Hockey Night", "Oilers at Flames"], 2))
        self.assertEqual(self.titles("nhl oilers", NOW), (["Oilers at Flames"], 1))
        self.assertEqual(self.titles("oilers leafs", NOW), ([], 0))

    def test_skips_finished_programmes(self):
        self.assertNotIn("Old hockey", self.titles("hockey", NOW)[0])

    def test_on_now(self):
        self.assertEqual(self.titles("", NOW, onNow=True), (["Hockey Night"], 1))

    def test_keep_narrows_channels(self):
        self.assertEqual(self.titles("hockey", NOW, keep=lambda p, c: c == "2"), (["Oilers at Flames"], 1))

    def test_limit_reports_total(self):
        self.assertEqual(self.titles("", NOW, limit=1), (["Hockey Night"], 3))


if __name__ == "__main__":
    unittest.main()
