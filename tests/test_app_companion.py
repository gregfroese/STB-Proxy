"""The Companion app's updates: the newest STB-Proxy-Companion-<version>.apk in the companion
folder beside config.json, offered at /api/companion and /companion.apk without a login."""
import os
import unittest

from tests.support import PORTAL, loadApp, portalConfig


class CompanionTest(unittest.TestCase):
    def setUp(self):
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.client = self.app.app.test_client()
        self.folder = os.path.join(os.path.dirname(self.app.configFile), "companion")

    def put(self, name, body=b"apk"):
        os.makedirs(self.folder, exist_ok=True)
        with open(os.path.join(self.folder, name), "wb") as f:
            f.write(body)

    def test_nothing_to_offer_is_not_found(self):
        self.assertEqual(self.client.get("/api/companion").status_code, 404)
        self.put("notes.txt")
        response = self.client.get("/api/companion")
        self.assertEqual((response.status_code, response.get_json()["code"]), (404, "not_found"))
        self.assertEqual(self.client.get("/companion.apk").status_code, 404)

    def test_the_newest_version_is_offered_by_number_not_by_name(self):
        self.put("STB-Proxy-Companion-1.9.0.apk", b"old")
        self.put("STB-Proxy-Companion-1.13.0.apk", b"newest")
        self.put("STB-Proxy-Companion-1.12.4.apk", b"older")
        self.assertEqual(self.client.get("/api/companion").get_json(),
                         {"versionName": "1.13.0", "url": "/companion.apk", "sizeBytes": 6})
        apk = self.client.get("/companion.apk")
        self.assertEqual(apk.status_code, 200)
        self.assertEqual(apk.data, b"newest")
        self.assertEqual(apk.mimetype, "application/vnd.android.package-archive")
        self.assertIn('filename=STB-Proxy-Companion.apk', apk.headers["Content-Disposition"])
        apk.close()


if __name__ == "__main__":
    unittest.main()
