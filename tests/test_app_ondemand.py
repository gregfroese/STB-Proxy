"""The viewer On Demand door, /api/ondemand/* (ADR 0004, ADR 0005)."""
import unittest
from unittest import mock

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
        self.assertEqual(response.get_json()["categories"], [])

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


def row(id, name, cat0, cat1="0", cat2="0", series=0):
    return {"id": str(id), "name": name, "o_name": name, "year": "2021",
            "added": "2026-10-0{} 12:00:00".format(id % 9 + 1), "rating_kinopoisk": "6.5",
            "category_id": cat0, "category_id_1": cat1, "category_id_2": cat2, "is_series": series}


class FakePortals:
    """The portals' On Demand catalogues, served through the stubbed stb calls (no network)."""

    def __init__(self, testCase, app, catalogues):
        self.catalogues = catalogues  # {portal url: {"categories": [...], "items": [...]}}
        self.pages = []
        for name, fake in (("getOnDemandCategories", self.categories), ("getOnDemandPage", self.page)):
            patcher = mock.patch.object(app.stb, name, side_effect=fake)
            patcher.start()
            testCase.addCleanup(patcher.stop)

    def categories(self, url, mac, token, proxy=None):
        return self.catalogues[url]["categories"]

    def page(self, url, mac, token, page, proxy=None):
        self.pages.append((url, page))
        items = self.catalogues[url]["items"]
        return {"total": len(items), "pageSize": 14, "items": items[(page - 1) * 14:page * 14]}


URL1 = "http://portal.test/stalker_portal/server/load.php"
URL2 = "http://other.test/stalker_portal/server/load.php"
OFF_URL = "http://off.test/stalker_portal/server/load.php"


class CategoriesTest(OnDemandTestCase):
    def setUp(self):
        self.app = loadApp(self, onDemandConfig(portals={
            "p1": portalConfig(name="First", url=URL1),
            "p2": portalConfig(name="Second", url=URL2),
            "p3": portalConfig(name="Switched off", url=OFF_URL, enabled="false"),
        }))
        self.client = self.app.app.test_client()
        self.app.getSettings()["enable security"] = "true"
        self.addAccount("viewer", onDemand=True)
        self.fake = FakePortals(self, self.app, {
            URL1: {"categories": [
                {"id": "*", "title": "All", "alias": "*"},
                {"id": "10", "title": "Action", "alias": "action", "censored": 0},
                {"id": "11", "title": "Kids  Movies", "alias": "kids", "censored": 0},
                {"id": "12", "title": "Empty", "alias": "empty", "censored": 0},
                {"id": "coming_soon", "title": "Coming soon", "alias": "coming_soon"},
            ], "items": [row(i, "Film {}".format(i), "10") for i in range(20)]
                        + [row(20, "Cartoon", "10", "0", "11"), row(21, "Soon", "coming_soon")]},
            URL2: {"categories": [
                {"id": "5", "title": "kids movies", "alias": "kids", "censored": 0},
            ], "items": [row(1, "Other cartoon", "5", "5", "5"), row(2, "Show", "5", series=1)]},
            OFF_URL: {"categories": [{"id": "1", "title": "Hidden", "alias": "h"}],
                      "items": [row(1, "Never", "1")]},
        })

    def test_before_the_first_crawl_every_enabled_portal_reads_failed(self):
        body = self.get("/api/ondemand/categories", "viewer").get_json()
        self.assertEqual(body["categories"], [])
        self.assertEqual(body["portals"], [
            {"portal": "p1", "name": "First", "status": "failed", "progress": None, "lastRefresh": None},
            {"portal": "p2", "name": "Second", "status": "failed", "progress": None, "lastRefresh": None},
        ])

    def test_after_the_crawl_categories_merge_across_portals_with_exact_counts(self):
        self.app.startOnDemand()
        body = self.get("/api/ondemand/categories", "viewer").get_json()
        self.assertEqual(body["categories"], [
            {"id": "action", "name": "Action", "count": 21},
            {"id": "kids movies", "name": "Kids  Movies", "count": 3},
        ])
        self.assertEqual([(p["portal"], p["status"], p["progress"]) for p in body["portals"]],
                         [("p1", "ready", None), ("p2", "ready", None)])
        self.assertTrue(all(isinstance(p["lastRefresh"], int) for p in body["portals"]))

    def test_the_crawl_pages_all_items_newest_first_and_skips_switched_off_portals(self):
        self.app.startOnDemand()
        self.assertEqual(self.fake.pages, [(URL1, 1), (URL1, 2), (URL2, 1)])


class CrawlGatingTest(OnDemandTestCase):
    def setUp(self):
        super().setUp()
        self.app.accounts.findAccount(self.app.getAccounts(), "viewer")["on demand"] = False
        self.fake = FakePortals(self, self.app, {"http://portal.test/stalker_portal/server/load.php": {
            "categories": [{"id": "10", "title": "Action", "alias": "action"}],
            "items": [row(1, "A", "10")],
        }})

    def switch(self, username, switch, value):
        self.client.post("/accounts/ondemand", headers=basic("admin", "12345"),
                         data={"username": username, "switch": switch, "value": value})

    def test_no_crawl_at_boot_while_every_account_is_off(self):
        self.app.startOnDemand()
        self.assertEqual(self.fake.pages, [])

    def test_a_crawl_at_boot_when_an_account_already_has_on_demand_on(self):
        self.app.accounts.findAccount(self.app.getAccounts(), "viewer")["on demand"] = True
        self.app.startOnDemand()
        self.assertEqual(len(self.fake.pages), 1)

    def test_a_disabled_account_with_on_demand_on_does_not_start_a_crawl(self):
        self.app.startOnDemand()  # "disabled" has On Demand on but is disabled
        self.assertEqual(self.fake.pages, [])

    def test_switching_the_first_account_on_starts_the_crawl(self):
        self.switch("off", "adult on demand", "true")
        self.switch("off", "on demand", "false")
        self.assertEqual(self.fake.pages, [])
        self.switch("off", "on demand", "true")
        self.assertEqual(len(self.fake.pages), 1)
        body = self.get("/api/ondemand/categories", "off").get_json()
        self.assertEqual(body["categories"], [{"id": "action", "name": "Action", "count": 1}])

    def test_enabling_an_account_that_has_on_demand_on_starts_the_crawl(self):
        self.client.post("/accounts/toggle", headers=basic("admin", "12345"),
                         data={"username": "disabled", "enabled": "true"})
        self.assertEqual(len(self.fake.pages), 1)


if __name__ == "__main__":
    unittest.main()
