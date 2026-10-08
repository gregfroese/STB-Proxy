import os
import tempfile
import time
import unittest

import recordings
from tests.support import PORTAL, loadApp, portalConfig
from tests.test_recordings import LOG, FakeResponse, joinParts


class RecordingRoutesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = os.path.join(self.dir.name, "rec")
        self.app = loadApp(self, {"portals": {PORTAL: portalConfig()}, "settings": {"recordings folder": self.folder}})
        self.client = self.app.app.test_client()
        self.responses = [FakeResponse()]
        store = recordings.RecordingStore(os.path.join(self.dir.name, "recordings.json"), LOG)
        self.app.recorder = recordings.Recorder(
            store, lambda: self.app.getSettings()["recordings folder"], self.app.recordingUrl, LOG,
            openStream=lambda url: self.responses[0], remux=joinParts, freeSpace=lambda path: 10 * 1024 ** 3)
        self.addCleanup(lambda: [self.app.recorder.stop(r["id"]) for r in store.all()])

    def start(self, **body):
        return self.client.post("/recordings/start", json=dict({"portal": PORTAL, "channelId": "2", "name": "Two"}, **body))

    def finished(self, id):
        for _ in range(300):
            if not self.app.recorder.isRunning(id):
                return
            time.sleep(0.01)

    def test_recordings_read_from_play_like_a_player(self):
        self.assertEqual(self.app.recordingUrl("p1", "2", "abc"), "http://127.0.0.1:8001/play/p1/2?recording=abc")
        self.assertEqual(self.app.TUNER_BUSY, recordings.TUNER_BUSY)

    def test_start_list_stop_play_and_delete(self):
        rec = self.start(minutes=30).get_json()
        self.assertEqual((rec["title"], rec["status"]), ("Two", "recording"))
        self.assertAlmostEqual(rec["stop"], time.time() + 1800, delta=5)
        listed = self.client.get("/recordings/list").get_json()
        self.assertEqual([r["id"] for r in listed["recordings"]], [rec["id"]])
        self.assertEqual((listed["folder"], listed["free"] > 0), (self.folder, True))
        self.assertEqual(self.client.post("/recordings/{}/delete".format(rec["id"])).status_code, 409)  # still recording
        time.sleep(0.05)  # record something
        self.assertEqual(self.client.post("/recordings/{}/stop".format(rec["id"])).get_json(), {"stopping": True})
        self.finished(rec["id"])
        played = self.client.get("/recordings/{}/file".format(rec["id"]), headers={"Range": "bytes=0-9"})
        self.assertEqual((played.status_code, played.mimetype, len(played.data)), (206, "video/mp4", 10))
        played.close()
        download = self.client.get("/recordings/{}/file?download=1".format(rec["id"]))
        self.assertIn("attachment", download.headers["Content-Disposition"])
        download.close()
        self.assertEqual(self.client.post("/recordings/{}/delete".format(rec["id"])).get_json(), {"deleted": True})
        self.assertEqual(self.client.get("/recordings/list").get_json()["recordings"], [])

    def test_until_a_programme_ends(self):
        rec = self.start(until=time.time() + 600).get_json()
        self.assertAlmostEqual(rec["stop"], time.time() + 600, delta=5)
        self.assertEqual(self.start(until=time.time() - 5).status_code, 400)  # already over
        self.assertEqual(self.start(minutes=-1).status_code, 400)
        self.assertEqual(self.start(minutes="soon").status_code, 400)

    def test_refusals_say_why(self):
        self.responses = [FakeResponse(503, body={"error": recordings.TUNER_BUSY})]
        response = self.start()
        self.assertEqual(response.status_code, 503)
        self.assertIn("No free tuner", response.get_json()["error"])
        self.assertEqual(self.client.post("/recordings/start", json={"portal": "nope", "channelId": "2"}).status_code, 404)
        self.app.getSettings()["recordings folder"] = ""
        self.assertIn("Recording is off", self.start().get_json()["error"])

    def test_file_route_only_serves_known_recordings(self):
        for path in ("/recordings/nope/file", "/recordings/..%2F..%2Fconfig.json/file", "/recordings/nope/stop",
                     "/recordings/nope/delete"):
            method = self.client.get if path.endswith("file") else self.client.post
            self.assertEqual(method(path).status_code, 404, path)

    def test_the_folder_setting_is_saved_trimmed(self):
        form = {k: v for k, v in self.app.getSettings().items() if k != "api token"}
        form["recordings folder"] = "  /mnt/recordings  "
        self.client.post("/settings/save", data=form)
        self.assertEqual(self.app.getSettings()["recordings folder"], "/mnt/recordings")
        self.assertIn('name="recordings folder"', self.client.get("/settings").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
