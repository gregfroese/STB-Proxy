import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


def accountConfig(**overrides):
    config = {
        "portals": {PORTAL: portalConfig(**{"channel blocks": {"2": "Kids", "3": "Sports"}})},
        "blocks": {"Kids": "true", "Sports": "true"},
    }
    config.update(overrides)
    return config


class AccountsPageTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, accountConfig())
        self.client = self.app.app.test_client()

    def test_nav_links_to_accounts(self):
        self.assertIn('href="/accounts"', self.client.get("/blocks").get_data(as_text=True))

    def test_page_lists_accounts_and_offers_blocks(self):
        self.app.getAccounts().append(
            {"username": "katie", "hash": "h", "blocks": ["Kids"], "enabled": True}
        )
        body = self.client.get("/accounts").get_data(as_text=True)
        self.assertIn("katie", body)
        self.assertIn("Kids", body)
        self.assertIn("Sports", body)

    def test_create_persists_hashed_password(self):
        response = self.client.post("/accounts/create", data={
            "username": "katie", "password": "secret", "blocks": ["Kids"], "enabled": "true"})
        self.assertEqual(response.status_code, 302)
        account = self.app.getAccounts()[0]
        self.assertEqual(account["username"], "katie")
        self.assertEqual(account["blocks"], ["Kids"])
        self.assertTrue(account["enabled"])
        self.assertTrue(self.app.accounts.verifyPassword("secret", account["hash"]))
        self.assertNotIn("secret", account["hash"])
        self.assertNotIn("secret", self.client.get("/accounts").get_data(as_text=True))

    def test_create_needs_a_username_and_password(self):
        self.client.post("/accounts/create", data={"username": "", "password": "x"})
        self.client.post("/accounts/create", data={"username": "katie", "password": ""})
        self.assertEqual(self.app.getAccounts(), [])

    def test_duplicate_username_is_refused(self):
        self.client.post("/accounts/create", data={"username": "katie", "password": "x"})
        self.client.post("/accounts/create", data={"username": "katie", "password": "y"})
        self.assertEqual(len(self.app.getAccounts()), 1)

    def test_edit_assigns_blocks(self):
        self.client.post("/accounts/create", data={"username": "katie", "password": "x", "blocks": ["Kids"]})
        self.client.post("/accounts/update", data={"username": "katie", "blocks": ["Sports"]})
        self.assertEqual(self.app.getAccounts()[0]["blocks"], ["Sports"])

    def test_toggle_revokes_without_losing_blocks(self):
        self.client.post("/accounts/create", data={"username": "katie", "password": "x", "blocks": ["Kids"]})
        self.client.post("/accounts/toggle", data={"username": "katie", "enabled": "false"})
        account = self.app.getAccounts()[0]
        self.assertFalse(account["enabled"])
        self.assertEqual(account["blocks"], ["Kids"])

    def test_reset_password(self):
        self.client.post("/accounts/create", data={"username": "katie", "password": "old"})
        self.client.post("/accounts/password", data={"username": "katie", "password": "new"})
        account = self.app.getAccounts()[0]
        self.assertFalse(self.app.accounts.verifyPassword("old", account["hash"]))
        self.assertTrue(self.app.accounts.verifyPassword("new", account["hash"]))

    def test_delete(self):
        self.client.post("/accounts/create", data={"username": "katie", "password": "x"})
        self.client.post("/accounts/delete", data={"username": "katie"})
        self.assertEqual(self.app.getAccounts(), [])

    def test_unknown_accounts_are_refused(self):
        self.client.post("/accounts/update", data={"username": "nope", "blocks": ["Kids"]})
        self.client.post("/accounts/delete", data={"username": "nope"})
        self.client.post("/accounts/password", data={"username": "nope", "password": "x"})
        self.client.post("/accounts/toggle", data={"username": "nope", "enabled": "true"})
        self.assertEqual(self.app.getAccounts(), [])


class HiddenBlockTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, accountConfig(**{"hidden blocks": ["Kids"]}))
        self.client = self.app.app.test_client()

    def test_hidden_blocks_are_not_offered_and_never_leak(self):
        self.app.getAccounts().append(
            {"username": "katie", "hash": "h", "blocks": ["Kids", "Sports"], "enabled": True}
        )
        body = self.client.get("/accounts").get_data(as_text=True)
        self.assertNotIn("Kids", body)
        self.assertIn("Sports", body)

    def test_hidden_blocks_cannot_be_assigned(self):
        self.client.post("/accounts/create", data={"username": "katie", "password": "x", "blocks": ["Kids"]})
        self.assertEqual(self.app.getAccounts()[0]["blocks"], [])


class CascadeTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, accountConfig(accounts=[
            {"username": "katie", "hash": "h", "blocks": ["Kids", "Sports"], "enabled": True},
        ]))
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def test_rename_rewrites_every_account(self):
        self.client.post("/blocks/rename", data={"name": "Kids", "newName": "Children"})
        self.assertEqual(self.app.getAccounts()[0]["blocks"], ["Children", "Sports"])

    def test_pruning_an_emptied_block_strips_it_from_accounts(self):
        self.client.post("/channels/blocks", json={
            "channels": [{"portal": PORTAL, "channelId": "3"}], "block": "Sports", "action": "remove"})
        self.assertEqual(self.app.getAccounts()[0]["blocks"], ["Kids"])


class NoAccountsConfigTest(unittest.TestCase):
    def test_a_config_without_accounts_loads_and_behaves_as_before(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.assertEqual(app.getAccounts(), [])
        self.assertEqual([e["GuideNumber"] for e in app.app.test_client().get("/lineup.json").get_json()], ["101"])


if __name__ == "__main__":
    unittest.main()
