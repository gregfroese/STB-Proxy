import base64
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
    if path == "/static/STB-Proxy-Companion.apk":
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"APK-BYTES"),
            headers={"Content-Type": "application/octet-stream"},
        )
    return httpx.Response(404)


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
