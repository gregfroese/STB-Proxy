"""On Demand sessions (ADR 0005): one viewer's playback of one Movie or Episode, as HLS
passed through STB-Proxy. No Flask here; app.py admits sessions, mints their links and
serves them.

A session holds one portal link, minted once. Its master and media playlists are rewritten
so that every URI is a bare name, relative to the session's own URL, and each name maps to
the upstream URL server-side: storage hosts and tokens never reach a client. Segments are
streamed a chunk at a time, never held whole.

A session never re-mints. An upstream 403 (on the user's portal: a newer session on the
MAC evicted it) or any other upstream failure ends it, and from then on every request
gets Ended with its reason: "evicted", "idle" (IDLE seconds with no request) or "stopped"
(the viewer, the operator, or a session that replaced it).
"""
import logging
import posixpath
import re
import secrets
import threading
import time
from urllib.parse import urljoin, urlparse, urlunparse

import requests

logger = logging.getLogger("STB-Proxy")

IDLE = 120  # seconds with no request before a session ends and frees its slot
KEEP_ENDED = 3600  # seconds an ended session still answers 410 (then 404)
CHUNK = 65536
PLAYLIST_MAX = 4 * 1024 * 1024  # a 3-hour VOD media playlist is well under 1 MB
TIMEOUT = (10, 60)
MASTER = "master.m3u8"
PLAYLIST_TYPE = "application/vnd.apple.mpegurl"
# Tags whose URI attribute names another playlist; any other URI is a resource (a segment,
# a key, an init section) passed through as it is.
PLAYLIST_TAGS = ("#EXT-X-MEDIA:", "#EXT-X-I-FRAME-STREAM-INF:")
AD_TYPES = ("vclub_ad", "advert")


class Ended(Exception):
    """The session ended; `reason` is "evicted", "idle" or "stopped"."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class NotHls(Exception):
    """The link isn't an HLS playlist (v1 plays HLS only)."""


class UpstreamError(Exception):
    """The portal or its storage failed."""


class Denied(Exception):
    """The portal won't play this item for the MAC (access_denied and the like)."""


def linkFrom(js, portalUrl):
    """The playable URL in a type=vod create_link `js`, resolved against the portal.

    `js` is an object {cmd, error}, a list with ads first (the film is the entry that isn't
    an ad), or a bare string (research 01). cmd may carry a "solution" prefix ("ffmpeg
    http://..."), be relative to the portal, or name localhost. Raises Denied when the
    portal refuses the item, UpstreamError when it fails."""
    if isinstance(js, list):
        films = [entry for entry in js if isinstance(entry, dict) and entry.get("media_type") not in AD_TYPES]
        js = films[-1] if films else None
    if isinstance(js, dict):
        error = js.get("error") or ""
        if error in ("access_denied", "nothing_to_play", "player_file_missing"):
            raise Denied(error)
        if error:
            raise UpstreamError(error)
        cmd = js.get("cmd")
    elif isinstance(js, str):
        cmd = js
    else:
        raise UpstreamError("create_link answered {!r}".format(js))
    link = str(cmd or "").strip().split(" ")[-1]
    if not link:
        raise UpstreamError("create_link gave no link")
    return resolve(link, portalUrl)


def resolve(link, portalUrl):
    """A link the portal gave relative to itself, or on localhost, made absolute."""
    portal = urlparse(portalUrl)
    if "://" not in link:
        return urljoin(portalUrl, link)
    parsed = urlparse(link)
    if parsed.hostname in ("localhost", "127.0.0.1") and portal.hostname not in ("localhost", "127.0.0.1"):
        netloc = portal.hostname + (":{}".format(parsed.port) if parsed.port else "")
        return urlunparse(parsed._replace(netloc=netloc))
    return link


def isMaster(text):
    return "#EXT-X-STREAM-INF" in text


def duration(text):
    """A VOD media playlist's length in whole seconds, or None if it isn't one."""
    if "#EXT-X-ENDLIST" not in text:
        return None
    total = 0.0
    for found in re.finditer(r"^#EXTINF:\s*([0-9.]+)", text, re.MULTILINE):
        total += float(found.group(1))
    return round(total)


class Session:
    """One On Demand session. app.py owns its slot: `onEnd` frees it, once."""

    def __init__(self, sid, account, portal, mac, title, proxy=None, headers=None, onEnd=None,
                 clock=time.time):
        self.sid = sid
        self.account = account
        self.portal = portal
        self.mac = mac
        self.title = title
        self.proxy = proxy
        self.headers = dict(headers or {})
        self.onEnd = onEnd
        self.clock = clock
        self.lastSeen = clock()
        self.reason = None  # why it ended, or None while it plays
        self.endedAt = None
        self.lock = threading.Lock()
        self.urls = {}  # name -> upstream URL
        self.names = {}  # upstream URL -> name
        self.playlistNames = set()
        self.cache = {}  # name -> rewritten VOD playlist (they never change)
        self.http = requests.Session()
        if proxy:
            self.http.proxies = {"http": proxy, "https": proxy}

    # Lifecycle

    def end(self, reason):
        """End the session for `reason` and free its slot. Only the first reason counts."""
        with self.lock:
            if self.reason is not None:
                return
            self.reason = reason
            self.endedAt = self.clock()
        logger.info("On Demand session of {} ({}) ended: {}".format(self.account, self.title, reason))
        try:
            self.http.close()
        except Exception:
            pass
        if self.onEnd is not None:
            self.onEnd()

    def check(self):
        """Raise Ended if the session is over; otherwise count this as a request."""
        if self.reason is not None:
            raise Ended(self.reason)
        self.lastSeen = self.clock()

    def idle(self):
        return self.reason is None and self.clock() - self.lastSeen >= IDLE

    # Playlists

    def open(self, link):
        """The first fetch: follow the minted link, check it is HLS and keep its rewritten
        master (and the first variant's media playlist, for the length). Returns the
        length in seconds, or None. Raises NotHls or UpstreamError."""
        self.urls[MASTER] = link
        self.playlistNames.add(MASTER)
        text = self.fetchPlaylist(MASTER)
        if isMaster(text):
            variant = next((line for line in text.splitlines() if line and not line.startswith("#")), None)
            if variant is None:
                return None
            return duration(self.fetchPlaylist(variant))
        return duration(text)

    def playlist(self, name):
        """A playlist of this session, rewritten. Raises Ended, or KeyError for an unknown
        name."""
        self.check()
        if name not in self.playlistNames:
            raise KeyError(name)
        cached = self.cache.get(name)
        if cached is not None:
            return cached
        try:
            return self.fetchPlaylist(name)
        except (UpstreamError, NotHls) as e:
            logger.info("On Demand session of {}: playlist failed ({})".format(self.account, e))
            self.end("evicted")
            raise Ended(self.reason)

    def fetchPlaylist(self, name):
        try:
            response = self.http.get(self.urls[name], headers=self.headers, stream=True, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise UpstreamError(str(e))
        try:
            if response.status_code != 200:
                raise UpstreamError("HTTP {}".format(response.status_code))
            # Judge by the first bytes, so a progressive file is never read past one chunk.
            body, checked = b"", False
            for chunk in response.iter_content(CHUNK):
                body += chunk
                head = body.lstrip(b"\xef\xbb\xbf \t\r\n")
                if not checked and len(head) >= len(b"#EXTM3U"):
                    if not head.startswith(b"#EXTM3U"):
                        raise NotHls(response.headers.get("Content-Type"))
                    checked = True
                if len(body) > PLAYLIST_MAX:
                    raise UpstreamError("playlist too large")
            if not checked:
                raise NotHls(response.headers.get("Content-Type"))
            base = response.url  # after redirects: relative URIs are relative to this
        except requests.RequestException as e:
            raise UpstreamError(str(e))
        finally:
            response.close()
        text = self.rewrite(body.decode("utf-8", "replace"), base)
        if isMaster(text) or "#EXT-X-ENDLIST" in text:
            self.cache[name] = text
        return text

    def rewrite(self, text, base):
        """Every URI in a playlist (a URI line or a URI="..." attribute) swapped for a
        bare name that maps to the absolute upstream URL."""
        lines, nextIsPlaylist = [], False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                playlist = stripped.startswith(PLAYLIST_TAGS)
                line = re.sub(r'URI="([^"]*)"',
                              lambda m: 'URI="{}"'.format(self.nameFor(urljoin(base, m.group(1)), playlist)), line)
                if stripped.startswith("#EXT"):  # a plain comment doesn't break the pair
                    nextIsPlaylist = stripped.startswith("#EXT-X-STREAM-INF")
            elif stripped:
                line = self.nameFor(urljoin(base, stripped), nextIsPlaylist)
                nextIsPlaylist = False
            lines.append(line)
        return "\n".join(lines) + "\n"

    def nameFor(self, url, playlist):
        with self.lock:
            name = self.names.get(url)
            if name is None:
                if playlist:
                    name = "v{}.m3u8".format(len(self.names))
                else:
                    ext = posixpath.splitext(urlparse(url).path)[1]
                    name = "s{}{}".format(len(self.names), ext if re.fullmatch(r"\.[A-Za-z0-9]{1,5}", ext) else "")
                self.names[url] = name
                self.urls[name] = url
                if playlist:
                    self.playlistNames.add(name)
            return name

    # Segments

    def segment(self, name, range=None):
        """Open a segment (or key, or init section): (status, headers, chunks). The chunks
        stream from upstream as they arrive. Raises Ended, or KeyError for an unknown name."""
        self.check()
        if name in self.playlistNames or name not in self.urls:
            raise KeyError(name)
        headers = dict(self.headers, **{"Accept-Encoding": "identity"})
        if range:
            headers["Range"] = range
        try:
            response = self.http.get(self.urls[name], headers=headers, stream=True, timeout=TIMEOUT)
        except requests.RequestException as e:
            logger.info("On Demand session of {}: segment failed ({})".format(self.account, e))
            self.end("evicted")
            raise Ended(self.reason)
        if response.status_code not in (200, 206, 416):
            response.close()
            logger.info("On Demand session of {}: segment got HTTP {}".format(self.account, response.status_code))
            self.end("evicted")
            raise Ended(self.reason)
        passed = {k: response.headers[k] for k in ("Content-Type", "Content-Length", "Content-Range")
                  if k in response.headers}
        if "Content-Encoding" in response.headers:
            passed.pop("Content-Length", None)  # requests decodes it, so the length changes
        return response.status_code, passed, self.chunks(response)

    def chunks(self, response):
        try:
            for chunk in response.iter_content(CHUNK):
                if self.reason is not None:
                    return  # stopped meanwhile
                self.lastSeen = self.clock()
                yield chunk
        except Exception as e:
            if self.reason is None:  # not just closed under it by end()
                logger.info("On Demand session of {}: segment broke off ({})".format(self.account, e))
                self.end("evicted")
        finally:
            response.close()
            self.lastSeen = self.clock()


class Sessions:
    """Every On Demand session, by sid, with ended ones kept KEEP_ENDED seconds so their
    viewers learn why (410)."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.sessions = {}
        self.lock = threading.Lock()

    def new(self, account, portal, mac, title, **kwargs):
        sid = secrets.token_urlsafe(24)
        session = Session(sid, account, portal, mac, title, clock=lambda: self.clock(), **kwargs)
        with self.lock:
            self.sessions[sid] = session
        return session

    def discard(self, session):
        """Forget a session that never started playing."""
        with self.lock:
            self.sessions.pop(session.sid, None)

    def find(self, sid, account):
        """The session `sid` of `account` (ended or not), else None."""
        self.sweep()
        session = self.sessions.get(sid) if isinstance(sid, str) else None
        if session is None or session.account != account:
            return None
        return session

    def playing(self):
        return [s for s in list(self.sessions.values()) if s.reason is None]

    def sweep(self):
        """End sessions idle for IDLE seconds, and forget ones ended KEEP_ENDED ago."""
        now = self.clock()
        for session in list(self.sessions.values()):
            if session.idle():
                session.end("idle")
            elif session.reason is not None and now - session.endedAt >= KEEP_ENDED:
                with self.lock:
                    self.sessions.pop(session.sid, None)
