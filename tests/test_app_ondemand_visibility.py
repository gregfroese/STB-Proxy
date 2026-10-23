"""Hidden On Demand categories and Adult On Demand (ADR 0004): strict filters on every
viewer query, and the Operator UI's On Demand page."""
import datetime
import json
import os
import re
import unittest

from tests.support import loadApp
from tests.test_app_ondemand import onDemandConfig
from tests.test_api_lineup import basic
from tests.test_app_ondemand_browse import BrowseTestCase, movie

CATEGORIES = (
    {"id": "10", "title": "Action"},
    {"id": "20", "title": "Kids"},
    {"id": "30", "title": "  late   NIGHT "},
    {"id": "40", "title": "Adults only", "censored": "1"},
)


class VisibilityTestCase(BrowseTestCase):
    def setUp(self):
        super().setUp()
        self.addAccount("grown", onDemand=True)
        self.app.getAccounts()[-1]["adult on demand"] = True

    def hide(self, *names):
        self.app.config["hidden on demand categories"] = list(names)

    def total(self, query="", username="viewer"):
        response = self.get("/api/ondemand/items" + query, username)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["total"]

    def listed(self, query="", username="viewer"):
        response = self.get("/api/ondemand/items" + query, username)
        self.assertEqual(response.status_code, 200, response.get_json())
        return sorted(i["name"] for i in response.get_json()["items"])

    def counts(self, username="viewer"):
        response = self.get("/api/ondemand/categories", username)
        self.assertEqual(response.status_code, 200, response.get_json())
        return {c["id"]: c["count"] for c in response.get_json()["categories"]}


class HiddenCategoryTest(VisibilityTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [
            movie(1, "Plain action", "2026-10-05 00:00:00", cat0="10"),
            movie(2, "Action for kids", "2026-10-04 00:00:00", cat0="10", cat1="20"),
            movie(3, "Late action", "2026-10-03 00:00:00", cat0="10", cat1="0", cat2="30"),
            movie(4, "Just kids", "2026-10-02 00:00:00", cat0="20"),
        ], categories=CATEGORIES)

    def test_an_item_in_a_hidden_category_in_any_slot_leaves_every_listing(self):
        self.hide("kids", "late night")
        self.assertEqual(self.listed(), ["Plain action"])
        self.assertEqual(self.total(), 1)
        self.assertEqual(self.listed("?category=action"), ["Plain action"])
        self.assertEqual(self.total("?category=action"), 1)
        self.assertEqual(self.total("?category=kids"), 0)

    def test_counts_are_exact_after_hiding_and_hidden_categories_are_not_listed(self):
        self.assertEqual(self.counts(), {"action": 3, "kids": 2, "late night": 1})
        self.hide("Kids")
        self.assertEqual(self.counts(), {"action": 2, "late night": 1})

    def test_search_leaves_out_items_in_a_hidden_category(self):
        self.hide("late night")
        self.assertEqual(self.listed("?q=action"), ["Action for kids", "Plain action"])
        self.assertEqual(self.total("?q=action"), 2)
        self.assertEqual(self.listed("?q=late"), [])

    def test_the_detail_and_poster_of_an_item_in_a_hidden_category_are_not_found(self):
        self.assertEqual(self.get("/api/ondemand/item/p1/3", "viewer").status_code, 200)
        self.hide("late night")
        for path in ("/api/ondemand/item/p1/3", "/api/ondemand/poster/p1/3"):
            response = self.get(path, "viewer")
            self.assertEqual((response.status_code, response.get_json()["code"]), (404, "not_found"), path)
        self.assertEqual(self.get("/api/ondemand/item/p1/1", "viewer").status_code, 200)


class AdultTest(VisibilityTestCase):
    def setUp(self):
        super().setUp()
        self.fill("p1", [
            movie(1, "Family film", "2026-10-05 00:00:00", cat0="10"),
            movie(2, "Grown film", "2026-10-04 00:00:00", cat0="10", cat2="40"),
            movie(3, "Censored film", "2026-10-03 00:00:00", cat0="10", censored="1"),
            movie(4, "Locked film", "2026-10-02 00:00:00", cat0="10", lock="1"),
            movie(5, "Kids film", "2026-10-01 00:00:00", cat0="20"),
        ], categories=CATEGORIES)

    def test_adult_categories_and_flagged_items_are_removed_while_adult_on_demand_is_off(self):
        self.assertEqual(self.listed(), ["Family film", "Kids film"])
        self.assertEqual(self.total("?q=film"), 2)
        self.assertEqual(self.counts(), {"action": 1, "kids": 1})
        for id in ("2", "3", "4"):
            self.assertEqual(self.get("/api/ondemand/item/p1/" + id, "viewer").status_code, 404, id)

    def test_an_account_with_adult_on_demand_on_sees_them(self):
        self.assertEqual(self.listed(username="grown"),
                         ["Censored film", "Family film", "Grown film", "Kids film", "Locked film"])
        self.assertEqual(self.counts("grown"), {"action": 4, "adults only": 1, "kids": 1})
        self.assertEqual(self.get("/api/ondemand/item/p1/3", "grown").status_code, 200)

    def test_the_hidden_list_applies_with_adult_on_demand_on(self):
        self.hide("adults only", "kids")
        self.assertEqual(self.listed(username="grown"), ["Censored film", "Family film", "Locked film"])
        self.assertEqual(self.counts("grown"), {"action": 3})


class OperatorPageTest(VisibilityTestCase):
    """The Operator UI's On Demand page: index status, the merged category table with
    Hide toggles, and stale hidden names. Not an On Demand browser."""

    def operator(self):
        settings = self.app.getSettings()
        return basic(settings["username"], settings["password"])

    def page(self):
        response = self.client.get("/ondemand", headers=self.operator())
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def row(self, body, name):
        """The category table row whose name cell is `name`."""
        match = re.search(r'<tr data-category="{}">(.*?)</tr>'.format(re.escape(name)), body, re.S)
        self.assertIsNotNone(match, name)
        return match.group(1)

    def test_the_nav_links_to_it(self):
        self.assertIn('href="/ondemand"', self.page())

    def test_accounts_cannot_open_it(self):
        self.assertEqual(self.get("/ondemand", "viewer").status_code, 401)

    def test_each_enabled_portal_shows_its_index_status_and_item_count(self):
        self.fill("p1", [movie(i, "Film", "2026-10-01 00:00:00") for i in range(3)])
        lastGood = datetime.datetime(2026, 10, 20, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
        self.index.addItems("p2", [movie(9, "Other", "2026-10-01 00:00:00")])
        self.index.setStatus("p2", "stale", lastRefresh=int(lastGood))
        body = self.page()
        first = re.search(r'<tr data-portal="p1">(.*?)</tr>', body, re.S).group(1)
        second = re.search(r'<tr data-portal="p2">(.*?)</tr>', body, re.S).group(1)
        self.assertIn("First", first)
        self.assertIn("Ready", first)
        self.assertIn("3 items", first)
        self.assertIn("Stale", second)
        self.assertIn('datetime="2026-10-20T12:00:00Z"', second)
        self.assertIn("1 item<", second)
        self.assertNotIn('data-portal="p3"', body)

    def test_indexing_partial_and_failed_statuses(self):
        self.index.setStatus("p1", "indexing", pagesDone=2, pagesTotal=5)
        self.index.setStatus("p2", "partial", lastRefresh=1)
        body = self.page()
        self.assertIn("Indexing 40%", re.search(r'<tr data-portal="p1">(.*?)</tr>', body, re.S).group(1))
        self.assertIn("Partial", re.search(r'<tr data-portal="p2">(.*?)</tr>', body, re.S).group(1))
        self.index.purge("p2")
        self.assertIn("Failed", re.search(r'<tr data-portal="p2">(.*?)</tr>', self.page(), re.S).group(1))

    def test_the_category_table_merges_portals_with_counts_adult_badges_and_hide_toggles(self):
        self.fill("p1", [
            movie(1, "A", "2026-10-01 00:00:00", cat0="10", cat1="40"),
            movie(2, "B", "2026-10-01 00:00:00", cat0="20"),
        ], categories=CATEGORIES)
        self.fill("p2", [movie(1, "C", "2026-10-01 00:00:00", cat0="7")],
                 categories=[{"id": "7", "title": "ACTION"}])
        self.hide("kids")
        body = self.page()
        action = self.row(body, "action")
        self.assertIn("Action", action)
        self.assertIn("First", action)
        self.assertIn("Second", action)
        self.assertIn("<td>2</td>", action)
        self.assertNotIn(">Adult</span>", action)
        self.assertIn('name="hidden" value="true"', action)
        adult = self.row(body, "adults only")
        self.assertIn(">Adult</span>", adult)
        self.assertIn("<td>1</td>", adult)
        kids = self.row(body, "kids")
        self.assertIn('name="hidden" value="false"', kids)
        self.assertIn("<td>1</td>", kids)  # the operator sees the unfiltered count
        self.assertNotIn("not on any portal", body)

    def test_a_hidden_name_on_no_portal_is_flagged(self):
        self.fill("p1", [movie(1, "A", "2026-10-01 00:00:00")])
        self.hide("old name")
        stale = self.row(self.page(), "old name")
        self.assertIn("not on any portal", stale)
        self.assertIn('name="hidden" value="false"', stale)

    def test_the_hide_toggle_hides_and_shows_a_category_by_its_merged_name(self):
        self.fill("p1", [movie(1, "A", "2026-10-01 00:00:00", cat0="30")], categories=CATEGORIES)
        response = self.client.post("/ondemand/hide", headers=self.operator(),
                                    data={"name": "late night", "hidden": "true"})
        self.assertEqual((response.status_code, response.location), (302, "/ondemand"))
        self.assertEqual(self.app.config["hidden on demand categories"], ["late night"])
        with open(self.app.configFile) as f:
            self.assertEqual(json.load(f)["hidden on demand categories"], ["late night"])
        self.assertEqual(self.total(), 0)
        self.client.post("/ondemand/hide", headers=self.operator(),
                         data={"name": "late night", "hidden": "false"})
        self.assertEqual(self.app.config["hidden on demand categories"], [])
        self.assertEqual(self.total(), 1)

    def test_hiding_needs_a_category_some_portal_has(self):
        self.fill("p1", [movie(1, "A", "2026-10-01 00:00:00")])
        self.client.post("/ondemand/hide", headers=self.operator(), data={"name": "nope", "hidden": "true"})
        self.assertEqual(self.app.config["hidden on demand categories"], [])

    def test_the_page_does_not_create_an_index_before_anything_is_indexed(self):
        self.index.close()
        self.app.onDemand["index"] = None
        os.remove(self.app.onDemandIndexFile())
        body = self.page()
        self.assertIn("Nothing indexed yet", body)
        self.assertFalse(os.path.exists(self.app.onDemandIndexFile()))


class HiddenConfigTest(unittest.TestCase):
    def test_hidden_names_load_normalised_and_deduplicated(self):
        app = loadApp(self, onDemandConfig(**{
            "hidden on demand categories": ["  Late  NIGHT ", 3, None, "kids", "KIDS", "  "]}))
        self.assertEqual(app.config["hidden on demand categories"], ["late night", "kids"])

    def test_a_missing_or_malformed_list_loads_empty(self):
        for value in (None, "kids", {"kids": True}):
            config = onDemandConfig()
            if value is not None:
                config["hidden on demand categories"] = value
            app = loadApp(self, config)
            self.assertEqual(app.config["hidden on demand categories"], [], value)


if __name__ == "__main__":
    unittest.main()
