import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from bff import config as config_module
from bff.security import login_limiter
from bff.sessions import SessionStore, build_fernet


def _xmltv() -> bytes:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=10)).strftime("%Y%m%d%H%M%S +0000")
    stop = (now + timedelta(minutes=20)).strftime("%Y%m%d%H%M%S +0000")
    return (
        '<?xml version="1.0"?><tv>'
        f'<programme start="{start}" stop="{stop}" channel="bbc.uk"><title>News</title></programme>'
        "</tv>"
    ).encode()


def _auth(user: str, password: str) -> str:
    raw = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {raw}"


_upstream_calls: dict[str, int] = {}


def _upstream(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/lineup":
        if request.headers.get("authorization") == _auth("katie", "pw"):
            return httpx.Response(
                200,
                json={
                    "account": "katie",
                    "blocks": ["News"],
                    "channels": [
                        {
                            "portal": "1",
                            "portalName": "Provider",
                            "channelId": "9",
                            "name": "BBC News",
                            "number": "501",
                            "logo": None,
                            "genre": "News",
                            "epgId": "bbc.uk",
                            "blocks": ["News"],
                            "favourite": False,
                            "blockFavourites": [],
                            "url": "/play/1/9",
                        }
                    ],
                    "failedPortals": [],
                },
            )
        return httpx.Response(401, json={"error": "no"})
    if path == "/xmltv":
        return httpx.Response(200, content=_xmltv())
    if path == "/api/guide/search":
        if request.headers.get("authorization") != _auth("katie", "pw"):
            return httpx.Response(401, json={"error": "no"})
        if request.url.params.get("q") == "bad(":
            return httpx.Response(400, json={"error": "Not a valid regex: bad("})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "portal": "1",
                        "channelId": "9",
                        "channelName": "BBC News",
                        "channelNumber": "501",
                        "logo": None,
                        "epgId": "bbc.uk",
                        "start": 1000,
                        "stop": 2000,
                        "title": "News",
                        "desc": "",
                    }
                ],
                "total": 1,
                "loadedAt": 1.0,
                "programmes": 42,
                "failed": [],
                "partial": [],
                "account": "katie",
            },
        )
    if path == "/api/guide/channel":
        _upstream_calls["guide_channel"] = _upstream_calls.get("guide_channel", 0) + 1
        if request.headers.get("authorization") != _auth("katie", "pw"):
            return httpx.Response(401, json={"error": "no"})
        if request.url.params.get("channelId") == "missing":
            return httpx.Response(404, json={"error": "Unknown channel"})
        return httpx.Response(
            200,
            json={
                "portal": "1",
                "channelId": "9",
                "programmes": [{"start": 1000, "stop": 2000, "title": "News", "desc": ""}],
            },
        )
    if path == "/play/1/9":
        return httpx.Response(503, json={"error": "busy"})
    if path == "/play/1/ok":
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"\x47\x40\x00\x10stream-bytes"),
            headers={"Content-Type": "video/mp2t"},
        )
    if path.startswith("/api/ondemand/"):
        return _ondemand_upstream(request)
    if path == "/static/STB-Proxy-Companion.apk":
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"APK-BYTES"),
            headers={"Content-Type": "application/octet-stream"},
        )
    return httpx.Response(404)


_MASTER = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=5000000\nv0.m3u8\n"


# A whole 64 KiB read, so the BFF relays it at once rather than waiting to fill one.
_FIRST_CHUNK = b"\x47" * 65536


class _EndlessSegment(httpx.AsyncByteStream):
    """A segment the portal is still sending: one chunk, then nothing until it is closed."""

    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self):
        yield _FIRST_CHUNK
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


_endless_segment = _EndlessSegment()


# The last /api/ondemand/* request STB-Proxy saw, so tests can check what the BFF forwarded.
_ondemand_seen: list[httpx.Request] = []


def _ondemand_upstream(request: httpx.Request) -> httpx.Response:
    """A fake of STB-Proxy's On Demand door: Basic auth, then the routes the BFF mirrors."""
    _ondemand_seen.append(request)
    if request.headers.get("authorization") != _auth("katie", "pw"):
        return httpx.Response(401, text="Could not verify your login!")
    path = request.url.path
    if path == "/api/ondemand/categories":
        return httpx.Response(200, json={"categories": [{"id": "drama", "name": "Drama", "count": 3}], "portals": []})
    if path == "/api/ondemand/items":
        if request.url.params.get("q") == "x":
            return httpx.Response(400, json={"error": "Search needs at least 2 characters", "code": "bad_request"})
        return httpx.Response(200, json={"items": [], "total": 0})
    if path == "/api/ondemand/item/p1/42":
        return httpx.Response(200, json={"portal": "p1", "id": "42", "kind": "movie", "name": "Film"})
    if path == "/api/ondemand/series/p1/7/season/3":
        return httpx.Response(200, json={"episodes": [{"id": "1", "seasonId": "3", "number": 1, "name": None}]})
    if path == "/api/ondemand/continue":
        return httpx.Response(200, json={"items": [{"portal": "p1", "id": "42", "kind": "movie"}]})
    if path == "/api/ondemand/play" and request.method == "POST":
        body = json.loads(request.content or b"null")
        if request.headers.get("content-type") != "application/json" or not isinstance(body, dict):
            return httpx.Response(400, json={"error": "Send a JSON object", "code": "bad_request"})
        if body.get("id") == "busy":
            return httpx.Response(503, json={"error": "All tuners are busy", "code": "busy"})
        return httpx.Response(200, json={
            "session": "s1", "type": "hls", "url": "/api/ondemand/session/s1/master.m3u8", "durationSec": 5400,
        })
    if path == "/api/ondemand/progress" and request.method == "PUT":
        body = json.loads(request.content or b"null")
        if request.headers.get("content-type") != "application/json" or not isinstance(body, dict):
            return httpx.Response(400, json={"error": "Send the item", "code": "bad_request"})
        return httpx.Response(204)
    if path == "/api/ondemand/session/s1" and request.method == "DELETE":
        return httpx.Response(204)
    if path == "/api/ondemand/poster/p1/42":
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"\xff\xd8poster-bytes"),
            headers={"Content-Type": "image/jpeg", "Cache-Control": "public, max-age=604800", "Content-Length": "14"},
        )
    if path == "/api/ondemand/poster/p1/none":
        return httpx.Response(404, json={"error": "No poster", "code": "not_found"})
    if path == "/api/ondemand/poster/p1/queued":
        return httpx.Response(504, json={"error": "Too many posters at once, try again"})
    if path == "/api/ondemand/session/s1/master.m3u8":
        return httpx.Response(
            200,
            stream=httpx.ByteStream(_MASTER),
            headers={"Content-Type": "application/vnd.apple.mpegurl", "Cache-Control": "no-store"},
        )
    if path == "/api/ondemand/session/s1/s0.ts":
        if request.headers.get("range") == "bytes=4-":
            return httpx.Response(
                206,
                stream=httpx.ByteStream(b"segment-tail"),
                headers={
                    "Content-Type": "video/mp2t",
                    "Content-Length": "12",
                    "Content-Range": "bytes 4-15/16",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-store",
                },
            )
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"\x47seg-segment-tail"),
            headers={"Content-Type": "video/mp2t", "Content-Length": "17", "Cache-Control": "no-store"},
        )
    if path == "/api/ondemand/session/s1/s1.ts":
        return httpx.Response(200, stream=_endless_segment, headers={"Content-Type": "video/mp2t"})
    if path == "/api/ondemand/session/gone/v0.m3u8":
        return httpx.Response(
            410, json={"error": "Playback stopped", "code": "session_ended", "reason": "evicted"}
        )
    if path == "/api/ondemand/item/p1/broken":
        return httpx.Response(500, text="<html>Internal Server Error</html>", headers={"Content-Type": "text/html"})
    return httpx.Response(404, json={"error": "That isn't in On Demand", "code": "not_found"})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.config, "session_db", str(tmp_path / "sessions.db"))
    monkeypatch.setattr(config_module.config, "cookie_secure", False)
    monkeypatch.setattr(config_module.config, "hls_dir", str(tmp_path / "hls-real"))
    login_limiter._state.clear()  # noqa: SLF001 - isolate the shared limiter between tests
    from bff.main import app

    with TestClient(app) as test_client:
        app.state.store = SessionStore(str(tmp_path / "sessions.db"), fernet=build_fernet())
        app.state.client = httpx.AsyncClient(
            transport=httpx.MockTransport(_upstream), base_url="http://proxy"
        )
        hls_dir = tmp_path / "hls"
        hls_dir.mkdir()
        (hls_dir / "index.m3u8").write_text("#EXTM3U\n#EXT-X-VERSION:7\n")
        (hls_dir / "init.mp4").write_bytes(b"\x00\x00\x00\x18ftyp")
        (hls_dir / "seg00000.m4s").write_bytes(b"\x00\x00\x00\x08moof")
        app.state.hls = FakeHls(hls_dir)
        yield test_client


class FakeHls:
    def __init__(self, directory, ended=False):
        self.directory = directory
        self.ended = ended

    def playlist_dir(self, portal, channel_id, user, password, transcode=False, session="default"):  # noqa: ARG002
        return None if self.ended else self.directory

    def stop(self, portal, channel_id, transcode, session):  # noqa: ARG002
        self.ended = True

    def reap(self):
        pass

    def shutdown(self):
        pass


def test_login_requires_bad_credentials_401(client):
    response = client.post("/api/login", json={"username": "katie", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["code"] == "bad_credentials"


def test_login_sets_session_and_lineup_rewrites_urls(client):
    response = client.post("/api/login", json={"username": "katie", "password": "pw"})
    assert response.status_code == 200
    body = response.json()
    assert body["account"] == "katie"
    assert body["operator"] is False
    assert body["csrf"]

    session = client.get("/api/session")
    assert session.status_code == 200
    assert session.json()["account"] == "katie"

    lineup = client.get("/api/lineup")
    assert lineup.status_code == 200
    assert lineup.json()["channels"][0]["url"] == "/stream/1/9"


def test_protected_routes_require_a_session(client):
    assert client.get("/api/lineup").status_code == 401
    assert client.get("/api/epg").status_code == 401


def test_epg_is_now_next_by_epg_id(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    epg = client.get("/api/epg")
    assert epg.status_code == 200
    assert epg.json()["bbc.uk"]["now"]["title"] == "News"


def test_guide_routes_require_a_session(client):
    assert client.get("/api/guide/search?q=news").status_code == 401
    assert client.get("/api/guide/channel?portal=1&channelId=9").status_code == 401


def test_guide_search_proxies_the_json_unchanged(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/api/guide/search?q=news&now=true")
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["title"] == "News"
    assert body["results"][0]["epgId"] == "bbc.uk"
    assert body["account"] == "katie"


def test_guide_search_bad_regex_is_a_client_400(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/api/guide/search?q=bad(&mode=regex")
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
    assert "regex" in response.json()["error"]


def test_guide_channel_out_of_scope_is_a_404(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/api/guide/channel?portal=1&channelId=missing")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_guide_channel_is_cached_and_refresh_bypasses(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    _upstream_calls["guide_channel"] = 0
    assert client.get("/api/guide/channel?portal=1&channelId=9").status_code == 200
    assert client.get("/api/guide/channel?portal=1&channelId=9").status_code == 200
    assert _upstream_calls["guide_channel"] == 1
    assert client.get("/api/guide/channel?portal=1&channelId=9&refresh=1").status_code == 200
    assert _upstream_calls["guide_channel"] == 2


def test_stream_503_is_normalised(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/stream/1/9")
    assert response.status_code == 503
    assert response.json()["code"] == "all_tuners_busy"


def test_stream_success_passes_through_body_and_headers(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/stream/1/ok")
    assert response.status_code == 200
    assert response.content == b"\x47\x40\x00\x10stream-bytes"
    assert response.headers["content-type"] == "video/mp2t"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"


def test_stream_404_is_not_found(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/stream/1/missing")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_stream_requires_a_session(client):
    assert client.get("/stream/1/ok").status_code == 401


def test_companion_apk_is_proxied_with_a_download_name(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/companion.apk")
    assert response.status_code == 200
    assert response.content == b"APK-BYTES"
    assert response.headers["content-type"] == "application/vnd.android.package-archive"
    assert "attachment" in response.headers["content-disposition"]
    assert "STB-Proxy-Companion.apk" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"


def test_companion_apk_is_public_so_the_login_page_can_offer_it(client):
    assert client.get("/companion.apk").status_code == 200


def test_hls_playlist_and_segments_are_served(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    playlist = client.get("/hls/1/9/copy/s1/index.m3u8")
    assert playlist.status_code == 200
    assert playlist.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert playlist.text.startswith("#EXTM3U")

    segment = client.get("/hls/1/9/copy/s1/seg00000.m4s")
    assert segment.status_code == 200
    assert segment.content == b"\x00\x00\x00\x08moof"

    assert client.get("/hls/1/9/transcode/s1/index.m3u8").status_code == 200


def test_hls_ended_session_is_404(client):
    from bff.main import app

    app.state.hls = FakeHls(None, ended=True)
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    assert client.get("/hls/1/9/copy/s1/index.m3u8").status_code == 404


def test_hls_session_can_be_stopped(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    assert client.delete("/hls/1/9/copy/s1").status_code == 200
    # Once stopped, the session is ended, so the playlist is gone.
    assert client.get("/hls/1/9/copy/s1/index.m3u8").status_code == 404


def test_hls_rejects_unknown_names_and_requires_a_session(client):
    assert client.get("/hls/1/9/copy/s1/index.m3u8").status_code == 401
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    assert client.get("/hls/1/9/copy/s1/evil.txt").status_code == 404
    assert client.get("/hls/1/9/copy/s1/seg99999.m4s").status_code == 404
    assert client.get("/hls/1/9/nope/s1/index.m3u8").status_code == 404


def test_logout_requires_csrf_and_clears_session(client):
    login = client.post("/api/login", json={"username": "katie", "password": "pw"})
    csrf = login.json()["csrf"]

    assert client.post("/api/logout").status_code == 403

    response = client.post("/api/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert client.get("/api/session").status_code == 401


def test_cookie_is_reissued_on_activity(client):
    client.post("/api/login", json={"username": "katie", "password": "pw"})
    response = client.get("/api/session")
    assert response.status_code == 200
    # The sliding idle window is re-issued to the browser on each authenticated call.
    assert "set-cookie" in response.headers


def test_security_headers_present(client):
    response = client.get("/api/session")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_spa_page_is_revalidated_so_a_deploy_reaches_tv_browsers(client, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>app</title>")
    monkeypatch.setattr(config_module.config, "static_dir", dist)
    for path in ("/", "/watch", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"


def _login(client) -> str:
    return client.post("/api/login", json={"username": "katie", "password": "pw"}).json()["csrf"]


def test_ondemand_json_passes_through_unchanged(client):
    _login(client)
    response = client.get("/api/ondemand/categories")
    assert response.status_code == 200
    assert response.json() == {"categories": [{"id": "drama", "name": "Drama", "count": 3}], "portals": []}


def test_ondemand_errors_pass_through_status_and_body(client):
    _login(client)
    response = client.get("/api/ondemand/items?q=x")
    assert response.status_code == 400
    assert response.json() == {"error": "Search needs at least 2 characters", "code": "bad_request"}


def test_ondemand_browse_routes_mirror_their_paths_and_query(client):
    _login(client)
    response = client.get("/api/ondemand/items?category=drama&q=war&sort=year&offset=60&limit=30")
    assert response.status_code == 200
    forwarded = _ondemand_seen[-1]
    assert forwarded.url.path == "/api/ondemand/items"
    assert dict(forwarded.url.params) == {"category": "drama", "q": "war", "sort": "year", "offset": "60", "limit": "30"}

    assert client.get("/api/ondemand/item/p1/42").json()["name"] == "Film"
    assert client.get("/api/ondemand/series/p1/7/season/3").json()["episodes"][0]["seasonId"] == "3"
    assert client.get("/api/ondemand/continue").json()["items"][0]["id"] == "42"
    assert client.get("/api/ondemand/item/p1/missing").json() == {"error": "That isn't in On Demand", "code": "not_found"}


def test_ondemand_json_is_not_cached(client):
    _login(client)
    assert client.get("/api/ondemand/continue").headers["cache-control"] == "no-store"
    before = len(_ondemand_seen)
    client.get("/api/ondemand/continue")
    client.get("/api/ondemand/continue")
    assert len(_ondemand_seen) == before + 2


def test_ondemand_routes_require_a_session(client):
    for path in ("/api/ondemand/categories", "/api/ondemand/items", "/api/ondemand/item/p1/42",
                 "/api/ondemand/series/p1/7/season/3", "/api/ondemand/continue"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["code"] == "unauthorized"


def test_ondemand_revoked_credentials_end_the_session(client):
    from bff.main import app

    # The Account's password changed on STB-Proxy since sign-in: the stored Basic login is refused.
    token, _ = app.state.store.create(username="katie", account="katie", password="old", user_agent=None, remote_ip=None)
    client.cookies.set(config_module.config.cookie_name, token)
    response = client.get("/api/ondemand/categories")
    assert response.status_code == 401
    assert response.json()["code"] == "session_invalid"
    assert client.get("/api/session").status_code == 401


def test_ondemand_non_json_upstream_error_is_a_proxy_error(client):
    _login(client)
    response = client.get("/api/ondemand/item/p1/broken")
    assert response.status_code == 502
    assert response.json()["code"] == "proxy_error"


def test_ondemand_ids_cannot_climb_out_of_the_route(client):
    _login(client)
    before = len(_ondemand_seen)
    assert client.get("/api/ondemand/item/p1/%2E%2E").status_code == 404
    assert client.get("/api/ondemand/series/p1/7/season/%2E").status_code == 404
    assert len(_ondemand_seen) == before


def test_ondemand_play_forwards_the_body_and_passes_the_session_back(client):
    csrf = _login(client)
    response = client.post("/api/ondemand/play", json={"portal": "p1", "id": "42"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.json() == {
        "session": "s1", "type": "hls", "url": "/api/ondemand/session/s1/master.m3u8", "durationSec": 5400,
    }
    forwarded = _ondemand_seen[-1]
    assert forwarded.method == "POST"
    assert json.loads(forwarded.content) == {"portal": "p1", "id": "42"}


def test_ondemand_play_busy_is_passed_through_not_renamed(client):
    csrf = _login(client)
    response = client.post("/api/ondemand/play", json={"portal": "p1", "id": "busy"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 503
    assert response.json() == {"error": "All tuners are busy", "code": "busy"}


def test_ondemand_progress_sent_with_keepalive_from_a_hidden_page_is_accepted(client):
    csrf = _login(client)
    # A keepalive fetch fired on visibilitychange: same-origin, its body maybe sent as text/plain.
    response = client.put(
        "/api/ondemand/progress",
        content=b'{"portal": "p1", "id": "42", "positionSec": 61.5, "durationSec": 5400}',
        headers={"X-CSRF-Token": csrf, "Content-Type": "text/plain;charset=UTF-8", "Sec-Fetch-Mode": "cors"},
    )
    assert response.status_code == 204
    assert response.content == b""
    forwarded = _ondemand_seen[-1]
    assert forwarded.method == "PUT"
    assert json.loads(forwarded.content)["positionSec"] == 61.5


def test_ondemand_session_can_be_released(client):
    csrf = _login(client)
    response = client.delete("/api/ondemand/session/s1", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert _ondemand_seen[-1].method == "DELETE"
    assert _ondemand_seen[-1].url.path == "/api/ondemand/session/s1"


def test_ondemand_changes_need_the_csrf_token(client):
    _login(client)
    before = len(_ondemand_seen)
    assert client.post("/api/ondemand/play", json={"portal": "p1", "id": "42"}).status_code == 403
    assert client.put("/api/ondemand/progress", json={"portal": "p1", "id": "42", "watched": True}).status_code == 403
    response = client.delete("/api/ondemand/session/s1", headers={"X-CSRF-Token": "wrong"})
    assert response.status_code == 403
    assert response.json()["code"] == "csrf"
    assert len(_ondemand_seen) == before


def test_ondemand_poster_is_streamed_with_its_cache_control(client):
    _login(client)
    response = client.get("/api/ondemand/poster/p1/42")
    assert response.status_code == 200
    assert response.content == b"\xff\xd8poster-bytes"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=604800"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_ondemand_poster_errors_pass_through(client):
    _login(client)
    missing = client.get("/api/ondemand/poster/p1/none")
    assert missing.status_code == 404
    assert missing.json() == {"error": "No poster", "code": "not_found"}
    queued = client.get("/api/ondemand/poster/p1/queued")
    assert queued.status_code == 504
    assert queued.json() == {"error": "Too many posters at once, try again"}


def test_ondemand_poster_requires_a_session(client):
    assert client.get("/api/ondemand/poster/p1/42").status_code == 401


def test_ondemand_playlist_is_passed_through_without_rewriting(client):
    _login(client)
    response = client.get("/api/ondemand/session/s1/master.m3u8")
    assert response.status_code == 200
    assert response.content == _MASTER
    assert response.headers["content-type"] == "application/vnd.apple.mpegurl"
    assert response.headers["cache-control"] == "no-store"


def test_ondemand_segment_is_streamed_through(client):
    _login(client)
    response = client.get("/api/ondemand/session/s1/s0.ts")
    assert response.status_code == 200
    assert response.content == b"\x47seg-segment-tail"
    assert response.headers["content-type"] == "video/mp2t"
    assert response.headers["content-length"] == "17"


def test_ondemand_segment_range_is_forwarded_and_206_relayed(client):
    _login(client)
    response = client.get("/api/ondemand/session/s1/s0.ts", headers={"Range": "bytes=4-"})
    assert response.status_code == 206
    assert response.content == b"segment-tail"
    assert response.headers["content-range"] == "bytes 4-15/16"
    assert _ondemand_seen[-1].headers["range"] == "bytes=4-"


def test_ondemand_ended_session_410_passes_through(client):
    _login(client)
    response = client.get("/api/ondemand/session/gone/v0.m3u8")
    assert response.status_code == 410
    assert response.json() == {"error": "Playback stopped", "code": "session_ended", "reason": "evicted"}


def test_ondemand_session_files_require_a_session(client):
    assert client.get("/api/ondemand/session/s1/master.m3u8").status_code == 401


def test_ondemand_viewer_leaving_closes_the_upstream_segment(client):
    from bff.main import app

    _login(client)
    token = client.cookies.get(config_module.config.cookie_name)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/ondemand/session/s1/s1.ts",
        "raw_path": b"/api/ondemand/session/s1/s1.ts",
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"cookie", f"{config_module.config.cookie_name}={token}".encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "state": {},
    }

    async def watch_then_leave():
        received: list[bytes] = []
        left = asyncio.Event()
        asked = False

        async def receive():
            nonlocal asked
            if not asked:
                asked = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await left.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                received.append(message["body"])
                left.set()  # the viewer closes the tab after the first chunk

        await asyncio.wait_for(app(scope, receive, send), timeout=5)
        return received

    received = asyncio.run(watch_then_leave())
    assert received == [_FIRST_CHUNK]
    assert _endless_segment.closed
