"""STB-Proxy web viewer BFF (spec 1.2/1.3/1.4).

Same-origin FastAPI server: authenticates viewers against STB-Proxy, holds their
credentials server-side, proxies the lineup / guide / live TS, and serves the
built Svelte SPA.
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .cache import TTLCache
from .config import config
from .epg import parse_now_next
from .errors import (
    ApiError,
    all_tuners_busy,
    api_error_handler,
    not_found,
    proxy_error,
    proxy_unreachable,
    session_invalid,
    unauthorized,
)
from .hls import HlsManager
from .security import apply_security_headers, check_origin, login_limiter, valid_csrf
from .sessions import Session, SessionStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stbweb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(
        base_url=config.proxy_url,
        follow_redirects=True,
        timeout=httpx.Timeout(config.request_timeout, read=config.stream_timeout),
    )
    app.state.store = SessionStore(config.session_db)
    app.state.lineup_cache = TTLCache()
    app.state.epg_cache = TTLCache()
    app.state.guide_cache = TTLCache()
    app.state.hls = (
        HlsManager(config.hls_dir, config.proxy_url, config.hls_ttl, config.ffmpeg_bin)
        if config.hls_enabled
        else None
    )
    revalidate_task = asyncio.create_task(_revalidate_loop(app))
    reap_task = asyncio.create_task(_hls_reap_loop(app))
    logger.info("BFF ready; upstream=%s static=%s", config.proxy_url, config.static_dir)
    try:
        yield
    finally:
        revalidate_task.cancel()
        reap_task.cancel()
        for task in (revalidate_task, reap_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        if app.state.hls is not None:
            app.state.hls.shutdown()
        await app.state.client.aclose()


app = FastAPI(title="STB-Proxy Web", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    apply_security_headers(response.headers)
    # Re-issue the cookie on activity so its browser Max-Age tracks the sliding
    # idle window (spec 1.4); the server-side expiry stays authoritative.
    token = request.cookies.get(config.cookie_name)
    store: SessionStore | None = getattr(request.app.state, "store", None)
    if token and store is not None and store.get(token) is not None:
        _set_cookie(response, token)
    return response


def _basic(request: Request, session: Session) -> tuple[str, str]:
    return session.basic(request.app.state.store.fernet)


def _get_session(request: Request) -> Session:
    token = request.cookies.get(config.cookie_name)
    session = request.app.state.store.get(token) if token else None
    if session is None:
        raise unauthorized()
    return session


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        config.cookie_name,
        token,
        max_age=config.idle,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


@app.post("/api/login")
async def login(request: Request):
    if not check_origin(request):
        raise ApiError(403, "csrf", "Cross-site request rejected.")

    try:
        body = await request.json()
    except ValueError:
        raise ApiError(400, "bad_request", "Expected a JSON body.")
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not username or not password:
        raise ApiError(400, "bad_request", "Username and password are required.")

    retry_after = login_limiter.retry_after(username)
    if retry_after > 0:
        return JSONResponse(
            {"error": "Too many attempts. Try again later.", "code": "rate_limited"},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    client: httpx.AsyncClient = request.app.state.client
    try:
        upstream = await client.get("/api/lineup", auth=(username, password))
    except httpx.HTTPError:
        raise ApiError(503, "proxy_unreachable", "STB-Proxy is unreachable right now.")

    if upstream.status_code == 401:
        login_limiter.record_failure(username)
        raise ApiError(401, "bad_credentials", "Wrong username or password.")
    if upstream.status_code >= 500:
        raise ApiError(503, "proxy_error", "STB-Proxy returned an error.")
    if upstream.status_code != 200:
        raise ApiError(502, "proxy_error", "STB-Proxy returned an error.")
    try:
        data = upstream.json()
    except ValueError:
        raise ApiError(502, "proxy_error", "STB-Proxy returned an error.")

    account = data.get("account")
    login_limiter.record_success(username)

    token, csrf = request.app.state.store.create(
        username=username,
        account=account,
        password=password,
        user_agent=request.headers.get("user-agent"),
        remote_ip=request.client.host if request.client else None,
    )
    response = JSONResponse({"account": account, "operator": account is None, "csrf": csrf})
    _set_cookie(response, token)
    return response


@app.post("/api/logout")
async def logout(request: Request):
    session = _get_session(request)
    if not valid_csrf(session.csrf, request.headers.get("x-csrf-token")):
        raise ApiError(403, "csrf", "Invalid CSRF token.")
    request.app.state.store.delete_hash(session.token_hash)
    response = JSONResponse({"ok": True})
    response.delete_cookie(config.cookie_name, path="/")
    return response


@app.get("/api/session")
async def session_info(request: Request):
    session = _get_session(request)
    return {
        "account": session.account,
        "operator": session.account is None,
        "csrf": session.csrf,
    }


@app.get("/api/lineup")
async def lineup(request: Request):
    session = _get_session(request)
    cache: TTLCache = request.app.state.lineup_cache
    key = ("lineup", session.username)
    cached = cache.get(key)
    if cached is not None:
        return cached

    client: httpx.AsyncClient = request.app.state.client
    try:
        upstream = await client.get("/api/lineup", auth=_basic(request, session))
    except httpx.HTTPError:
        raise proxy_unreachable()

    if upstream.status_code == 401:
        request.app.state.store.delete_hash(session.token_hash)
        raise session_invalid()
    if upstream.status_code != 200:
        raise proxy_error()
    try:
        data = upstream.json()
    except ValueError:
        raise proxy_error()

    for channel in data.get("channels", []):
        url = channel.get("url", "")
        if isinstance(url, str) and url.startswith("/play/"):
            channel["url"] = "/stream/" + url[len("/play/"):]

    cache.set(key, data, config.lineup_ttl)
    return data


@app.get("/api/epg")
async def epg(request: Request):
    session = _get_session(request)
    cache: TTLCache = request.app.state.epg_cache
    key = ("epg", session.username)
    cached = cache.get(key)
    if cached is not None:
        return cached

    client: httpx.AsyncClient = request.app.state.client
    try:
        upstream = await client.get("/xmltv", auth=_basic(request, session))
    except httpx.HTTPError:
        raise proxy_unreachable()

    if upstream.status_code == 401:
        request.app.state.store.delete_hash(session.token_hash)
        raise session_invalid()
    if upstream.status_code != 200:
        raise proxy_error()

    data = parse_now_next(upstream.content, datetime.now(timezone.utc))
    cache.set(key, data, config.epg_ttl)
    return data


_GUIDE_SEARCH_PARAMS = ("q", "mode", "now", "channel", "channelMode", "limit")


def _upstream_message(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error") or "STB-Proxy rejected the request.")
    except ValueError:
        return "STB-Proxy rejected the request."


def _guide_payload(request: Request, session: Session, upstream: httpx.Response):
    """The server guide JSON, passed through unchanged; errors map like /api/epg, plus the
    two client errors (bad query -> 400, out-of-scope channel -> 404) surfaced as such."""
    if upstream.status_code == 401:
        request.app.state.store.delete_hash(session.token_hash)
        raise session_invalid()
    if upstream.status_code == 400:
        raise ApiError(400, "bad_request", _upstream_message(upstream))
    if upstream.status_code == 404:
        raise not_found(_upstream_message(upstream))
    if upstream.status_code != 200:
        raise proxy_error()
    try:
        return upstream.json()
    except ValueError:
        raise proxy_error()


@app.get("/api/guide/search")
async def guide_search(request: Request):
    """Proxy the account-scoped guide search; uncached (query-specific, the server is warm)."""
    session = _get_session(request)
    params = {key: request.query_params[key] for key in _GUIDE_SEARCH_PARAMS if key in request.query_params}

    client: httpx.AsyncClient = request.app.state.client
    try:
        upstream = await client.get("/api/guide/search", params=params, auth=_basic(request, session))
    except httpx.HTTPError:
        raise proxy_unreachable()
    return _guide_payload(request, session, upstream)


@app.get("/api/guide/channel")
async def guide_channel(request: Request):
    """Proxy one channel's timeline, cached per account+channel; refresh=1 bypasses."""
    session = _get_session(request)
    portal = request.query_params.get("portal", "")
    channel_id = request.query_params.get("channelId", "")
    cache: TTLCache = request.app.state.guide_cache
    key = ("guide-channel", session.username, portal, channel_id)
    if request.query_params.get("refresh") not in ("1", "true"):
        cached = cache.get(key)
        if cached is not None:
            return cached

    client: httpx.AsyncClient = request.app.state.client
    try:
        upstream = await client.get(
            "/api/guide/channel",
            params={"portal": portal, "channelId": channel_id},
            auth=_basic(request, session),
        )
    except httpx.HTTPError:
        raise proxy_unreachable()
    data = _guide_payload(request, session, upstream)
    cache.set(key, data, config.guide_ttl)
    return data


@app.get("/stream/{portal}/{channel_id}")
async def stream(portal: str, channel_id: str, request: Request):
    token = request.cookies.get(config.cookie_name)
    session = request.app.state.store.peek(token) if token else None
    if session is None:
        raise unauthorized()

    client: httpx.AsyncClient = request.app.state.client
    upstream_request = client.build_request(
        "GET",
        f"/play/{portal}/{channel_id}",
        headers={"Accept-Encoding": "identity"},
    )
    try:
        upstream = await client.send(upstream_request, stream=True, auth=_basic(request, session))
    except httpx.HTTPError:
        raise proxy_unreachable()

    if upstream.status_code == 503:
        await upstream.aclose()
        raise all_tuners_busy()
    if upstream.status_code == 404:
        await upstream.aclose()
        raise not_found()
    if upstream.status_code == 401:
        await upstream.aclose()
        request.app.state.store.delete_hash(session.token_hash)
        raise session_invalid()
    if upstream.status_code >= 400:
        await upstream.aclose()
        raise proxy_error()

    content_type = upstream.headers.get("content-type", "application/octet-stream")

    async def body():
        try:
            async for chunk in upstream.aiter_raw(65536):
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        body(),
        status_code=200,
        headers={
            "Content-Type": content_type,
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


_HLS_NAME = re.compile(r"^(index\.m3u8|init\.mp4|seg\d+\.m4s)$")
_HLS_VARIANTS = {"copy": False, "transcode": True}


@app.get("/hls/{portal}/{channel_id}/{variant}/{session}/{name}")
async def hls(portal: str, channel_id: str, variant: str, session: str, name: str, request: Request):
    """The HLS fallback: ffmpeg remuxes the channel; hls.js plays the playlist.

    ``copy`` repackages the TS; ``transcode`` re-encodes the video for streams
    whose bitstream the browser's hardware decoder rejects. ``session`` scopes one
    playback, so a stopped stream is not silently restarted when the player retries.
    """
    auth = _get_session(request)
    manager: HlsManager | None = request.app.state.hls
    if manager is None or variant not in _HLS_VARIANTS or not _HLS_NAME.match(name):
        raise not_found("Not found.")

    try:
        directory = manager.playlist_dir(
            portal,
            channel_id,
            *_basic(request, auth),
            transcode=_HLS_VARIANTS[variant],
            session=session,
        )
    except FileNotFoundError:
        raise proxy_error()
    if directory is None:
        raise not_found("Stream ended.")

    path = directory / name
    if name == "index.m3u8":
        for _ in range(50):  # wait up to ~10s for ffmpeg to write the first playlist
            if path.is_file():
                break
            await asyncio.sleep(0.2)
    if not path.is_file():
        raise not_found("Stream not ready.")

    media_type = "application/vnd.apple.mpegurl" if name.endswith(".m3u8") else "video/mp4"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.delete("/hls/{portal}/{channel_id}/{variant}/{session}")
async def hls_stop(portal: str, channel_id: str, variant: str, session: str, request: Request):
    """The player left: end this HLS session now so its ffmpeg and tuner are freed."""
    _get_session(request)
    manager: HlsManager | None = request.app.state.hls
    if manager is not None and variant in _HLS_VARIANTS:
        manager.stop(portal, channel_id, _HLS_VARIANTS[variant], session)
    return {"ok": True}


@app.get("/companion.apk")
async def companion_apk(request: Request):
    """The Android companion app, proxied from STB-Proxy's /static so the browser can grab it.

    STB-Proxy itself is not reachable from the browser, so this streams the APK the
    operator dropped in its static folder, named for a clean download. Public (no
    session): the login page offers it, and the app needs credentials anyway.
    """
    client: httpx.AsyncClient = request.app.state.client
    upstream_request = client.build_request("GET", "/static/STB-Proxy-Companion.apk")
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError:
        raise proxy_unreachable()
    if upstream.status_code != 200:
        await upstream.aclose()
        raise not_found("The companion app isn't available.")

    async def body():
        try:
            async for chunk in upstream.aiter_raw(65536):
                yield chunk
        finally:
            await upstream.aclose()

    headers = {
        "Content-Type": "application/vnd.android.package-archive",
        "Content-Disposition": 'attachment; filename="STB-Proxy-Companion.apk"',
        "Cache-Control": "no-store",
    }
    length = upstream.headers.get("content-length")
    if length:
        headers["Content-Length"] = length
    return StreamingResponse(body(), status_code=200, headers=headers)


async def _hls_reap_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(5)
        manager: HlsManager | None = getattr(app.state, "hls", None)
        if manager is not None:
            manager.reap()


async def _revalidate_loop(app: FastAPI) -> None:
    store: SessionStore = app.state.store
    client: httpx.AsyncClient = app.state.client
    while True:
        await asyncio.sleep(config.revalidate)
        try:
            store.purge_expired()
            for session in store.all_valid():
                try:
                    auth = session.basic(store.fernet)
                except Exception:
                    store.delete_hash(session.token_hash)
                    continue
                try:
                    response = await client.get("/api/lineup", auth=auth)
                except httpx.HTTPError:
                    continue  # proxy down: keep sessions, retry next pass
                if response.status_code == 401:
                    logger.info("dropping revoked session for %s", session.username)
                    store.delete_hash(session.token_hash)
        except Exception:
            logger.exception("session revalidation pass failed")


def _mount_spa() -> None:
    dist: Path = config.static_dir
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path.startswith(("api/", "stream/", "hls/")):
            raise not_found("Not found.")
        if path:
            candidate = (dist / path).resolve()
            try:
                candidate.relative_to(dist.resolve())
            except ValueError:
                raise not_found("Not found.")
            if candidate.is_file():
                return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise not_found("The web client is not built yet.")


_mount_spa()
