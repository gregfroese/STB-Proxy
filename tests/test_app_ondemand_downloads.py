"""On Demand downloads through the app: the viewer API, the Account switch, the slot a
running download holds and gives up, and the operator's controls. The fake portal and
storage host are test_app_ondemand_play's; ffmpeg is stood in for by a plain copy."""
import os
import shutil
import tempfile
import threading
from unittest import mock

import downloads
import ondemand
from tests.support import PORTAL
from tests.test_api_lineup import basic
from tests.test_app_ondemand_play import SEGMENT, PlayTestCase


def copyRemux(parts, out):
    with open(out, "wb") as f:
        for part in parts:
            with open(part, "rb") as p:
                shutil.copyfileobj(p, f)


class DownloadTestCase(PlayTestCase):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.app.getSettings()["downloads movies folder"] = os.path.join(self.dir.name, "movies")
        self.app.getSettings()["downloads tv folder"] = os.path.join(self.dir.name, "tv")
        os.makedirs(os.path.join(self.dir.name, "movies"))
        os.makedirs(os.path.join(self.dir.name, "tv"))
        self.app.getAccounts()[0]["downloads"] = True  # "viewer"; "other" has it off
        self.downloader = self.app.getDownloader()
        self.downloader.remux = copyRemux
        self.downloader.started = -10 ** 9  # STB-Proxy has been up for ages: the portal is quiet
        self.downloader.start = lambda: None  # no background thread: the tests run the queue

    def download(self, body, username="viewer", status=202):
        response = self.client.post("/api/ondemand/downloads", json=body, headers=basic(username, "secret"))
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response.get_json()

    def listed(self, username="viewer"):
        return self.fetch("/api/ondemand/downloads", username).get_json()

    def runQueue(self):
        self.downloader.tick()
        job = self.downloader.running.get(PORTAL)
        if job is not None:
            job["thread"].join(10)
        return job


class ApiTest(DownloadTestCase):
    def test_a_movie_downloads_into_the_movies_folder(self):
        [queued] = self.download({"portal": PORTAL, "id": "5"})["items"]
        self.assertEqual((queued["status"], queued["kind"], queued["title"], queued["mine"]),
                         ("queued", "movie", "Heat", True))
        self.assertEqual(queued["item"], {"portal": PORTAL, "id": "5"})
        detail = self.fetch("/api/ondemand/item/{}/5".format(PORTAL)).get_json()
        self.assertTrue(detail["canDownload"])
        self.assertEqual((detail["download"]["status"], detail["download"]["mine"]), ("queued", True))
        other = self.fetch("/api/ondemand/item/{}/5".format(PORTAL), "other").get_json()
        self.assertFalse(other["download"]["mine"])

        self.runQueue()
        [done] = self.listed()["items"]
        self.assertEqual((done["status"], done["progress"]), ("done", 100))
        path = os.path.join(self.dir.name, "movies", "Heat (2020)", "Heat (2020).mp4")
        with open(path, "rb") as f:
            self.assertEqual(f.read(), SEGMENT * 3)
        self.assertEqual(done["sizeBytes"], len(SEGMENT) * 3)
        self.assertEqual(self.streaming(), [])  # its slot is back
        self.assertEqual(self.portal.mints, [("/media/5.mpg", "0")])

    def test_plex_scans_the_new_folder_when_it_is_set_up(self):
        self.app.getSettings().update({"plex url": "http://plex.test:32400", "plex token": "tok"})
        with mock.patch.object(self.app.plex, "scanFolder", return_value="x") as scan:
            self.download({"portal": PORTAL, "id": "5"})
            self.runQueue()
        movies = os.path.join(self.dir.name, "movies")
        scan.assert_called_once_with("http://plex.test:32400", "tok", "movie", movies,
                                     os.path.join(movies, "Heat (2020)"))

    def test_the_switch_and_the_folder_gate_it(self):
        self.assertEqual(self.download({"portal": PORTAL, "id": "5"}, "other", 403)["code"], "downloads_off")
        self.assertFalse(self.fetch("/api/ondemand/item/{}/5".format(PORTAL), "other").get_json()["canDownload"])
        self.app.getSettings()["downloads movies folder"] = ""
        self.assertEqual(self.download({"portal": PORTAL, "id": "5"}, status=503)["code"], "downloads_unavailable")
        self.assertFalse(self.fetch("/api/ondemand/item/{}/5".format(PORTAL)).get_json()["canDownload"])
        self.assertTrue(self.listed()["canDownload"])  # Episodes still can
        self.download({"portal": PORTAL, "seriesId": "77", "seasonId": "31685"})
        self.app.getSettings()["downloads tv folder"] = ""
        self.assertFalse(self.listed()["canDownload"])

    def test_only_what_the_viewer_may_see(self):
        self.download({"portal": PORTAL, "id": "8"})
        self.assertEqual(len(self.listed()["items"]), 1)
        self.app.config["hidden on demand categories"] = [ondemand.normalisedName("Hidden")]
        self.assertEqual(self.listed()["items"], [])
        self.assertEqual(self.download({"portal": PORTAL, "id": "8"}, status=404)["code"], "not_found")

    def test_a_season_queues_every_episode_named_for_plex(self):
        [episode] = self.download({"portal": PORTAL, "seriesId": "77", "seasonId": "31685"})["items"]
        self.assertEqual((episode["kind"], episode["title"]), ("episode", "Show - S2 E3"))
        self.assertEqual(episode["item"], {"portal": PORTAL, "seriesId": "77", "seasonId": "31685", "episodeId": "901"})
        episodes = self.fetch("/api/ondemand/series/{}/77/season/31685".format(PORTAL)).get_json()
        self.assertEqual(episodes[0]["download"]["status"], "queued")
        again = self.download({"portal": PORTAL, "seriesId": "77", "seasonId": "31685", "episodeId": "901"})
        self.assertEqual(again["items"][0]["id"], episode["id"])  # the same download
        self.runQueue()
        rec = self.downloader.get(episode["id"])
        self.assertEqual(rec["status"], "done", rec["error"])
        self.assertTrue(rec["file"].startswith(os.path.join(self.dir.name, "tv", "Show")))
        self.assertIn(os.path.join("Season 02", "Show"), rec["file"])
        self.assertTrue(rec["file"].endswith(" - S02E03.mp4"))

    def test_other_accounts_see_it_but_only_its_owner_cancels(self):
        [queued] = self.download({"portal": PORTAL, "id": "5"})["items"]
        [seen] = self.listed("other")["items"]
        self.assertFalse(seen["mine"])
        url = "/api/ondemand/downloads/" + queued["id"]
        self.assertEqual(self.client.delete(url, headers=basic("other", "secret")).status_code, 404)
        self.assertEqual(self.client.delete(url, headers=basic("viewer", "secret")).status_code, 204)
        self.assertEqual(self.listed()["items"], [])

    def test_a_finished_download_is_the_operators_to_delete(self):
        [queued] = self.download({"portal": PORTAL, "id": "5"})["items"]
        self.runQueue()
        url = "/api/ondemand/downloads/" + queued["id"]
        self.assertEqual(self.client.delete(url, headers=basic("viewer", "secret")).status_code, 409)
        file = self.downloader.get(queued["id"])["file"]
        response = self.client.post("/ondemand/downloads/delete", data={"id": queued["id"]},
                                    headers=basic("admin", "12345"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(os.path.exists(file))
        self.assertEqual(self.listed()["items"], [])

    def test_the_operator_page_lists_downloads(self):
        self.download({"portal": PORTAL, "id": "5"})
        page = self.client.get("/ondemand", headers=basic("admin", "12345")).get_data(as_text=True)
        self.assertIn("<td>Heat</td>", page)
        self.assertIn("Queued", page)


class GivingWayTest(DownloadTestCase):
    def holdDownload(self):
        """Start the download and stop it on its second segment, holding the slot."""
        self.download({"portal": PORTAL, "id": "5"})
        reached, release = threading.Event(), threading.Event()
        realSegment = downloads.ondemandsession.Session.segment

        def slowSegment(session, name, range=None):
            if session.sid.startswith("download-") and len([f for f in self.portal.fetches if f.endswith(".ts")]) == 1:
                reached.set()
                release.wait(5)
            return realSegment(session, name, range)

        patcher = mock.patch.object(downloads.ondemandsession.Session, "segment", slowSegment)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.downloader.tick()
        self.assertTrue(reached.wait(5))
        return release

    def test_a_running_download_shows_in_streaming_and_a_viewer_pauses_it(self):
        release = self.holdDownload()
        [entry] = self.streaming()
        self.assertEqual((entry["kind"], entry["channel name"], entry["account"]), ("download", "Heat", "viewer"))

        self.assertEqual(self.live("2").status_code, 200)  # one MAC, one stream: the viewer wins
        release.set()
        job = self.downloader.running.get(PORTAL)
        if job is not None:
            job["thread"].join(5)
        rec = self.downloader.list()[0]
        self.assertEqual((rec["status"], rec["segmentsDone"]), ("queued", 1))
        self.assertEqual([e.get("kind") for e in self.streaming()], [None])  # just the live channel
        self.assertIsNone(self.runQueue())  # not while someone watches

    def test_the_operator_can_pause_it_from_the_streams_page(self):
        release = self.holdDownload()
        [entry] = self.streaming()
        response = self.client.post("/streams/stop", data={"portal": PORTAL, "download": entry["download"]},
                                    headers=basic("admin", "12345"))
        self.assertEqual(response.get_json(), {"ok": True})
        release.set()
        self.assertEqual(self.streaming(), [])

    def test_an_on_demand_viewer_pauses_it_too(self):
        release = self.holdDownload()
        self.play({"portal": PORTAL, "id": "5"}, "other")
        release.set()
        self.assertEqual([e["kind"] for e in self.streaming()], ["on demand"])


class AccountSwitchTest(DownloadTestCase):
    def test_the_operator_switches_downloads_on(self):
        response = self.client.post("/accounts/ondemand", data={"username": "other", "switch": "downloads",
                                                                "value": "true"}, headers=basic("admin", "12345"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.app.getAccounts()[1]["downloads"])
        self.download({"portal": PORTAL, "id": "5"}, "other")
