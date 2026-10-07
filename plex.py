"""Keep a Plex DVR's channel map in step with STB-Proxy's lineup."""
import requests

from urllib.parse import urlencode

TIMEOUT = 30
# Plex stops reading a request after 32 KB (and answers 400), and it only takes the channel
# map in the URL, as two parameters per channel. Leave room for the rest of the request line.
MAX_QUERY = 32000


class PlexSyncError(Exception):
    def __init__(self, message, retry=True):
        super().__init__(message)
        self.retry = retry  # False when trying again can't help


def call(method, plexUrl, path, token, params=None):
    plexUrl = plexUrl.rstrip("/")
    try:
        response = requests.request(
            method,
            plexUrl + path,
            params=params,
            headers={"X-Plex-Token": token, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise PlexSyncError(
            "couldn't reach Plex at {} ({})".format(plexUrl, e.__class__.__name__)
        )
    if response.status_code == 401:
        raise PlexSyncError("Plex rejected the token (HTTP 401)", retry=False)
    if not 200 <= response.status_code < 300:
        raise PlexSyncError(
            "Plex returned HTTP {} for {} {}".format(response.status_code, method, path),
            retry=response.status_code >= 500,
        )
    return response


def findDvr(plexUrl, token, tunerUri):
    """(dvrKey, deviceKey) of the Plex DVR whose tuner is at tunerUri."""
    reply = call("GET", plexUrl, "/livetv/dvrs", token)
    try:
        dvrs = reply.json()["MediaContainer"].get("Dvr", [])
    except (ValueError, KeyError, AttributeError):
        raise PlexSyncError("unexpected reply from Plex when listing DVRs")
    for dvr in dvrs:
        for device in dvr.get("Device", []):
            if device.get("uri", "").rstrip("/") == tunerUri.rstrip("/"):
                return dvr["key"], device["key"]
    raise PlexSyncError("no Plex DVR uses this tuner ({})".format(tunerUri))


def channelMapParams(lineupEntries):
    params = []
    for entry in lineupEntries:
        params.append(("channelMappingByKey[{}]".format(entry["GuideNumber"]), entry["epgId"]))
        params.append(("channelMapping[{}]".format(entry["GuideNumber"]), entry["epgId"]))
    params.append(("channelsEnabled", ",".join(e["GuideNumber"] for e in lineupEntries)))
    return params


def sync(plexUrl, token, tunerUri, lineupEntries):
    """Map and enable exactly lineupEntries in Plex, then reload its guide.

    Plex drops channels missing from the map, so lineupEntries must be the
    complete set of available channels.
    """
    if not lineupEntries:
        raise PlexSyncError("no channels are available, so Plex was left unchanged")
    params = channelMapParams(lineupEntries)
    size = len(urlencode(params))
    if size > MAX_QUERY:
        perChannel = size / len(lineupEntries)
        raise PlexSyncError(
            "Plex can take about {} channels in one update and the lineup has {}. Switch off a block, "
            "or shorten long EPG IDs set in the Playlist Editor".format(int(MAX_QUERY / perChannel), len(lineupEntries)),
            retry=False,
        )
    dvrKey, deviceKey = findDvr(plexUrl, token, tunerUri)
    call(
        "PUT",
        plexUrl,
        "/media/grabbers/devices/{}/channelmap".format(deviceKey),
        token,
        params,
    )
    call("POST", plexUrl, "/livetv/dvrs/{}/reloadGuide".format(dvrKey), token)
    return "Plex updated: {} channels enabled".format(len(lineupEntries))
