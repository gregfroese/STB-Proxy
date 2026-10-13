"""HLS fallback (spec 2.7): remux a live channel to HLS with ffmpeg so browsers
whose TS demuxer (mpegts.js) mishandles certain streams (e.g. B-frame-heavy
1080p60) can play it with hls.js.

One ffmpeg process per active (portal, channel); reaped after an idle TTL.
"""

from __future__ import annotations

import base64
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger("stbweb.hls")


class HlsManager:
    def __init__(self, base_dir: str, proxy_url: str, ttl: int, ffmpeg_bin: str = "ffmpeg") -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.proxy_url = proxy_url.rstrip("/")
        self.ttl = ttl
        self.ffmpeg = ffmpeg_bin
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def playlist_dir(
        self,
        portal: str,
        channel_id: str,
        user: str,
        password: str,
        transcode: bool = False,
        session: str = "default",
    ) -> Path | None:
        """Return the directory holding this channel's live playlist, starting ffmpeg if needed.

        ``transcode`` re-encodes the video (for streams whose H.264 bitstream the
        browser's hardware decoder rejects); otherwise the stream is copied.

        ``session`` identifies one playback attempt. If that session's ffmpeg has
        exited (e.g. the operator stopped the stream), return None instead of
        restarting it, so a live player that retries gives up rather than
        silently reconnecting. A new playback uses a new session.
        """
        key = f"{portal}__{channel_id}__{'t' if transcode else 'c'}__{session}"
        now = time.time()
        with self._lock:
            session_state = self._sessions.get(key)
            if session_state is not None:
                if session_state["proc"].poll() is None:
                    session_state["last"] = now
                    return Path(session_state["dir"])
                return None  # it ended: don't reconnect this playback

            directory = self.base / key
            shutil.rmtree(directory, ignore_errors=True)
            directory.mkdir(parents=True, exist_ok=True)
            token = base64.b64encode(f"{user}:{password}".encode()).decode()
            command = [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "warning",
                "-headers",
                f"Authorization: Basic {token}\r\n",
                "-i",
                f"{self.proxy_url}/play/{portal}/{channel_id}",
            ]
            if transcode:
                # Re-encode video (conformant bitstream, monotonic timestamps) and
                # audio (codec-agnostic), so the browser hardware decoder is happy.
                command += [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-tune",
                    "zerolatency",
                    "-g",
                    "50",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                ]
            else:
                command += ["-c", "copy", "-bsf:a", "aac_adtstoasc"]
            command += [
                "-f",
                "hls",
                "-hls_time",
                "2",
                "-hls_list_size",
                "5",
                "-hls_flags",
                "delete_segments+omit_endlist+independent_segments",
                "-hls_segment_type",
                "fmp4",
                "-hls_fmp4_init_filename",
                "init.mp4",
                "-hls_segment_filename",
                str(directory / "seg%05d.m4s"),
                str(directory / "index.m3u8"),
            ]
            try:
                proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                logger.error("ffmpeg not found at %s; HLS fallback unavailable", self.ffmpeg)
                raise
            self._sessions[key] = {
                "proc": proc,
                "dir": str(directory),
                "last": now,
            }
            logger.info("started HLS remux for %s (transcode=%s, pid %s)", key, transcode, proc.pid)
            return directory

    def reap(self) -> None:
        """Drop sessions nobody has asked for within the TTL (including ones whose ffmpeg
        has exited, so a stopped stream stays stopped until the viewer moves on)."""
        now = time.time()
        with self._lock:
            for key in list(self._sessions):
                if now - self._sessions[key]["last"] > self.ttl:
                    self._cleanup_locked(key)

    def shutdown(self) -> None:
        with self._lock:
            for key in list(self._sessions):
                self._cleanup_locked(key)

    def _cleanup_locked(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session is None:
            return
        try:
            session["proc"].kill()
        except Exception:
            pass
        shutil.rmtree(session["dir"], ignore_errors=True)
        logger.info("stopped HLS remux for %s", key)
