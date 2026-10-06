import json
import os
import tempfile
import unittest
from unittest import mock

import stb
from tests.support import PORTAL, loadApp, portalConfig

MAC = "00:1A:79:00:00:01"

# Shaped like a real capture: fields the form shows, plus extras only Advanced holds.
CAPTURED = {
    "_note": "Captured from the living room box",
    "cookies": {"adid": "abc", "timezone": "America/Edmonton"},
    "headers": {"User-Agent": "MAG ua", "X-User-Agent": "Model: MAG250; Link: WiFi", "Referer": "http://x/c/"},
    "handshake": {"prehash": "ph", "token": ""},
    "profile": {"sn": "SN1", "stb_type": "MAG250", "device_id": "D1", "device_id2": "D2", "signature": "SIG",
                "hw_version": "1.7-BD-00", "timestamp": "0"},
}


def tempDevices(testCase):
    tmp = tempfile.TemporaryDirectory()
    testCase.addCleanup(tmp.cleanup)
    path = os.path.join(tmp.name, "devices.json")
    patcher = mock.patch.object(stb, "devicesFile", path)
    patcher.start()
    testCase.addCleanup(patcher.stop)
    return path


class CandidatesTest(unittest.TestCase):
    def test_box_address_with_c_folder(self):
        self.assertEqual(
            stb.portalUrlCandidates("http://h:8080/c/"),
            ["http://h:8080/server/load.php", "http://h:8080/portal.php",
             "http://h:8080/stalker_portal/server/load.php", "http://h:8080/stalker_portal/portal.php"],
        )

    def test_stalker_folder_comes_first_when_typed(self):
        self.assertEqual(stb.portalUrlCandidates("h/stalker_portal/c/index.html")[0], "http://h/stalker_portal/server/load.php")

    def test_typed_api_address_is_tried_first_without_duplicates(self):
        candidates = stb.portalUrlCandidates("http://h/stalker_portal/server/load.php")
        self.assertEqual(candidates[0], "http://h/stalker_portal/server/load.php")
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertNotIn("http://h/stalker_portal/server/server/load.php", candidates)


class FindPortalTest(unittest.TestCase):
    def setUp(self):
        stb.sessions.clear()
        self.addCleanup(stb.sessions.clear)

    def find(self, url, works, advertised=None):
        with mock.patch.object(stb, "getToken", side_effect=lambda u, m, p=None: "t" if u == works else None), \
                mock.patch.object(stb, "getUrl", return_value=advertised) as getUrl:
            return stb.findPortal(url, [MAC]), getUrl

    def test_typed_api_address_that_works_skips_the_search(self):
        (found, tried), getUrl = self.find("http://h/portal.php", "http://h/portal.php")
        self.assertEqual((found, tried), ("http://h/portal.php", ["http://h/portal.php"]))
        getUrl.assert_not_called()

    def test_address_the_portal_advertises_is_next(self):
        (found, tried), _ = self.find("http://h/c/", "http://h/odd/load.php", advertised="http://h/odd/load.php")
        self.assertEqual(found, "http://h/odd/load.php")
        self.assertEqual(tried, ["http://h/odd/load.php"])

    def test_extra_path_typed_is_found_without_it(self):
        # Typed a folder the portal doesn't use; the API is at the server's root.
        (found, tried), _ = self.find("http://h:8080/stalker_portal/c/", "http://h:8080/portal.php")
        self.assertEqual(found, "http://h:8080/portal.php")
        self.assertEqual(tried[:2], ["http://h:8080/stalker_portal/server/load.php", "http://h:8080/stalker_portal/portal.php"])

    def test_nothing_found_reports_every_address_tried(self):
        (found, tried), _ = self.find("http://h/c/", None)
        self.assertIsNone(found)
        self.assertEqual(len(tried), 4)


class DeviceFileTest(unittest.TestCase):
    def setUp(self):
        self.path = tempDevices(self)

    def test_save_and_remove(self):
        stb.sessions[("http://h/portal.php", MAC)] = {"token": "old", "time": 9e99}
        stb.saveDevice(MAC, {"profile": {"sn": "SN1"}})
        self.assertEqual(stb.device(MAC), {"profile": {"sn": "SN1"}})
        self.assertNotIn(("http://h/portal.php", MAC), stb.sessions)  # logs in again with the new details
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        stb.removeDevice(MAC)
        self.assertEqual(stb.device(MAC), {})

    def test_other_macs_are_kept(self):
        stb.saveDevice("A", {"profile": {"sn": "1"}})
        stb.saveDevice("B", {"profile": {"sn": "2"}})
        stb.removeDevice("A")
        self.assertEqual(stb.loadDevices(), {"B": {"profile": {"sn": "2"}}})


class PortalFormTest(unittest.TestCase):
    def setUp(self):
        self.path = tempDevices(self)
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig(**{"macs": {MAC: "2027"}})}})
        self.client = self.app.app.test_client()
        stb.sessions.clear()
        self.addCleanup(stb.sessions.clear)

    def form(self, **fields):
        form = {"name": "New", "url": "http://h/c/", "macs": MAC, "streams per mac": "1", "proxy": ""}
        form.update(fields)
        return form

    def messages(self):
        return self.client.get("/portals").get_data(as_text=True)

    def test_form_round_trip_keeps_everything(self):
        split = self.app.deviceForForm(CAPTURED)
        self.assertEqual(split["fields"], {"model": "MAG250", "serial": "SN1", "device id": "D1",
                                           "device id2": "D2", "signature": "SIG", "timezone": "America/Edmonton"})
        form = {"device " + k: v for k, v in split["fields"].items()}
        form["device extra"] = json.dumps(split["extra"])
        details, error = self.app.deviceFromForm(form)
        self.assertIsNone(error)
        self.assertEqual(details, CAPTURED)

    def test_model_fills_in_the_box_header(self):
        details, _ = self.app.deviceFromForm({"device model": "MAG254", "device serial": "S"})
        self.assertEqual(details["headers"]["X-User-Agent"], "Model: MAG254; Link: Ethernet")
        self.assertEqual(self.app.deviceForForm(details)["extra"], {})  # not shown twice

    def test_add_saves_device_before_testing_and_reports_found_address(self):
        seen = []

        def getToken(url, mac, proxy=None):
            seen.append(stb.device(mac).get("profile", {}).get("sn"))
            return "t" if url == "http://h/portal.php" else None

        with mock.patch.object(self.app.stb, "getToken", side_effect=getToken), \
                mock.patch.object(self.app.stb, "getUrl", return_value=None), \
                mock.patch.object(self.app.stb, "getExpires", return_value="2027-01-01"):
            self.client.post("/portal/add", data=self.form(**{"device state": "on", "device serial": "SN9"}))
        self.assertTrue(seen and all(sn == "SN9" for sn in seen))
        added = [p for p in self.app.getPortals().values() if p["name"] == "New"]
        self.assertEqual(added[0]["url"], "http://h/portal.php")
        self.assertIn("Found Portal(New) at http://h/portal.php", self.messages())

    def test_refused_mac_suggests_device_lock(self):
        with mock.patch.object(self.app.stb, "getUrl", return_value=None), \
                mock.patch.object(self.app.stb, "getExpires", return_value=None):
            self.client.post("/portal/add", data=self.form())
        body = self.messages()
        self.assertIn("refused MAC({})".format(MAC), body)
        self.assertIn("turn on Device lock", body)
        self.assertFalse([p for p in self.app.getPortals().values() if p["name"] == "New"])

    def test_unreachable_portal_lists_addresses_tried(self):
        with mock.patch.object(self.app.stb, "getToken", return_value=None), \
                mock.patch.object(self.app.stb, "getUrl", return_value=None):
            self.client.post("/portal/add", data=self.form())
        self.assertIn("http://h/stalker_portal/portal.php", self.messages())

    def test_bad_advanced_json_saves_nothing(self):
        self.client.post("/portal/add", data=self.form(**{"device state": "on", "device extra": "{nope"}))
        self.assertIn("isn&#39;t valid JSON", self.messages())
        self.assertEqual(stb.loadDevices(), {})

    def test_edit_keep_leaves_devices_alone_and_off_removes_them(self):
        stb.saveDevice(MAC, CAPTURED)
        url = self.app.getPortals()[PORTAL]["url"]
        edit = {"id": PORTAL, "name": "Test portal", "url": url, "macs": MAC, "streams per mac": "1", "proxy": ""}
        self.client.post("/portal/update", data=dict(edit, **{"device state": "keep"}))
        self.assertEqual(stb.device(MAC), CAPTURED)
        self.client.post("/portal/update", data=dict(edit, **{"device state": "off"}))
        self.assertEqual(stb.device(MAC), {})

    def test_portals_page_offers_device_lock(self):
        stb.saveDevice(MAC, CAPTURED)
        body = self.client.get("/portals").get_data(as_text=True)
        self.assertEqual(body.count('name="device state"'), 2)  # add and edit forms
        data = body.split('<script id="devicesData" type="application/json">')[1].split("</script>")[0]
        self.assertEqual(json.loads(data)[MAC]["fields"]["serial"], "SN1")


if __name__ == "__main__":
    unittest.main()
