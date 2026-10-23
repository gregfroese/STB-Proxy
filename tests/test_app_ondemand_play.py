"""On Demand sessions: POST /api/ondemand/play, the rewritten HLS under
/api/ondemand/session/<sid>/, and the session's slot (ADR 0005, the viewer On Demand API
contract). One local fake server plays both the portal (create_link and the Files step) and
the storage host it links to; nothing leaves 127.0.0.1."""
import base64
import hashlib
import json
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qsl, urlparse

import stb
from tests.support import PORTAL, loadApp, portalConfig
from tests.test_api_lineup import basic
from tests.test_app_ondemand import onDemandConfig
from tests.test_app_ondemand_browse import movie
from tests.test_app_preview import FakeProcess
from tests.test_ondemand_series import infomirEpisode, infomirSeason, infomirSeries

# support.py stubs these out; these tests talk to the fake portal for real.
realGetOnDemandList = stb.getOnDemandList

MAC = "00:1A:79:00:00:01"
SEGMENT = b"\x47" * 200_000  # an MPEG-TS segment (sync bytes) bigger than one chunk
CHANNELS = [{"id": i, "name": "Channel " + i, "cmd": "ffrt http://localhost/ch/" + i} for i in ("2", "3")]


def quickHash(password):
    """A real Account password hash with one PBKDF2 round, so each request's login is quick."""
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), b"salt", 1)
    return "pbkdf2_sha256$1${}${}".format(base64.b64encode(b"salt").decode(), base64.b64encode(digest).decode())


class FakePortal:
    """The portal's load.php and its storage host, on one local server.

    Movie 5's link answers 302 to itself, then a single-variant master, a VOD media playlist
    with three segments (one by absolute URL) and the segments. `links` maps a cmd to the
    create_link `js`; `lists` maps get_ordered_list params to rows."""

    def __init__(self):
        fake = self
        self.mints = []  # (cmd, series) of every create_link
        self.fetches = []  # storage paths requested
        self.forbidden = False  # every storage request gets 403 (a newer session evicted it)
        self.lists = {}
        self.files = {}  # more storage paths: (body, Content-Type)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fake.handle(self)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:{}".format(self.server.server_address[1])
        self.url = self.base + "/stalker_portal/server/load.php"
        self.links = {
            "/media/5.mpg": {"id": "5", "cmd": "ffmpeg " + self.base + "/s1/tok/playlist.m3u8?token=T1&vtt_mode=x"},
            "/media/6.mpg": {"id": "6", "cmd": self.base + "/s1/tok/movie.mkv?token=T1"},
            "/media/7.mpg": {"id": "7", "cmd": "", "error": "access_denied"},
            "/media/file_901.mpg": {"id": "901", "cmd": self.base + "/s1/tok/playlist.m3u8?token=T1"},
        }
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def handle(self, request):
        parsed = urlparse(request.path)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if parsed.path == "/stalker_portal/server/load.php":
            return self.portal(request, query)
        self.fetches.append(parsed.path)
        if self.forbidden or query.get("token") != "T1":
            return self.send(request, 403, b"Forbidden", "text/plain")
        if parsed.path == "/s1/tok/playlist.m3u8" and "again" not in query:
            request.send_response(302)
            request.send_header("Location", request.path + "&again=1")
            request.send_header("Content-Length", "0")
            request.end_headers()
            return
        if parsed.path == "/s1/tok/playlist.m3u8":
            return self.send(request, 200, (
                "#EXTM3U\n#EXT-X-VERSION:3\n"
                '#EXT-X-STREAM-INF:BANDWIDTH=2000000,CODECS="avc1.640029,mp4a.40.2",CLOSED-CAPTIONS=NONE\n'
                "tracks-v1a1/mono.ts.m3u8?token=T1\n").encode(), "application/vnd.apple.mpegurl")
        if parsed.path == "/s1/tok/tracks-v1a1/mono.ts.m3u8":
            return self.send(request, 200, (
                "#EXTM3U\n#EXT-X-TARGETDURATION:16\n#EXT-X-PLAYLIST-TYPE:VOD\n"
                "#EXTINF:8.5,\nsegment1.ts?token=T1\n"
                "#EXTINF:8.5,\nsegment2.ts?token=T1\n"
                "#EXTINF:3.25,\n" + self.base + "/s2/segment3.ts?token=T1\n"
                "#EXT-X-ENDLIST\n").encode(), "application/vnd.apple.mpegurl")
        if parsed.path.endswith(".ts"):
            return self.send(request, 200, SEGMENT, "video/MP2T")
        if parsed.path in self.files:
            body, contentType = self.files[parsed.path]
            return self.send(request, 200, body, contentType)
        if parsed.path.endswith(".mkv"):
            return self.send(request, 200, b"\x1aE\xdf\xa3" + b"\0" * 100_000, "video/x-matroska")
        self.send(request, 404, b"Not found", "text/plain")

    def portal(self, request, query):
        action = query.get("action")
        if action == "create_link":
            self.mints.append((query.get("cmd"), query.get("series")))
            js = self.links.get(query.get("cmd"), {"cmd": "", "error": "nothing_to_play"})
        elif action == "get_ordered_list":
            params = tuple(sorted((k, v) for k, v in query.items()
                                  if k not in ("type", "action", "p", "JsHttpRequest")))
            rows = self.lists.get(params, [])
            js = {"total_items": len(rows), "max_page_items": 14, "data": rows}
        else:
            js = None
        self.send(request, 200, json.dumps({"js": js}).encode(), "application/json")

    def send(self, request, status, body, contentType):
        request.send_response(status)
        request.send_header("Content-Type", contentType)
        request.send_header("Content-Length", str(len(body)))
        request.end_headers()
        request.wfile.write(body)


class PlayTestCase(unittest.TestCase):
    """One portal with one MAC allowing one stream, two Tuners, and two Accounts with On
    Demand on. Its index holds Movies 5 (HLS), 6 (a progressive file) and 7 (not rented),
    and Series 77."""

    def setUp(self):
        self.portal = FakePortal()
        self.addCleanup(self.portal.close)
        self.app = loadApp(self, onDemandConfig(
            portals={PORTAL: portalConfig(name="First", url=self.portal.url)},
            settings={"test streams": "false", "hdhr tuners": "2"},
        ))
        self.client = self.app.app.test_client()
        self.app.getSettings()["enable security"] = "true"
        self.app.SHARE_GRACE = 0.3
        self.app.ONDEMAND_SESSION_SWEEP = 0  # no background sweeper; requests sweep
        self.now = 1000.0
        self.app.onDemandSessions.clock = lambda: self.now
        for username in ("viewer", "other"):
            self.app.getAccounts().append({
                "username": username, "hash": quickHash("secret"),
                "blocks": ["Kids"], "enabled": True, "on demand": True, "adult on demand": False,
            })
        index = self.app.onDemandIndex()
        self.addCleanup(index.close)
        index.setCategories(PORTAL, [{"id": "10", "title": "Action"}, {"id": "11", "title": "Hidden"}])
        index.addItems(PORTAL, [
            movie(5, "Heat", "2026-10-01 10:00:00", cmd="/media/5.mpg", has_files="0"),
            movie(6, "Progressive", "2026-10-01 10:00:00", cmd="/media/6.mpg", has_files="0"),
            movie(7, "Not rented", "2026-10-01 10:00:00", cmd="/media/7.mpg", has_files="0"),
            movie(8, "Secret", "2026-10-01 10:00:00", cat0="11", cmd="/media/8.mpg", has_files="0"),
            infomirSeries(77, "Show"),
        ])
        index.setStatus(PORTAL, "ready", lastRefresh=1)
        self.portal.lists = {
            (("movie_id", "77"),): [infomirSeason(31685, 2, "Second", 1)],
            (("movie_id", "77"), ("season_id", "31685")): [infomirEpisode(901, 31685, 3, "Three")],
            (("episode_id", "901"), ("movie_id", "77"), ("season_id", "31685")): [{
                "id": "901", "is_file": True, "cmd": "/media/file_901.mpg",
                "name": "English / Excellent quality (1080)"}],
        }
        patches = [
            (stb, "getOnDemandList", {"new": realGetOnDemandList}),
            (self.app.subprocess, "Popen", {"side_effect": lambda cmd, **kw: FakeProcess(cmd)}),
            (stb, "getAllChannels", {"return_value": CHANNELS}),
            (stb, "getLink", {"return_value": "http://stream.test/live"}),
            (self.app, "moveMac", {}),
        ]
        for target, name, kwargs in patches:
            patcher = mock.patch.object(target, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.stopAll)

    def stopAll(self):
        for tile in list(self.app.previews):
            self.app.stopPreview(tile)
        for stream in list(self.app.sharedStreams.values()):
            stream.end()
        for session in list(self.app.onDemandSessions.sessions.values()):
            session.end("stopped")

    def play(self, body, username="viewer", status=200):
        response = self.client.post("/api/ondemand/play", json=body, headers=basic(username, "secret"))
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response.get_json()

    def fetch(self, url, username="viewer", status=200):
        response = self.client.get(url, headers=basic(username, "secret"))
        self.assertEqual(response.status_code, status, response.get_data(as_text=True)[:300])
        return response

    def text(self, url, username="viewer"):
        return self.fetch(url, username).get_data(as_text=True)

    def streaming(self):
        return self.client.get("/streaming", headers=basic("admin", "12345")).get_json().get(PORTAL, [])

    def live(self, channel, tile=None):
        """Request a live channel as the operator (Plex) or a preview tile, reading it in the
        background if it plays."""
        query = "?web=true&viewer=browser1&tile=" + tile if tile else ""
        response = self.client.get("/play/{}/{}{}".format(PORTAL, channel, query))
        if response.status_code == 200:
            chunks = iter(response.response)
            next(chunks)
            threading.Thread(target=lambda: [None for _ in chunks], daemon=True).start()
        return response


    def uris(self, playlist):
        return [line for line in playlist.splitlines() if line and not line.startswith("#")]


class MoviePlayTest(PlayTestCase):
    def test_a_movie_plays_as_hls_through_the_session(self):
        body = self.play({"portal": PORTAL, "id": "5"})
        sid = body["session"]
        self.assertEqual(body, {"session": sid, "type": "hls", "durationSec": 20,
                                "url": "/api/ondemand/session/{}/master.m3u8".format(sid)})
        self.assertEqual(self.portal.mints, [("/media/5.mpg", "0")])

        base = "/api/ondemand/session/{}/".format(sid)
        master = self.text(body["url"])
        self.assertTrue(master.startswith("#EXTM3U"))
        self.assertIn('CODECS="avc1.640029,mp4a.40.2"', master)
        [variant] = self.uris(master)
        media = self.text(base + variant)
        segments = self.uris(media)
        self.assertEqual(len(segments), 3)
        self.assertIn("#EXT-X-ENDLIST", media)
        for uri in [variant] + segments:
            self.assertNotIn("/", uri)  # relative to the session, with nothing of the portal's
            self.assertNotIn("token", uri)
        for text in (master, media):
            self.assertNotIn("127.0.0.1", text)
            self.assertNotIn("T1", text)

        response = self.fetch(base + segments[2])
        self.assertEqual(response.headers["Content-Type"], "video/MP2T")
        chunks = list(response.response)
        self.assertGreater(len(chunks), 1)  # streamed a chunk at a time, never held whole
        self.assertEqual(b"".join(chunks), SEGMENT)
        self.assertEqual(self.portal.fetches[-1], "/s2/segment3.ts")
        self.assertEqual(self.portal.mints, [("/media/5.mpg", "0")])  # never re-minted


    def test_uri_attributes_and_renditions_are_rewritten_too(self):
        hls = "application/vnd.apple.mpegurl"
        self.portal.links["/media/5.mpg"] = {"cmd": self.portal.base + "/s3/master.m3u8?token=T1"}
        self.portal.files = {
            "/s3/master.m3u8": (
                b'#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="en",URI="audio/en.m3u8?token=T1"\n'
                b'#EXT-X-STREAM-INF:BANDWIDTH=1,AUDIO="a"\nvideo/main.m3u8?token=T1\n', hls),
            "/s3/video/main.m3u8": (
                b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4?token=T1"\n'
                b'#EXT-X-KEY:METHOD=AES-128,URI="/keys/k1?token=T1",IV=0x1\n'
                b"#EXTINF:4.0,\nv1.m4s?token=T1\n#EXT-X-ENDLIST\n", hls),
            "/s3/audio/en.m3u8": (b"#EXTM3U\n#EXTINF:4.0,\na1.aac?token=T1\n#EXT-X-ENDLIST\n", hls),
            "/keys/k1": (b"0123456789abcdef", "application/octet-stream"),
        }
        body = self.play({"portal": PORTAL, "id": "5"})
        self.assertEqual(body["durationSec"], 4)
        base = "/api/ondemand/session/{}/".format(body["session"])
        master = self.text(body["url"])
        audio = re.search(r'URI="([^"]+)"', master).group(1)
        [video] = self.uris(master)
        media = self.text(base + video)
        key = re.search(r'#EXT-X-KEY:.*URI="([^"]+)"', media).group(1)
        names = [audio, video, key, re.search(r'#EXT-X-MAP:URI="([^"]+)"', media).group(1)]
        names += self.uris(media) + self.uris(self.text(base + audio))
        for name in names:
            self.assertRegex(name, r"^[A-Za-z0-9.]+$")
        self.assertEqual(self.fetch(base + key).get_data(), b"0123456789abcdef")

    def test_a_link_in_an_ad_list_or_a_bare_string_plays(self):
        link = self.portal.base + "/s1/tok/playlist.m3u8?token=T1"
        for js in ([{"media_type": "vclub_ad", "cmd": "ffmpeg http://ads.invalid/ad.ts"}, {"cmd": "ffmpeg " + link}],
                   "auto " + link):
            self.portal.links["/media/5.mpg"] = js
            body = self.play({"portal": PORTAL, "id": "5"})
            self.assertEqual(body["durationSec"], 20)
            self.client.delete("/api/ondemand/session/" + body["session"], headers=basic("viewer", "secret"))


class RefusedPlayTest(PlayTestCase):
    def test_what_this_viewer_cant_see_is_not_found_and_nothing_is_minted(self):
        self.app.getHiddenOnDemand().append(self.app.ondemand.normalisedName("Hidden"))
        for body in ({"portal": PORTAL, "id": "8"},       # in a hidden category
                     {"portal": PORTAL, "id": "404"},     # no such item
                     {"portal": PORTAL, "id": "77"},      # a Series, not a Movie
                     {"portal": "nope", "id": "5"}):      # no such portal
            self.assertEqual(self.play(body, status=404)["code"], "not_found", body)
        self.assertEqual(self.portal.mints, [])

    def test_a_malformed_body_is_a_bad_request(self):
        for body in ({}, {"portal": PORTAL}, {"id": "5"}, {"portal": PORTAL, "seriesId": "77"},
                     {"portal": PORTAL, "id": None}, ["p1", "5"]):
            self.assertEqual(self.play(body, status=400)["code"], "bad_request", body)

    def test_an_account_without_on_demand_cant_play(self):
        self.app.accounts.findAccount(self.app.getAccounts(), "other")["on demand"] = False
        self.assertEqual(self.play({"portal": PORTAL, "id": "5"}, "other", status=404)["code"], "on_demand_off")

    def test_a_link_that_isnt_hls_is_unsupported_and_frees_the_slot(self):
        body = self.play({"portal": PORTAL, "id": "6"}, status=502)
        self.assertEqual(body["code"], "unsupported_stream")
        self.assertTrue(body["error"])
        self.assertEqual(self.streaming(), [])
        self.play({"portal": PORTAL, "id": "5"})

    def test_an_item_the_portal_wont_play_is_not_found(self):
        self.assertEqual(self.play({"portal": PORTAL, "id": "7"}, status=404)["code"], "not_found")
        self.assertEqual(self.streaming(), [])

    def test_a_portal_that_fails_is_a_portal_error_and_frees_the_slot(self):
        with mock.patch.object(stb, "getToken", return_value=None):
            self.assertEqual(self.play({"portal": PORTAL, "id": "5"}, status=502)["code"], "portal_error")
        self.portal.forbidden = True  # the link is dead before the first fetch
        self.assertEqual(self.play({"portal": PORTAL, "id": "5"}, status=502)["code"], "portal_error")
        self.assertEqual(self.streaming(), [])



class SlotTest(PlayTestCase):
    def test_a_session_takes_the_macs_slot_and_is_listed_as_on_demand(self):
        self.play({"portal": PORTAL, "id": "5"})
        [entry] = self.streaming()
        self.assertEqual((entry["kinds"], entry["channel name"], entry["account"], entry["mac"], entry["portal name"]),
                         (["on demand"], "Heat", "viewer", MAC, "First"))

    def test_with_no_free_slot_another_session_gets_busy(self):
        self.play({"portal": PORTAL, "id": "5"})
        for username in ("viewer", "other"):  # a second device on the same Account too
            body = self.play({"portal": PORTAL, "id": "5"}, username, status=503)
            self.assertEqual(body, {"error": "All tuners are busy", "code": "busy"})
        self.assertEqual(len(self.streaming()), 1)
        self.assertEqual(len(self.portal.mints), 1)

    def test_live_viewing_gets_busy_while_a_session_holds_the_slot(self):
        self.play({"portal": PORTAL, "id": "5"})
        self.assertEqual(self.live("2").status_code, 503)

    def test_a_session_gets_busy_while_a_live_viewer_holds_the_slot(self):
        self.assertEqual(self.live("2").status_code, 200)
        self.assertEqual(self.play({"portal": PORTAL, "id": "5"}, status=503)["code"], "busy")
        self.assertEqual(self.app.sharedStreams[(PORTAL, "2")].done, False)

    def test_a_session_stops_a_preview_for_its_slot(self):
        self.assertEqual(self.live("2", tile="t0").status_code, 200)
        self.play({"portal": PORTAL, "id": "5"})
        self.assertEqual([k for k, stream in self.app.sharedStreams.items() if not stream.done], [])
        self.assertEqual([e["kinds"] for e in self.streaming()], [["on demand"]])

    def test_a_session_takes_no_tuner(self):
        self.app.getSettings()["hdhr tuners"] = "1"
        self.app.getPortals()[PORTAL]["streams per mac"] = "2"
        self.assertEqual(self.live("2").status_code, 200)  # the one Tuner
        self.play({"portal": PORTAL, "id": "5"})


class ReplacesTest(PlayTestCase):
    def test_replaces_hands_the_viewers_own_slot_to_the_next_episode(self):
        first = self.play({"portal": PORTAL, "id": "5"})
        second = self.play({"portal": PORTAL, "seriesId": "77", "seasonId": "31685", "episodeId": "901",
                            "replaces": first["session"]})
        self.assertNotEqual(first["session"], second["session"])
        self.assertEqual(self.fetch(first["url"], status=410).get_json()["reason"], "stopped")
        self.assertTrue(self.text(second["url"]).startswith("#EXTM3U"))
        self.assertEqual([e["channel name"] for e in self.streaming()], ["Show - S2 E3"])

    def test_replaces_naming_another_accounts_session_is_ignored(self):
        first = self.play({"portal": PORTAL, "id": "5"})
        body = self.play({"portal": PORTAL, "id": "5", "replaces": first["session"]}, "other", status=503)
        self.assertEqual(body["code"], "busy")
        self.assertTrue(self.text(first["url"]).startswith("#EXTM3U"))


class SessionEndTest(PlayTestCase):
    def setUp(self):
        super().setUp()
        self.started = self.play({"portal": PORTAL, "id": "5"})
        self.base = "/api/ondemand/session/{}/".format(self.started["session"])
        [self.variant] = self.uris(self.text(self.started["url"]))
        self.segments = self.uris(self.text(self.base + self.variant))

    def assertEnded(self, reason):
        for name in ("master.m3u8", self.variant, self.segments[0]):
            body = self.fetch(self.base + name, status=410).get_json()
            self.assertEqual((body["code"], body["reason"]), ("session_ended", reason), name)
            self.assertTrue(body["error"])
        self.assertEqual(self.streaming(), [])
        self.assertEqual(self.portal.mints, [("/media/5.mpg", "0")])  # never re-minted

    def test_a_session_ends_after_120_seconds_with_no_request(self):
        self.now += 119
        self.fetch(self.base + self.segments[0])
        self.now += 119
        self.assertEqual(len(self.streaming()), 1)
        self.now += 1
        self.assertEqual(self.streaming(), [])
        self.assertEnded("idle")

    def test_an_upstream_403_evicts_the_session(self):
        self.portal.forbidden = True
        self.assertEqual(self.fetch(self.base + self.segments[1], status=410).get_json()["reason"], "evicted")
        self.portal.forbidden = False
        self.assertEnded("evicted")

    def test_the_viewer_can_end_the_session(self):
        response = self.client.delete(self.base.rstrip("/"), headers=basic("viewer", "secret"))
        self.assertEqual(response.status_code, 204)
        self.assertEnded("stopped")

    def test_the_operator_can_stop_the_session_from_the_streams_page(self):
        [entry] = self.streaming()
        response = self.client.post("/streams/stop", data={"portal": PORTAL, "session": entry["session"]},
                                    headers=basic("admin", "12345"))
        self.assertEqual(response.status_code, 200)
        self.assertEnded("stopped")

    def test_the_session_belongs_to_its_account(self):
        self.assertEqual(self.fetch(self.started["url"], "other", status=404).get_json()["code"], "not_found")
        self.assertEqual(self.client.delete(self.base.rstrip("/"), headers=basic("other", "secret")).status_code, 404)
        self.assertEqual(self.fetch(self.base + "nothing.ts", status=404).get_json()["code"], "not_found")
        self.assertTrue(self.text(self.started["url"]).startswith("#EXTM3U"))

    def test_an_ended_session_is_forgotten_after_an_hour(self):
        self.client.delete(self.base.rstrip("/"), headers=basic("viewer", "secret"))
        self.now += 3600
        self.assertEqual(self.fetch(self.started["url"], status=404).get_json()["code"], "not_found")


class StreamsPageTest(PlayTestCase):
    def test_the_streams_page_badges_on_demand_and_stops_it_by_session(self):
        body = self.client.get("/streams", headers=basic("admin", "12345")).get_data(as_text=True)
        self.assertIn('"on demand": "on demand"', body)
        self.assertIn("data-session", body)
        self.assertIn("session: button.dataset.session", body)


class EpisodePlayTest(PlayTestCase):
    def test_an_infomir_episode_plays_its_file_after_the_files_step(self):
        body = self.play({"portal": PORTAL, "seriesId": "77", "seasonId": "31685", "episodeId": "901"})
        self.assertEqual(body["durationSec"], 20)
        self.assertEqual(self.portal.mints, [("/media/file_901.mpg", "0")])
        self.assertTrue(self.text(body["url"]).startswith("#EXTM3U"))
        [entry] = self.streaming()
        self.assertEqual(entry["channel name"], "Show - S2 E3")

    def test_a_numbered_episode_mints_its_series_cmd_with_its_number(self):
        index = self.app.onDemandIndex()
        index.addItems(PORTAL, [movie(9, "Old show", "2026-10-01 10:00:00", is_series="1",
                                      series=[1, 2, 3], cmd="/media/5.mpg")])
        self.play({"portal": PORTAL, "seriesId": "9", "seasonId": "1", "episodeId": "2"})
        self.assertEqual(self.portal.mints, [("/media/5.mpg", "2")])

    def test_an_episode_that_isnt_one_of_the_seasons_is_not_found(self):
        for body in ({"portal": PORTAL, "seriesId": "77", "seasonId": "31685", "episodeId": "999"},
                     {"portal": PORTAL, "seriesId": "77", "seasonId": "1", "episodeId": "901"},
                     {"portal": PORTAL, "seriesId": "5", "seasonId": "31685", "episodeId": "901"}):
            self.assertEqual(self.play(body, status=404)["code"], "not_found", body)
        self.assertEqual(self.portal.mints, [])


if __name__ == "__main__":
    unittest.main()
