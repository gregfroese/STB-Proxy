import json
import os
import shutil
import subprocess
import unittest

from tests.support import PORTAL, loadApp, portalConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = ["TSN 1 FHD", "TSN 4 4K", "SPORTSNET ONE", "SPORTSNET ONE 4K", "SPORTSNET 360", "Sports Max", "UK | SKY SPORTS"]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ChannelQueryTest(unittest.TestCase):
    def matches(self, text, mode):
        script = (
            "const {parseChannelQuery} = require(%s);"
            "const f = parseChannelQuery(%s, %s);"
            "console.log(JSON.stringify(f && f.error ? {error: f.error} : %s.filter(n => !f || f(n))));"
        ) % (json.dumps(os.path.join(ROOT, "static", "channel-filter.js")), json.dumps(text), json.dumps(mode), json.dumps(NAMES))
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_whole_words_keep_tsn_out_of_sportsnet(self):
        self.assertEqual(self.matches("TSN", "words"), ["TSN 1 FHD", "TSN 4 4K"])
        self.assertEqual(len(self.matches("TSN", "contains")), 5)

    def test_word_starts_with(self):
        self.assertEqual(self.matches("sport", "prefix"),
                         ["SPORTSNET ONE", "SPORTSNET ONE 4K", "SPORTSNET 360", "Sports Max", "UK | SKY SPORTS"])

    def test_and_or_not_and_phrases(self):
        self.assertEqual(self.matches("sportsnet -4k", "words"), ["SPORTSNET ONE", "SPORTSNET 360"])
        self.assertEqual(self.matches("TSN, sportsnet one", "words"),
                         ["TSN 1 FHD", "TSN 4 4K", "SPORTSNET ONE", "SPORTSNET ONE 4K"])
        self.assertEqual(self.matches('"sportsnet one" -4k', "words"), ["SPORTSNET ONE"])
        self.assertEqual(len(self.matches("-4k", "words")), 5)

    def test_exact_and_regex(self):
        self.assertEqual(self.matches(" sportsnet  one ", "exact"), ["SPORTSNET ONE"])
        self.assertEqual(self.matches("^TSN [0-9]", "regex"), ["TSN 1 FHD", "TSN 4 4K"])
        self.assertIn("error", self.matches("[", "regex"))

    def test_empty_query_keeps_everything(self):
        self.assertEqual(self.matches("  ", "words"), NAMES)


class FilterBarTest(unittest.TestCase):
    def test_editor_loads_the_filters(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        client = app.app.test_client()
        body = client.get("/editor").get_data(as_text=True)
        self.assertIn("channel-filter.js", body)
        self.assertIn("function filterMatches", body)
        self.assertEqual(client.get("/static/channel-filter.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SameLanguageEverywhereTest(unittest.TestCase):
    """The guide searches on the server (guide.parseQuery); the editor in the browser."""

    CASES = [("TSN", "words"), ("TSN", "contains"), ("sport", "prefix"), ("sportsnet -4k", "words"),
             ("TSN, sportsnet one", "words"), ('"sportsnet one" -4k', "words"), ("-4k", "prefix"),
             (" sportsnet  one ", "exact"), ("^TSN [0-9]", "regex"), ("sky sports, -max", "contains")]

    def test_python_and_javascript_agree(self):
        import guide
        script = (
            "const {parseChannelQuery} = require(%s);"
            "console.log(JSON.stringify(%s.map(([t, m]) => { const f = parseChannelQuery(t, m); return %s.filter(n => !f || f(n)); })));"
        ) % (json.dumps(os.path.join(ROOT, "static", "channel-filter.js")), json.dumps(self.CASES), json.dumps(NAMES))
        javascript = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
        python = [[n for n in NAMES if not guide.parseQuery(t, m) or guide.parseQuery(t, m)(n)] for t, m in self.CASES]
        self.assertEqual(python, javascript)
