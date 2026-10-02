"""Keep a Plex DVR's channel map in step with STB-Proxy's lineup."""
import requests

TIMEOUT = 30


class PlexSyncError(Exception):
    pass


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
        raise PlexSyncError("Plex rejected the token (HTTP 401)")
    if not 200 <= response.status_code < 300:
        raise PlexSyncError(
            "Plex returned HTTP {} for {} {}".format(response.status_code, method, path)
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
    dvrKey, deviceKey = findDvr(plexUrl, token, tunerUri)
    call(
        "PUT",
        plexUrl,
        "/media/grabbers/devices/{}/channelmap".format(deviceKey),
        token,
        channelMapParams(lineupEntries),
    )
    call("POST", plexUrl, "/livetv/dvrs/{}/reloadGuide".format(dvrKey), token)
    return "Plex updated: {} channels enabled".format(len(lineupEntries))
