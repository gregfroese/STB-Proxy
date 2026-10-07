"""Keep Jellyfin's Live TV in step with STB-Proxy's lineup.

Jellyfin reads STB-Proxy as an M3U tuner (/playlist) with an XMLTV guide (/xmltv). When
the lineup changes, its "Refresh Guide" task re-reads both, so channels come and go.
"""
import json as jsonlib

import requests

TIMEOUT = 30
REFRESH_TASK = "RefreshGuide"


class JellyfinError(Exception):
    def __init__(self, message, retry=True):
        super().__init__(message)
        self.retry = retry  # False when trying again can't help


def call(method, jellyfinUrl, path, apiKey, json=None, params=None):
    jellyfinUrl = jellyfinUrl.rstrip("/")
    try:
        response = requests.request(
            method,
            jellyfinUrl + path,
            json=json,
            params=params,
            headers={
                "Authorization": 'MediaBrowser Client="STB-Proxy", Token="{}"'.format(apiKey),
                "Accept": "application/json",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise JellyfinError("couldn't reach Jellyfin at {} ({})".format(jellyfinUrl, e.__class__.__name__))
    if response.status_code in (401, 403):
        raise JellyfinError("Jellyfin rejected the API key (HTTP {})".format(response.status_code), retry=False)
    if not 200 <= response.status_code < 300:
        raise JellyfinError("Jellyfin returned HTTP {} for {} {}".format(response.status_code, method, path),
                            retry=response.status_code >= 500)
    return response


def reply(response):
    # Jellyfin may start JSON with a byte-order mark.
    return jsonlib.loads(response.content.decode("utf-8-sig"))


def liveTvConfig(jellyfinUrl, apiKey):
    try:
        return reply(call("GET", jellyfinUrl, "/System/Configuration/livetv", apiKey))
    except ValueError:
        raise JellyfinError("unexpected reply from Jellyfin when reading its Live TV settings")


def ours(url, stbBase):
    return str(url or "").rstrip("/").startswith(stbBase.rstrip("/"))


def status(jellyfinUrl, apiKey, stbBase):
    """Whether Jellyfin has STB-Proxy as a tuner and as a guide."""
    config = liveTvConfig(jellyfinUrl, apiKey)
    return {
        "tuner": any(ours(t.get("Url"), stbBase) for t in config.get("TunerHosts") or []),
        "guide": any(ours(p.get("Path"), stbBase) for p in config.get("ListingProviders") or []),
    }


def setup(jellyfinUrl, apiKey, stbBase, tunerCount=0):
    """Make Jellyfin use STB-Proxy as an M3U tuner and an XMLTV guide. Returns a message.

    Adds whichever is missing. tunerCount is Jellyfin's own limit on streams from the
    tuner; 0 (no limit) is best, since STB-Proxy already knows how many streams each
    portal account allows, and a stream Jellyfin wrongly thinks is still open can't then
    block playback. An existing STB-Proxy tuner with another limit is changed to this one.
    """
    config = liveTvConfig(jellyfinUrl, apiKey)
    stbBase = stbBase.rstrip("/")
    tuner = next((t for t in config.get("TunerHosts") or [] if ours(t.get("Url"), stbBase)), None)
    changes = []
    if tuner is None:
        call("POST", jellyfinUrl, "/LiveTv/TunerHosts", apiKey, json={
            "Type": "m3u",
            "Url": stbBase + "/playlist",
            "FriendlyName": "STB-Proxy",
            "TunerCount": tunerCount,
            "ImportFavoritesOnly": False,
            "AllowHWTranscoding": True,
            "AllowFmp4TranscodingContainer": False,
            "AllowStreamSharing": True,
            "EnableStreamLooping": False,
            "IgnoreDts": True,
        })
        changes.append("added the tuner ({}/playlist)".format(stbBase))
    elif int(tuner.get("TunerCount") or 0) != tunerCount:
        # Same Id: Jellyfin updates the tuner rather than adding another.
        call("POST", jellyfinUrl, "/LiveTv/TunerHosts", apiKey, json=dict(tuner, TunerCount=tunerCount))
        changes.append("set the tuner's stream limit to {}".format("none" if tunerCount == 0 else tunerCount))
    if not any(ours(p.get("Path"), stbBase) for p in config.get("ListingProviders") or []):
        call("POST", jellyfinUrl, "/LiveTv/ListingProviders", apiKey,
             params={"validateListings": "false", "validateLogin": "false"},
             json={"Type": "xmltv", "Path": stbBase + "/xmltv", "EnableAllTuners": True})
        changes.append("added the guide ({}/xmltv)".format(stbBase))
    refresh(jellyfinUrl, apiKey)
    if not changes:
        return "Jellyfin already has STB-Proxy as a tuner and guide; it's reloading the channels and guide"
    return "Jellyfin Live TV: " + " and ".join(changes) + "; it's loading the channels and guide"


def refresh(jellyfinUrl, apiKey):
    """Run Jellyfin's Refresh Guide task, which re-reads the tuner's channels and the guide."""
    try:
        tasks = reply(call("GET", jellyfinUrl, "/ScheduledTasks", apiKey))
    except ValueError:
        raise JellyfinError("unexpected reply from Jellyfin when listing its tasks")
    task = next((t for t in tasks if t.get("Key") == REFRESH_TASK), None)
    if not task:
        raise JellyfinError("Jellyfin has no Refresh Guide task (is Live TV set up?)")
    if task.get("State") == "Running":
        # It may already have read the old lineup: start it again so it sees the new one.
        call("DELETE", jellyfinUrl, "/ScheduledTasks/Running/" + task["Id"], apiKey)
    call("POST", jellyfinUrl, "/ScheduledTasks/Running/" + task["Id"], apiKey)
    return "Jellyfin is refreshing its channels and guide"
