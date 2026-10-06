import unittest

import logos

CHANNELS = [
    {"id": "TSN1.ca", "name": "TSN1", "alt_names": [], "country": "CA"},
    {"id": "TSN1.mt", "name": "TSN1", "alt_names": [], "country": "MT"},
    {"id": "SportsnetOne.ca", "name": "Sportsnet One", "alt_names": [], "country": "CA"},
    {"id": "Sportsnet.ca", "name": "Sportsnet", "alt_names": [], "country": "CA"},
    {"id": "SkySports.uk", "name": "Sky Sports Main Event", "alt_names": [], "country": "UK"},
    {"id": "ID.ca", "name": "Investigation Discovery", "alt_names": [], "country": "CA"},
    {"id": "ID.au", "name": "Investigation Discovery", "alt_names": [], "country": "AU"},
    {"id": "Old.ca", "name": "Old Channel", "alt_names": [], "country": "CA", "closed": "2020-01-01"},
]
LOGOS = [
    {"channel": "TSN1.ca", "feed": None, "in_use": True, "url": "https://x/tsn1-ca.png"},
    {"channel": "TSN1.mt", "feed": None, "in_use": True, "url": "https://x/tsn1-mt.png"},
    {"channel": "SportsnetOne.ca", "feed": None, "in_use": False, "url": "https://x/sn1-old.png"},
    {"channel": "SportsnetOne.ca", "feed": None, "in_use": True, "url": "https://x/sn1.png"},
    {"channel": "Sportsnet.ca", "feed": None, "in_use": True, "url": "https://x/sn.png"},
    {"channel": "Sportsnet.ca", "feed": "West", "in_use": True, "url": "https://x/sn-west.png"},
    {"channel": "SkySports.uk", "feed": None, "in_use": True, "url": "https://x/sky.png"},
    {"channel": "ID.ca", "feed": None, "in_use": True, "url": "https://x/id-ca.png"},
    {"channel": "ID.au", "feed": None, "in_use": True, "url": "https://x/id-au.png"},
    {"channel": "Old.ca", "feed": None, "in_use": True, "url": "https://x/old.png"},
]
FEEDS = [
    {"channel": "Sportsnet.ca", "id": "East", "name": "East", "alt_names": [], "is_main": True},
    {"channel": "Sportsnet.ca", "id": "West", "name": "West", "alt_names": [], "is_main": False},
]


class CleanTest(unittest.TestCase):
    def test_prefixes_tags_and_suffixes_go(self):
        self.assertEqual(logos.clean("UK | SKY SPORTS MAIN EVENT 4K"), ("UK", "SKY SPORTS MAIN EVENT"))
        self.assertEqual(logos.clean("MX | DAZN 13 - UPCOMING"), ("MX", "DAZN 13"))
        self.assertEqual(logos.clean("TSN 1 FHD"), (None, "TSN 1"))
        self.assertEqual(logos.clean("LIVE: Some Event (backup)"), (None, "Some Event"))

    def test_key_ignores_case_spacing_and_punctuation(self):
        self.assertEqual(logos.key("TSN 1"), logos.key("tsn1"))
        self.assertEqual(logos.key("A&E"), "aande")


class MatchTest(unittest.TestCase):
    def setUp(self):
        self.index = logos.buildIndex(CHANNELS, LOGOS, FEEDS)

    def test_clear_matches(self):
        self.assertEqual(logos.match(self.index, "SPORTSNET ONE 4K"), "https://x/sn1.png")  # in-use logo
        self.assertEqual(logos.match(self.index, "UK | Sky Sports Main Event HD"), "https://x/sky.png")

    def test_feeds(self):
        self.assertEqual(logos.match(self.index, "SPORTSNET WEST"), "https://x/sn-west.png")  # its own logo
        self.assertEqual(logos.match(self.index, "SPORTSNET EAST"), "https://x/sn.png")  # main feed: channel logo

    def test_ambiguous_names_get_no_logo_on_their_own(self):
        self.assertIsNone(logos.match(self.index, "TSN 1"))

    def test_closed_channels_are_skipped(self):
        self.assertIsNone(logos.match(self.index, "Old Channel"))

    def test_country_from_group_name(self):
        found = logos.matchAll(self.index, [("1", "INVESTIGATION DISCOVERY", "ENGLISH | CANADA")])
        self.assertEqual(found, {"1": "https://x/id-ca.png"})

    def test_country_from_the_groups_other_channels(self):
        found = logos.matchAll(self.index, [("1", "TSN 1 FHD", "SPORTS"), ("2", "SPORTSNET ONE", "SPORTS")])
        self.assertEqual(found["1"], "https://x/tsn1-ca.png")


if __name__ == "__main__":
    unittest.main()
