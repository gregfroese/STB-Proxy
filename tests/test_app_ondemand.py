"""The viewer On Demand door, /api/ondemand/* (ADR 0004, ADR 0005)."""
import unittest

from tests.support import PORTAL, loadApp, portalConfig
from tests.test_api_lineup import basic


def onDemandConfig(**overrides):
    config = {
        "portals": {PORTAL: portalConfig()},
        "blocks": {"Kids": "true"},
    }
    config.update(overrides)
    return config


class OnDemandTestCase(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, onDemandConfig())
        self.client = self.app.app.test_client()
        self.app.getSettings()["enable security"] = "true"
        self.addAccount("viewer", onDemand=True)
        self.addAccount("off", onDemand=False)
        self.addAccount("disabled", onDemand=True, enabled=False)

    def addAccount(self, username, onDemand, enabled=True):
        self.app.getAccounts().append({
            "username": username,
            "hash": self.app.accounts.hashPassword("secret"),
            "blocks": ["Kids"],
            "enabled": enabled,
            "on demand": onDemand,
            "adult on demand": False,
        })

    def get(self, path, username=None, password="secret"):
        headers = basic(username, password) if username else {}
        return self.client.get(path, headers=headers)


class GateTest(OnDemandTestCase):
    PATH = "/api/ondemand/categories"

    def assertOff(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["code"], "on_demand_off")
        self.assertTrue(response.get_json()["error"])

    def test_an_account_with_on_demand_on_gets_in(self):
        response = self.get(self.PATH, "viewer")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"categories": [], "portals": []})

    def test_an_account_with_on_demand_off_gets_404(self):
        self.assertOff(self.get(self.PATH, "off"))

    def test_the_operator_gets_404(self):
        # The operator login is what Plex and Jellyfin use; they never reach On Demand.
        self.assertOff(self.get(self.PATH, "admin", "12345"))

    def test_anonymous_gets_404_when_security_is_off(self):
        self.app.getSettings()["enable security"] = "false"
        self.assertOff(self.get(self.PATH))

    def test_anonymous_and_bad_logins_get_the_feed_challenge_when_security_is_on(self):
        self.assertEqual(self.get(self.PATH).status_code, 401)
        self.assertEqual(self.get(self.PATH, "viewer", "wrong").status_code, 401)

    def test_a_disabled_account_is_not_let_in(self):
        # A disabled Account doesn't resolve, so with security on it gets the challenge.
        self.assertEqual(self.get(self.PATH, "disabled").status_code, 401)
        self.app.getSettings()["enable security"] = "false"
        self.assertOff(self.get(self.PATH, "disabled"))

    def test_switching_off_takes_effect_on_the_next_request(self):
        self.assertEqual(self.get(self.PATH, "viewer").status_code, 200)
        self.app.accounts.findAccount(self.app.getAccounts(), "viewer")["on demand"] = False
        self.assertOff(self.get(self.PATH, "viewer"))


if __name__ == "__main__":
    unittest.main()
