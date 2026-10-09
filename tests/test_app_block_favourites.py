import unittest

from tests.support import PORTAL, loadApp, portalConfig


class BlockFavouritesTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{
                "channel blocks": {"1": ["NHL"], "2": ["NHL", "Movies"], "3": ["Movies"]},
                "favourite channels": ["3"],
            })},
            "blocks": {"NHL": "true", "Movies": "true"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def mark(self, channelId, block, on=True):
        return self.client.post("/block/favourite", data={
            "portal": PORTAL, "channelId": channelId, "block": block, "favourite": "true" if on else "false"})

    def rows(self):
        return {r["channelId"]: r for r in self.client.get("/editor_data").get_json()["data"]}

    def test_a_favourite_in_one_block_isnt_in_others_or_overall(self):
        self.assertEqual(self.mark("2", "NHL").get_json(), {"blockFavourites": ["NHL"]})
        rows = self.rows()
        self.assertEqual(rows["2"]["blockFavourites"], ["NHL"])
        self.assertFalse(rows["2"]["favourite"])  # overall favourites are separate
        self.assertEqual(rows["1"]["blockFavourites"], [])
        self.assertEqual(self.mark("2", "Movies").get_json(), {"blockFavourites": ["Movies", "NHL"]})
        self.assertEqual(self.mark("2", "NHL", on=False).get_json(), {"blockFavourites": ["Movies"]})

    def test_only_a_channel_in_the_block_can_be_its_favourite(self):
        self.assertEqual(self.mark("3", "NHL").status_code, 400)
        self.assertEqual(self.client.post("/block/favourite", data={"portal": "nope", "channelId": "1", "block": "NHL",
                                                                    "favourite": "true"}).status_code, 404)

    def test_leaving_the_block_or_renaming_it_keeps_them_right(self):
        self.mark("1", "NHL")
        self.mark("2", "NHL")
        self.client.post("/blocks/rename", data={"name": "NHL", "newName": "Hockey"})
        self.assertEqual(self.rows()["1"]["blockFavourites"], ["Hockey"])
        self.client.post("/channel/blocks", data={"portal": PORTAL, "channelId": "1", "blocks": []})
        self.assertEqual(self.rows()["1"]["blockFavourites"], [])  # left the block
        self.assertEqual(self.rows()["2"]["blockFavourites"], ["Hockey"])
        self.client.post("/channel/blocks", data={"portal": PORTAL, "channelId": "2", "blocks": ["Movies"]})
        self.assertEqual(self.app.config["block favourites"], {})  # the block is gone


if __name__ == "__main__":
    unittest.main()
