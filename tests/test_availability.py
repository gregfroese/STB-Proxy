import unittest

import availability


def portal(enabled=(), blocks=None, dead=()):
    return {
        "enabled channels": list(enabled),
        "channel blocks": dict(blocks or {}),
        "dead channels": list(dead),
    }


class LineupChannelsTest(unittest.TestCase):
    """What Plex and Jellyfin get: a hidden block's channels stay in STB-Proxy."""

    def test_a_hidden_blocks_channels_are_left_out(self):
        p = portal(blocks={"1": ["Private"], "2": ["Private", "NHL"], "3": ["NHL"]}, enabled=["4"])
        blocks = {"Private": "true", "NHL": "true"}
        self.assertEqual(availability.lineupChannels(p, blocks, ["Private"]), {"2", "3", "4"})
        self.assertEqual(availability.availableChannels(p, blocks), {"1", "2", "3", "4"})  # in STB-Proxy

    def test_a_channel_enabled_on_its_own_still_goes(self):
        p = portal(blocks={"1": ["Private"]}, enabled=["1"], dead=["5"])
        self.assertEqual(availability.lineupChannels(p, {"Private": "true"}, ["Private"]), {"1"})

    def test_dead_channels_are_still_left_out(self):
        p = portal(blocks={"1": ["NHL"], "2": ["NHL"]}, dead=["2"])
        self.assertEqual(availability.lineupChannels(p, {"NHL": "true"}, []), {"1"})


class AvailableChannelsTest(unittest.TestCase):
    def test_individually_enabled(self):
        self.assertEqual(availability.availableChannels(portal(["1", "2"]), {}), {"1", "2"})

    def test_block_on_adds_its_channels(self):
        p = portal(["1"], {"2": "NHL", "3": "NHL"})
        self.assertEqual(availability.availableChannels(p, {"NHL": "true"}), {"1", "2", "3"})

    def test_block_off_or_unknown_adds_nothing(self):
        p = portal(["1"], {"2": "NHL", "3": "NBA"})
        self.assertEqual(availability.availableChannels(p, {"NHL": "false"}), {"1"})

    def test_enabled_channel_stays_when_its_block_is_off(self):
        p = portal(["2"], {"2": "NHL"})
        self.assertEqual(availability.availableChannels(p, {"NHL": "false"}), {"2"})

    def test_dead_channel_hidden_even_if_enabled_and_in_block_that_is_on(self):
        p = portal(["1", "2"], {"2": "NHL", "3": "NHL"}, dead=["2", "3"])
        self.assertEqual(availability.availableChannels(p, {"NHL": "true"}), {"1"})

    def test_channel_in_several_blocks_is_on_if_any_block_is(self):
        p = portal(blocks={"2": ["NHL", "Sports"]})
        self.assertEqual(availability.availableChannels(p, {"NHL": "false", "Sports": "true"}), {"2"})
        self.assertEqual(availability.availableChannels(p, {"NHL": "false", "Sports": "false"}), set())

    def test_missing_keys_mean_nothing_extra(self):
        self.assertEqual(availability.availableChannels({"enabled channels": ["1"]}, {}), {"1"})


class BlocksTest(unittest.TestCase):
    def setUp(self):
        self.portals = {
            "a": portal(blocks={"1": "NHL", "2": "NHL", "3": "NBA"}, dead=["2"]),
            "b": portal(blocks={"9": "NHL"}),
        }

    def test_block_names_across_portals(self):
        self.assertEqual(availability.blockNames(self.portals), {"NHL", "NBA"})

    def test_prune_drops_blocks_no_channel_names(self):
        blocks = {"NHL": "true", "Old": "true", "NBA": "false"}
        self.assertEqual(availability.pruneBlocks(self.portals, blocks), {"NHL": "true", "NBA": "false"})

    def test_summaries_count_channels_and_dead_sorted_by_name(self):
        self.assertEqual(
            availability.blockSummaries(self.portals, {"NHL": "true"}),
            [
                {"name": "NBA", "enabled": False, "hidden": False, "channels": 1, "dead": 0},
                {"name": "NHL", "enabled": True, "hidden": False, "channels": 3, "dead": 1},
            ],
        )

    def test_channel_counts_in_each_of_its_blocks(self):
        portals = {"a": portal(blocks={"1": ["NHL", "Sports"], "2": ["Sports"]})}
        self.assertEqual(availability.blockNames(portals), {"NHL", "Sports"})
        self.assertEqual(
            [(s["name"], s["channels"]) for s in availability.blockSummaries(portals, {})],
            [("NHL", 1), ("Sports", 2)],
        )

    def test_summaries_mark_hidden_blocks(self):
        summaries = availability.blockSummaries(self.portals, {}, ["NBA"])
        self.assertEqual([(s["name"], s["hidden"]) for s in summaries], [("NBA", True), ("NHL", False)])

    def test_rename_across_portals_keeps_other_blocks(self):
        portals = {"a": portal(blocks={"1": ["NHL", "Sports"], "2": ["NBA"]}), "b": portal(blocks={"9": ["NHL"]})}
        availability.renameBlock(portals, "NHL", "Hockey")
        self.assertEqual(portals["a"]["channel blocks"], {"1": ["Hockey", "Sports"], "2": ["NBA"]})
        self.assertEqual(portals["b"]["channel blocks"], {"9": ["Hockey"]})

    def test_no_blocks(self):
        self.assertEqual(availability.blockSummaries({"a": portal()}, {}), [])


class BlockNamesTest(unittest.TestCase):
    def test_parse_trims_and_drops_blanks_and_repeats(self):
        self.assertEqual(availability.parseBlockNames(" NHL, Sports ,, NHL"), ["NHL", "Sports"])
        self.assertEqual(availability.parseBlockNames(""), [])

    def test_normalise_converts_single_names_to_lists(self):
        self.assertEqual(
            availability.normaliseChannelBlocks({"1": "NHL", "2": ["NHL", " Sports"], "3": "", "4": []}),
            {"1": ["NHL"], "2": ["NHL", "Sports"]},
        )


if __name__ == "__main__":
    unittest.main()
