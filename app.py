import flask
import stb
import availability
import plex
import jellyfin
import guide
import logos
import recordings
import os
import shutil
import json
import subprocess
import uuid
import logging
import re
import queue
import threading
import time
import requests
from urllib.parse import urlparse
import xml.etree.cElementTree as ET
from flask import (
    Flask,
    render_template,
    redirect,
    request,
    Response,
    make_response,
    flash,
)
from datetime import datetime, timezone
from functools import wraps
import secrets
import waitress

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)

logger = logging.getLogger("STB-Proxy")
logger.setLevel(logging.INFO)
logFormat = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
fileHandler = logging.FileHandler("STB-Proxy.log")
fileHandler.setFormatter(logFormat)
logger.addHandler(fileHandler)
consoleFormat = logging.Formatter("[%(levelname)s] %(message)s")
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(consoleFormat)
logger.addHandler(consoleHandler)

basePath = os.path.abspath(os.getcwd())

if os.getenv("HOST"):
    host = os.getenv("HOST")
else:
    host = "localhost:8001"

if os.getenv("CONFIG"):
    configFile = os.getenv("CONFIG")
else:
    configFile = os.path.join(basePath, "config.json")

occupied = {}
# The browser preview each tile is watching, by (viewer id, tile id), so a new channel in
# that tile can stop it at once instead of waiting for its connection to close. The preview
# player is tile "player"; Multiview's tiles are "t0" to "t8".
previews = {}
config = {}

d_ffmpegcmd = "ffmpeg -re -http_proxy <proxy> -timeout <timeout> -i <url> -map 0 -codec copy -f mpegts pipe:"

defaultSettings = {
    "stream method": "ffmpeg",
    "ffmpeg command": "ffmpeg -re -http_proxy <proxy> -timeout <timeout> -i <url> -map 0 -codec copy -f mpegts pipe:",
    "ffmpeg timeout": "5",
    "test streams": "true",
    "try all macs": "false",
    "use channel genres": "true",
    "use channel numbers": "true",
    "sort playlist by channel genre": "false",
    "sort playlist by channel number": "false",
    "sort playlist by channel name": "false",
    "enable security": "false",
    "username": "admin",
    "password": "12345",
    "enable hdhr": "false",
    "hdhr name": "STB-Proxy",
    "hdhr id": str(uuid.uuid4().hex),
    "hdhr tuners": "1",
    "plex url": "",
    "plex token": "",
    "api token": "",
    "jellyfin url": "",
    "jellyfin api key": "",
    "recordings folder": "",
}

defaultPortal = {
    "enabled": "true",
    "name": "",
    "url": "",
    "macs": {},
    "streams per mac": "1",
    "proxy": "",
    "enabled channels": [],
    "custom channel names": {},
    "custom channel numbers": {},
    "custom genres": {},
    "custom epg ids": {},
    "fallback channels": {},
    "custom logos": {},
    "logos": "portal",
    "channel blocks": {},
    "dead channels": [],
    "favourite channels": [],
}


configLock = threading.Lock()


def writeConfig(data):
    """Write to a temporary file and swap it in, so a crash mid-write leaves the old config intact."""
    with configLock:
        tmp = configFile + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, configFile)


def defaultEpgId(portal, channelId):
    # Short on purpose: Plex takes its whole channel map in one URL of at most 32 KB, and
    # each channel's id appears in it twice. Six characters of the portal id keep it unique.
    return "{}.{}".format(portal[:6], channelId)


def previewLink(portal, channelId):
    # Relative, so the browser plays it from whatever address it's using: the LAN, or a
    # reverse proxy (with its login and HTTPS). Plex and players get full links built from HOST.
    return "/play/{}/{}?web=true".format(portal, channelId)


def loadConfig():
    if os.path.exists(configFile):
        try:
            with open(configFile) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            # Never replace a config we can't read: it holds every portal and edit.
            logger.critical(
                "Can't read config {} ({}). Not starting, so it isn't overwritten. "
                "Fix or restore it, then restart.".format(configFile, e)
            )
            raise SystemExit(1)
    else:
        logger.warning("No existing config found. Creating a new one")
        data = {}

    data.setdefault("portals", {})
    data.setdefault("settings", {})
    data.setdefault("blocks", {})
    data.setdefault("saved filters", {})
    if not isinstance(data.get("block favourites"), dict):
        data["block favourites"] = {}
    if not isinstance(data.get("hidden blocks"), list):
        data["hidden blocks"] = []

    settings = data["settings"]
    settingsOut = {}

    for setting, default in defaultSettings.items():
        value = settings.get(setting)
        if not value or type(default) != type(value):
            value = default
        settingsOut[setting] = value

    if not settingsOut["api token"]:
        settingsOut["api token"] = secrets.token_urlsafe(24)
    data["settings"] = settingsOut

    portals = data["portals"]
    portalsOut = {}

    for portal in portals:
        portalsOut[portal] = {}
        for setting, default in defaultPortal.items():
            value = portals[portal].get(setting)
            if not value or type(default) != type(value):
                value = default
            portalsOut[portal][setting] = value
        portalsOut[portal]["channel blocks"] = availability.normaliseChannelBlocks(
            portalsOut[portal]["channel blocks"]
        )
        if portalsOut[portal]["logos"] not in LOGO_SOURCES:
            portalsOut[portal]["logos"] = defaultPortal["logos"]
        if "logos" not in portals[portal] and settings.get("match logos") == "false":
            # Looking logos up used to be one switch in Settings, for every portal.
            portalsOut[portal]["logos"] = "portal only"

    data["portals"] = portalsOut

    writeConfig(data)

    return data


def getPortals():
    return config["portals"]


def savePortals(portals):
    config["portals"] = portals
    writeConfig(config)


def getSettings():
    return config["settings"]


def saveSettings(settings):
    config["settings"] = settings
    writeConfig(config)


def getSavedFilters():
    return config.setdefault("saved filters", {})


def saveSavedFilters(saved):
    config["saved filters"] = saved
    writeConfig(config)


def getBlocks():
    return config["blocks"]


def saveBlocks(blocks):
    config["blocks"] = blocks
    names = availability.blockNames(getPortals())
    config["hidden blocks"] = [name for name in getHiddenBlocks() if name in names]
    config["block favourites"] = pruneBlockFavourites(getPortals(), getBlockFavourites())
    writeConfig(config)


def getBlockFavourites():
    """Favourites within a block, apart from the overall favourites: {block: {portal: [channelId]}}."""
    return config.setdefault("block favourites", {})


def pruneBlockFavourites(portals, favourites):
    """Only channels still in the block (and blocks that still have some)."""
    pruned = {}
    for block, byPortal in favourites.items():
        for portal, channelIds in byPortal.items():
            channelBlocks = portals.get(portal, {}).get("channel blocks", {})
            kept = [c for c in channelIds if block in channelBlocks.get(c, [])]
            if kept:
                pruned.setdefault(block, {})[portal] = kept
    return pruned


def blockFavouritesOf(portal, channelId):
    """The blocks a channel is a favourite in, by name."""
    return sorted(b for b, byPortal in getBlockFavourites().items() if channelId in byPortal.get(portal, []))


# The recorder, made on first use so tests can load the app against their own config.
recorder = None
recorderLock = threading.Lock()


def recordingUrl(portal, channelId, id):
    # A recording reads from /play like Plex does, so it shares streams and tuners.
    return "http://127.0.0.1:8001/play/{}/{}?recording={}".format(portal, channelId, id)


def getRecorder():
    global recorder
    with recorderLock:
        if recorder is None:
            store = recordings.RecordingStore(
                os.path.join(os.path.dirname(os.path.abspath(configFile)), "recordings.json"), logger)
            recorder = recordings.Recorder(
                store, lambda: getSettings().get("recordings folder", "").strip(), recordingUrl, logger)
        return recorder


def getHiddenBlocks():
    """Blocks left out of the API, so integrations such as Home Assistant don't see them."""
    return config.setdefault("hidden blocks", [])


def authorise(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        settings = getSettings()
        security = settings["enable security"]
        username = settings["username"]
        password = settings["password"]
        if (
            security == "false"
            or auth
            and auth.username == username
            and auth.password == password
        ):
            return f(*args, **kwargs)

        return make_response(
            "Could not verify your login!",
            401,
            {"WWW-Authenticate": 'Basic realm="Login Required"'},
        )

    return decorated


def moveMac(portalId, mac):
    portals = getPortals()
    macs = portals[portalId]["macs"]
    x = macs[mac]
    del macs[mac]
    macs[mac] = x
    portals[portalId]["macs"] = macs
    savePortals(portals)


@app.route("/", methods=["GET"])
@authorise
def home():
    return redirect("/portals", code=302)


@app.route("/portals", methods=["GET"])
@authorise
def portals():
    devices = {mac: deviceForForm(details) for mac, details in stb.loadDevices().items()}
    with logoRefreshesLock:
        refreshes = dict(logoRefreshes)
    return render_template("portals.html", portals=getPortals(), devices=devices,
                           logoSources=LOGO_SOURCES, logoRefreshes=refreshes)


# The device details asked for in the portal form, and where each goes in devices.json.
DEVICE_FIELDS = {
    "model": ("profile", "stb_type"),
    "serial": ("profile", "sn"),
    "device id": ("profile", "device_id"),
    "device id2": ("profile", "device_id2"),
    "signature": ("profile", "signature"),
    "timezone": ("cookies", "timezone"),
}


def modelHeader(model):
    return "Model: {}; Link: Ethernet".format(model)


def deviceFromForm(form):
    """The devices.json entry described by the portal form, or (None, why not)."""
    extra = form.get("device extra", "").strip()
    try:
        details = json.loads(extra) if extra else {}
    except ValueError as e:
        return None, "Device lock: the Advanced box isn't valid JSON ({})".format(e)
    if not isinstance(details, dict) or not all(
        isinstance(details.get(section, {}), dict) for section in ("cookies", "headers", "handshake", "profile")
    ):
        return None, 'Device lock: the Advanced box should look like {"headers": {...}, "profile": {...}}'
    for field, (section, key) in DEVICE_FIELDS.items():
        value = form.get("device " + field, "").strip()
        if value:
            details.setdefault(section, {})[key] = value
    model = details.get("profile", {}).get("stb_type")
    if model:
        # What a MAG box sends; portals that check the model often check this too.
        details.setdefault("headers", {}).setdefault("X-User-Agent", modelHeader(model))
    if not details:
        return None, "Device lock is on, but no device details were filled in"
    return details, None


def deviceForForm(details):
    """Split a devices.json entry into the form's fields and the rest (for Advanced)."""
    details = json.loads(json.dumps(details))
    fields = {}
    for field, (section, key) in DEVICE_FIELDS.items():
        value = details.get(section, {}).pop(key, None)
        if value is not None:
            fields[field] = value
    headers = details.get("headers", {})
    if "model" in fields and headers.get("X-User-Agent") == modelHeader(fields["model"]):
        del headers["X-User-Agent"]  # filled in from the model again on save
    extra = {k: v for k, v in details.items() if v != {}}
    return {"fields": fields, "extra": extra}


def applyDeviceForm(form, macs):
    """Save or clear the device details sent with a portal, before its MACs are tested.

    "device state" is "on", "off", or "keep" (the form couldn't show them: leave as is).
    Returns an error message, or None.
    """
    state = form.get("device state", "keep")
    if state == "off":
        for mac in macs:
            stb.removeDevice(mac)
    elif state == "on":
        details, error = deviceFromForm(form)
        if error:
            return error
        for mac in macs:
            stb.saveDevice(mac, details)
    return None


def formMacs(form):
    macs = []
    for mac in form["macs"].split(","):
        mac = mac.strip()
        if mac and mac not in macs:
            macs.append(mac)
    return macs


def locatePortal(name, url, macs, proxy):
    """Find the portal's API address from whatever was typed, saying what happened."""
    found, tried = stb.findPortal(url, macs, proxy)
    if not found:
        message = (
            "Couldn't log in to Portal({}) at any of: {}. Check the address and MACs. "
            "If the portal only accepts your MAC from one box, turn on Device lock.".format(name, ", ".join(tried))
        )
        logger.error(message)
        flash(message, "danger")
    elif found != url.strip():
        flash("Found Portal({}) at {}".format(name, found), "info")
    return found


def testMac(name, url, mac, proxy, deviceLocked):
    """The MAC's expiry if the portal accepts it, flashing the result either way."""
    token = stb.getToken(url, mac, proxy)
    if token:
        stb.getProfile(url, mac, token, proxy)
        expiry = stb.getExpires(url, mac, token, proxy)
        if expiry:
            logger.info("Successfully tested MAC({}) for Portal({})".format(mac, name))
            flash("Successfully tested MAC({}) for Portal({})".format(mac, name), "success")
            return expiry
    message = "Portal({}) at {} refused MAC({}).".format(name, url, mac)
    if not deviceLocked:
        message += " If the portal only accepts this MAC from one box, turn on Device lock and add that box's details."
    else:
        message += " Check the device details: some portals check more than the main fields (see Advanced)."
    logger.error(message)
    flash(message, "danger")


@app.route("/portal/add", methods=["POST"])
@authorise
def portalsAdd():
    id = uuid.uuid4().hex
    enabled = "true"
    name = request.form["name"]
    url = request.form["url"]
    macs = formMacs(request.form)
    streamsPerMac = request.form["streams per mac"]
    proxy = request.form["proxy"]
    logoSource = request.form.get("logos")
    if logoSource not in LOGO_SOURCES:
        logoSource = defaultPortal["logos"]

    error = applyDeviceForm(request.form, macs)
    if error:
        flash(error, "danger")
        return redirect("/portals", code=302)

    url = locatePortal(name, url, macs, proxy)
    if not url:
        return redirect("/portals", code=302)

    deviceLocked = request.form.get("device state") == "on"
    macsd = {}
    for mac in macs:
        expiry = testMac(name, url, mac, proxy, deviceLocked)
        if expiry:
            macsd[mac] = expiry

    if len(macsd) > 0:
        portal = {
            "enabled": enabled,
            "name": name,
            "url": url,
            "macs": macsd,
            "streams per mac": streamsPerMac,
            "proxy": proxy,
            "logos": logoSource,
        }

        for setting, default in defaultPortal.items():
            if not portal.get(setting):
                portal[setting] = default

        portals = getPortals()
        portals[id] = portal
        savePortals(portals)
        logger.info("Portal({}) added!".format(portal["name"]))
        flash("Portal({}) added!".format(name), "success")

    else:
        logger.error("None of the MACs tested OK for Portal({}). Not added".format(name))

    return redirect("/portals", code=302)


@app.route("/portal/update", methods=["POST"])
@authorise
def portalUpdate():
    id = request.form["id"]
    enabled = request.form.get("enabled", "false")
    name = request.form["name"]
    url = request.form["url"]
    newmacs = formMacs(request.form)
    streamsPerMac = request.form["streams per mac"]
    proxy = request.form["proxy"]
    retest = request.form.get("retest", None)

    error = applyDeviceForm(request.form, newmacs)
    if error:
        flash(error, "danger")
        return redirect("/portals", code=302)

    portals = getPortals()
    logoSource = request.form.get("logos")
    if logoSource not in LOGO_SOURCES:
        logoSource = portals[id].get("logos", defaultPortal["logos"])
    if url.strip() != portals[id]["url"] or retest:
        url = locatePortal(name, url, newmacs, proxy)
        if not url:
            return redirect("/portals", code=302)

    deviceLocked = request.form.get("device state") == "on" or any(stb.device(mac) for mac in newmacs)
    oldmacs = portals[id]["macs"]
    macsout = {}

    for mac in newmacs:
        if retest or mac not in oldmacs.keys():
            expiry = testMac(name, url, mac, proxy, deviceLocked)
            if expiry:
                macsout[mac] = expiry
        else:
            macsout[mac] = oldmacs[mac]

    if len(macsout) > 0:
        portals[id]["enabled"] = enabled
        portals[id]["name"] = name
        portals[id]["url"] = url
        portals[id]["macs"] = macsout
        portals[id]["streams per mac"] = streamsPerMac
        portals[id]["proxy"] = proxy
        logosChanged = logoSource != portals[id].get("logos")
        portals[id]["logos"] = logoSource
        savePortals(portals)
        logger.info("Portal({}) updated!".format(name))
        flash("Portal({}) updated!".format(name), "success")
        if logosChanged:
            portalLogos.pop(id, None)
            if looksUpLogos(portals[id]):
                currentLogoIndex()  # may not have been needed before
            threading.Thread(target=syncPlex, daemon=True).start()  # so Plex and Jellyfin show them

    else:
        logger.error("None of the MACs tested OK for Portal({}). Not updated".format(name))

    return redirect("/portals", code=302)


@app.route("/portal/remove", methods=["POST"])
@authorise
def portalRemove():
    id = request.form["deleteId"]
    portals = getPortals()
    name = portals[id]["name"]
    del portals[id]
    savePortals(portals)
    logger.info("Portal ({}) removed!".format(name))
    flash("Portal ({}) removed!".format(name), "success")
    return redirect("/portals", code=302)


# Channel logos: your own (set in the Playlist Editor), else the portal's and one looked up
# by name in the iptv-org database (downloaded in the background, refreshed weekly), in the
# order each portal's "logos" setting picks.
LOGO_SOURCES = {
    "portal": "The portal's, looked up where it has none",
    "lookup": "Looked up, the portal's where none is found",
    "portal only": "The portal's only",
    "lookup only": "Looked up only",
}
LOGO_INDEX_MAX_AGE = 7 * 24 * 3600
LOGO_RETRY_AGE = 3600
logoIndex = {"index": None, "time": 0, "tried": 0}
logoIndexLock = threading.Lock()
portalLogos = {}


def logoIndexFile():
    return os.path.join(os.path.dirname(os.path.abspath(configFile)), "logo-index.json")


def refreshLogoIndex(force=False):
    """Load the logo index from disk, downloading a fresh one if it's missing or a week old
    (or always, with force). False if a download was needed and failed."""
    with logoIndexLock:
        path = logoIndexFile()
        if not force:
            try:
                with open(path) as f:
                    logoIndex.update(index=json.load(f), time=os.path.getmtime(path))
                portalLogos.clear()
            except (OSError, ValueError):
                pass
            if logoIndex["index"] is not None and time.time() - logoIndex["time"] < LOGO_INDEX_MAX_AGE:
                return True
        try:
            # Tens of MB of JSON to parse: never at the same time as the guide.
            with guideLock:
                data = [requests.get(u, timeout=60).json() for u in (logos.CHANNELS_URL, logos.LOGOS_URL, logos.FEEDS_URL)]
                index = logos.buildIndex(*data)
                del data
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(index, f)
            os.replace(tmp, path)
            logoIndex.update(index=index, time=time.time())
            portalLogos.clear()
            logger.info("Channel logos downloaded from iptv-org: {} names".format(len(index)))
            return True
        except Exception as e:
            logger.error("Couldn't download channel logos from iptv-org ({}); trying again later".format(e))
            return False


def looksUpLogos(portal):
    return portal.get("logos", defaultPortal["logos"]) != "portal only"


def currentLogoIndex():
    """The logo index if it's ready (None if not). Loads it in the background."""
    now = time.time()
    stale = logoIndex["index"] is None or now - logoIndex["time"] > LOGO_INDEX_MAX_AGE
    if stale and now - logoIndex["tried"] > LOGO_RETRY_AGE and not logoIndexLock.locked():
        logoIndex["tried"] = now
        threading.Thread(target=refreshLogoIndex, daemon=True).start()
    return logoIndex["index"]


def matchedLogos(portalId, allChannels, genres=None):
    """{channel id: logo URL} matched by name for a portal's channels (worked out once per list)."""
    if not looksUpLogos(getPortals().get(portalId, {})):
        return {}
    index = currentLogoIndex()
    if not index or not allChannels:
        return {}
    cached = portalLogos.get(portalId)
    if cached and cached[0] == id(allChannels) and cached[1] == id(index):
        return cached[2]
    genres = genres or {}
    entries = [(str(c["id"]), str(c["name"]), genres.get(str(c.get("tv_genre_id")), "")) for c in allChannels]
    result = logos.matchAll(index, entries)
    portalLogos[portalId] = (id(allChannels), id(index), result)
    return result


def knownLogos(portalId):
    """The matched logos last worked out for a portal (for places without its channel list)."""
    cached = portalLogos.get(portalId)
    return cached[2] if cached and looksUpLogos(getPortals().get(portalId, {})) else {}


def portalLogoUrl(portal, portalLogo):
    """The full address of a logo as the portal lists it ("" if it has none)."""
    portalLogo = str(portalLogo or "")
    if not portalLogo or "://" in portalLogo:
        return portalLogo
    parsed = urlparse(portal["url"])
    base = parsed.scheme + "://" + parsed.netloc
    if portalLogo.startswith("/"):
        return base + portalLogo
    # A bare file name: Stalker portals keep logos under misc/logos/320 next to server/.
    root = parsed.path.split("/server/")[0] if "/server/" in parsed.path else ""
    return base + root + "/misc/logos/320/" + portalLogo


def channelLogo(portal, channelId, portalLogo, matched, yours=True):
    """The logo to show for a channel: yours, else the portal's and the matched one in the
    order the portal's "logos" setting picks."""
    custom = portal.get("custom logos", {}).get(channelId) if yours else None
    if custom:
        return custom
    fromPortal = portalLogoUrl(portal, portalLogo)
    lookedUp = matched.get(channelId, "")
    source = portal.get("logos", defaultPortal["logos"])
    if source == "portal only":
        return fromPortal
    if source == "lookup only":
        return lookedUp
    if source == "lookup":
        return lookedUp or fromPortal
    return fromPortal or lookedUp


# "Refresh logos" on the Portals page: the latest result for each portal, by portal id.
logoRefreshes = {}
logoRefreshesLock = threading.Lock()


def refreshPortalLogos(portalId):
    """Load a portal's channels (and so its logos) afresh, download the logo index again and
    match the names again, then update Plex and Jellyfin. The result goes in logoRefreshes."""
    portal = getPortals()[portalId]
    notes = []
    try:
        if looksUpLogos(portal) and refreshLogoIndex(force=True) is False:
            notes.append("couldn't download logos from iptv-org, so the last ones were used")
        allChannels = genres = None
        for mac in portal["macs"]:
            try:
                token = stb.getToken(portal["url"], mac, portal["proxy"])
                stb.getProfile(portal["url"], mac, token, portal["proxy"])
                allChannels = stb.getAllChannels(portal["url"], mac, token, portal["proxy"], refresh=True)
                genres = stb.getGenreNames(portal["url"], mac, token, portal["proxy"])
                break
            except Exception:
                allChannels = None
        if not allChannels:
            message, ok = "Couldn't load the channels from the portal", False
        else:
            portalLogos.pop(portalId, None)
            matched = matchedLogos(portalId, allChannels, genres)
            enabled = set(portal.get("enabled channels", []))
            channels = [c for c in allChannels if str(c["id"]) in enabled] or allChannels
            counts = {"yours": 0, "portal": 0, "lookup": 0, "none": 0}
            for c in channels:
                channelId = str(c["id"])
                logo = channelLogo(portal, channelId, c.get("logo"), matched)
                if not logo:
                    counts["none"] += 1
                elif logo == portal.get("custom logos", {}).get(channelId):
                    counts["yours"] += 1
                elif logo == portalLogoUrl(portal, c.get("logo")):
                    counts["portal"] += 1
                else:
                    counts["lookup"] += 1
            message = "{} {}: {} from the portal, {} looked up, {} yours, {} without".format(
                len(channels), "in the playlist" if enabled else "channels",
                counts["portal"], counts["lookup"], counts["yours"], counts["none"])
            ok = True
            category, synced = syncPlex()
            if category != "info":
                notes.append(synced)
    except Exception as e:
        logger.exception("Refreshing logos for Portal({}) failed".format(portal["name"]))
        message, ok = "Refreshing logos failed ({})".format(e.__class__.__name__), False
    message = "; ".join([message] + notes)
    (logger.info if ok else logger.error)("Logos for Portal({}): {}".format(portal["name"], message))
    with logoRefreshesLock:
        logoRefreshes[portalId] = {
            "running": False,
            "ok": ok,
            "message": message,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


@app.route("/portal/logos", methods=["POST"])
@authorise
def portalLogosRefresh():
    id = request.form["id"]
    portals = getPortals()
    if id not in portals:
        flash("That portal no longer exists", "danger")
        return redirect("/portals", code=302)
    source = request.form.get("logos")
    if source in LOGO_SOURCES and source != portals[id].get("logos"):
        portals[id]["logos"] = source
        savePortals(portals)
    with logoRefreshesLock:
        if logoRefreshes.get(id, {}).get("running"):
            flash("Logos for {} are already being refreshed".format(portals[id]["name"]), "info")
            return redirect("/portals", code=302)
        logoRefreshes[id] = {"running": True, "ok": True, "message": "Refreshing logos...",
                             "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
    threading.Thread(target=refreshPortalLogos, args=(id,), daemon=True).start()
    flash("Refreshing the channel logos for {}. It takes a minute or two; the result shows on its card."
          .format(portals[id]["name"]), "info")
    return redirect("/portals", code=302)


@app.route("/portal/logos/status", methods=["GET"])
@authorise
def portalLogosStatus():
    with logoRefreshesLock:
        return flask.jsonify(logoRefreshes)


@app.route("/editor", methods=["GET"])
@authorise
def editor():
    return render_template("editor.html", allBlocks=sorted(availability.blockNames(getPortals())))


@app.route("/editor_data", methods=["GET"])
@authorise
def editor_data():
    channels = []
    portals = getPortals()
    for portal in portals:
        if portals[portal]["enabled"] == "true":
            portalName = portals[portal]["name"]
            url = portals[portal]["url"]
            macs = list(portals[portal]["macs"].keys())
            proxy = portals[portal]["proxy"]
            enabledChannels = portals[portal].get("enabled channels", [])
            customChannelNames = portals[portal].get("custom channel names", {})
            customGenres = portals[portal].get("custom genres", {})
            customChannelNumbers = portals[portal].get("custom channel numbers", {})
            customEpgIds = portals[portal].get("custom epg ids", {})
            customLogos = portals[portal].get("custom logos", {})
            fallbackChannels = portals[portal].get("fallback channels", {})
            channelBlocks = portals[portal].get("channel blocks", {})
            deadChannels = portals[portal].get("dead channels", [])
            favouriteChannels = portals[portal].get("favourite channels", [])
            available = availability.availableChannels(portals[portal], getBlocks())

            for mac in macs:
                try:
                    token = stb.getToken(url, mac, proxy)
                    stb.getProfile(url, mac, token, proxy)
                    allChannels = stb.getAllChannels(url, mac, token, proxy)
                    genres = stb.getGenreNames(url, mac, token, proxy)
                    break
                except:
                    allChannels = None
                    genres = None

            if allChannels and genres:
                matched = matchedLogos(portal, allChannels, genres)
                for channel in allChannels:
                    channelId = str(channel["id"])
                    channelName = str(channel["name"])
                    channelNumber = str(channel["number"])
                    genre = str(genres.get(str(channel["tv_genre_id"])))
                    if channelId in enabledChannels:
                        enabled = True
                    else:
                        enabled = False
                    customChannelNumber = customChannelNumbers.get(channelId)
                    if customChannelNumber == None:
                        customChannelNumber = ""
                    customChannelName = customChannelNames.get(channelId)
                    if customChannelName == None:
                        customChannelName = ""
                    customGenre = customGenres.get(channelId)
                    if customGenre == None:
                        customGenre = ""
                    customEpgId = customEpgIds.get(channelId)
                    if customEpgId == None:
                        customEpgId = ""
                    fallbackChannel = fallbackChannels.get(channelId)
                    if fallbackChannel == None:
                        fallbackChannel = ""
                    channels.append(
                        {
                            "portal": portal,
                            "portalName": portalName,
                            "enabled": enabled,
                            "channelNumber": channelNumber,
                            "customChannelNumber": customChannelNumber,
                            "channelName": channelName,
                            "customChannelName": customChannelName,
                            "genre": genre,
                            "customGenre": customGenre,
                            "channelId": channelId,
                            "customEpgId": customEpgId,
                            "logo": channelLogo(portals[portal], channelId, channel.get("logo"), matched),
                            "customLogo": customLogos.get(channelId, ""),
                            "autoLogo": channelLogo(portals[portal], channelId, channel.get("logo"), matched, yours=False),
                            "fallbackChannel": fallbackChannel,
                            "blocks": channelBlocks.get(channelId, []),
                            "dead": channelId in deadChannels,
                            "favourite": channelId in favouriteChannels,
                            "blockFavourites": blockFavouritesOf(portal, channelId),
                            "available": channelId in available,
                            "link": previewLink(portal, channelId),
                        }
                    )
            else:
                logger.error(
                    "Error getting channel data for {}, skipping".format(portalName)
                )
                flash(
                    "Error getting channel data for {}, skipping".format(portalName),
                    "danger",
                )

    data = {"data": channels}

    return flask.jsonify(data)


@app.route("/editor/save", methods=["POST"])
@authorise
def editorSave():
    enabledEdits = json.loads(request.form["enabledEdits"])
    numberEdits = json.loads(request.form["numberEdits"])
    nameEdits = json.loads(request.form["nameEdits"])
    genreEdits = json.loads(request.form["genreEdits"])
    epgEdits = json.loads(request.form["epgEdits"])
    fallbackEdits = json.loads(request.form["fallbackEdits"])
    blockEdits = json.loads(request.form.get("blockEdits", "[]"))
    logoEdits = json.loads(request.form.get("logoEdits", "[]"))
    portals = getPortals()
    blocks = getBlocks()
    availableBefore = {p: availability.availableChannels(portals[p], blocks) for p in portals}
    for edit in enabledEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        enabled = edit["enabled"]
        if enabled:
            portals[portal].setdefault("enabled channels", [])
            portals[portal]["enabled channels"].append(channelId)
        else:
            portals[portal]["enabled channels"] = list(
                filter((channelId).__ne__, portals[portal]["enabled channels"])
            )

    for edit in numberEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customNumber = edit["custom number"]
        if customNumber:
            portals[portal].setdefault("custom channel numbers", {})
            portals[portal]["custom channel numbers"].update({channelId: customNumber})
        else:
            portals[portal]["custom channel numbers"].pop(channelId)

    for edit in nameEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customName = edit["custom name"]
        if customName:
            portals[portal].setdefault("custom channel names", {})
            portals[portal]["custom channel names"].update({channelId: customName})
        else:
            portals[portal]["custom channel names"].pop(channelId)

    for edit in genreEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customGenre = edit["custom genre"]
        if customGenre:
            portals[portal].setdefault("custom genres", {})
            portals[portal]["custom genres"].update({channelId: customGenre})
        else:
            portals[portal]["custom genres"].pop(channelId)

    for edit in epgEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customEpgId = edit["custom epg id"]
        if customEpgId:
            portals[portal].setdefault("custom epg ids", {})
            portals[portal]["custom epg ids"].update({channelId: customEpgId})
        else:
            portals[portal]["custom epg ids"].pop(channelId)

    for edit in fallbackEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        channelName = edit["channel name"]
        if channelName:
            portals[portal].setdefault("fallback channels", {})
            portals[portal]["fallback channels"].update({channelId: channelName})
        else:
            portals[portal]["fallback channels"].pop(channelId)

    for edit in logoEdits:
        portal = edit["portal"]
        customLogos = dict(portals[portal].get("custom logos", {}))
        if edit["logo"].strip():
            customLogos[edit["channel id"]] = edit["logo"].strip()
        else:
            customLogos.pop(edit["channel id"], None)
        portals[portal]["custom logos"] = customLogos

    # Build new dicts rather than mutating: other threads may be iterating the old ones.
    newChannelBlocks = {}
    for edit in blockEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        names = availability.parseBlockNames(edit["block"])
        channelBlocks = newChannelBlocks.setdefault(
            portal, dict(portals[portal].get("channel blocks", {}))
        )
        if names:
            channelBlocks[channelId] = names
        else:
            channelBlocks.pop(channelId, None)
    for portal, channelBlocks in newChannelBlocks.items():
        portals[portal]["channel blocks"] = channelBlocks

    savePortals(portals)
    saveBlocks(availability.pruneBlocks(portals, blocks))
    logger.info("Playlist config saved!")
    flash("Playlist config saved!", "success")

    availableAfter = {p: availability.availableChannels(portals[p], getBlocks()) for p in portals}
    if availableAfter != availableBefore:
        category, message = syncPlex()
        flash(message, category)

    return redirect("/editor", code=302)


@app.route("/editor/reset", methods=["POST"])
@authorise
def editorReset():
    portals = getPortals()
    for portal in portals:
        portals[portal]["enabled channels"] = []
        portals[portal]["custom channel numbers"] = {}
        portals[portal]["custom channel names"] = {}
        portals[portal]["custom genres"] = {}
        portals[portal]["custom epg ids"] = {}
        portals[portal]["fallback channels"] = {}
        portals[portal]["custom logos"] = {}

    savePortals(portals)
    logger.info("Playlist reset!")
    flash("Playlist reset!", "success")

    return redirect("/editor", code=302)


@app.route("/blocks", methods=["GET"])
@authorise
def blocksPage():
    return render_template(
        "blocks.html",
        blocks=availability.blockSummaries(getPortals(), getBlocks(), getHiddenBlocks()),
        allBlocks=sorted(availability.blockNames(getPortals())),
        favourites=sum(
            len(p.get("favourite channels", [])) for p in getPortals().values() if p["enabled"] == "true"
        ),
        lastPlexSync=lastPlexSync,
        plexConfigured=plexConfigured(),
        lastJellyfinSync=lastJellyfinSync,
        jellyfinConfigured=jellyfinConfigured(),
        retryAt=syncRetry["at"],
    )


@app.route("/blocks/toggle", methods=["POST"])
@authorise
def blocksToggle():
    name = request.form["name"]
    enabled = request.form.get("enabled") == "true"
    if name not in availability.blockNames(getPortals()):
        flash("No block called {}".format(name), "danger")
        return redirect("/blocks", code=302)

    blocks = getBlocks()
    blocks[name] = "true" if enabled else "false"
    saveBlocks(blocks)
    logger.info("Block({}) switched {}".format(name, "on" if enabled else "off"))
    flash("{} switched {}".format(name, "on" if enabled else "off"), "success")

    category, message = syncPlex()
    flash(message, category)
    return redirect("/blocks", code=302)


@app.route("/blocks/rename", methods=["POST"])
@authorise
def blocksRename():
    name = request.form["name"]
    newNames = availability.parseBlockNames(request.form.get("newName", ""))
    portals = getPortals()
    if name not in availability.blockNames(portals):
        flash("No block called {}".format(name), "danger")
        return redirect("/blocks", code=302)
    if len(newNames) != 1:
        flash("Give the block one new name, without commas", "danger")
        return redirect("/blocks", code=302)
    newName = newNames[0]
    if newName == name:
        return redirect("/blocks", code=302)
    if newName in availability.blockNames(portals):
        flash("There's already a block called {}".format(newName), "danger")
        return redirect("/blocks", code=302)

    # The lineup doesn't change, so Plex and Jellyfin don't need updating.
    availability.renameBlock(portals, name, newName)
    blocks = getBlocks()
    if name in blocks:
        blocks[newName] = blocks.pop(name)
    config["hidden blocks"] = [newName if n == name else n for n in getHiddenBlocks()]
    favourites = getBlockFavourites()
    if name in favourites:
        favourites[newName] = favourites.pop(name)
    for pageFilters in getSavedFilters().values():
        for filters in pageFilters.values():
            if filters.get("block") == name:
                filters["block"] = newName
    saveBlocks(blocks)
    logger.info("Block({}) renamed to {}".format(name, newName))
    flash("{} renamed to {}".format(name, newName), "success")
    return redirect("/blocks", code=302)


@app.route("/blocks/hide", methods=["POST"])
@authorise
def blocksHide():
    name = request.form["name"]
    hidden = request.form.get("hidden") == "true"
    if name not in availability.blockNames(getPortals()):
        flash("No block called {}".format(name), "danger")
        return redirect("/blocks", code=302)

    names = [n for n in getHiddenBlocks() if n != name]
    config["hidden blocks"] = names + [name] if hidden else names
    writeConfig(config)
    logger.info("Block({}) {} the API".format(name, "hidden from" if hidden else "shown in"))
    flash("{} {} the API".format(name, "hidden from" if hidden else "shown in"), "success")
    return redirect("/blocks", code=302)


@app.route("/blocks/sync", methods=["POST"])
@authorise
def blocksSync():
    category, message = syncPlex()
    flash(message, category)
    return redirect("/blocks", code=302)


@app.route("/channel/dead", methods=["POST"])
@authorise
def channelDead():
    portal = request.form["portal"]
    channelId = request.form["channelId"]
    dead = request.form.get("dead") == "true"
    portals = getPortals()
    if portal not in portals:
        return flask.jsonify({"error": "Unknown portal"}), 404

    blocks = getBlocks()
    wasAvailable = channelId in availability.availableChannels(portals[portal], blocks)
    deadChannels = [c for c in portals[portal].get("dead channels", []) if c != channelId]
    if dead:
        deadChannels.append(channelId)
    portals[portal]["dead channels"] = deadChannels
    savePortals(portals)
    logger.info(
        "Channel({}) for Portal({}) marked {}".format(channelId, portal, "dead" if dead else "working")
    )

    plexMessage = ""
    if wasAvailable != (channelId in availability.availableChannels(portals[portal], blocks)):
        _, plexMessage = syncPlex()
    return flask.jsonify({"dead": dead, "plex": plexMessage})


@app.route("/channel/blocks", methods=["POST"])
@authorise
def channelBlocks():
    portal = request.form["portal"]
    channelId = request.form["channelId"]
    names = availability.parseBlockNames(",".join(request.form.getlist("blocks")))
    portals = getPortals()
    if portal not in portals:
        return flask.jsonify({"error": "Unknown portal"}), 404

    blocks = getBlocks()
    wasAvailable = channelId in availability.availableChannels(portals[portal], blocks)
    # Build a new dict rather than mutating: other threads may be iterating the old one.
    channelBlocks = dict(portals[portal].get("channel blocks", {}))
    if names:
        channelBlocks[channelId] = names
    else:
        channelBlocks.pop(channelId, None)
    portals[portal]["channel blocks"] = channelBlocks
    savePortals(portals)
    saveBlocks(availability.pruneBlocks(portals, blocks))
    logger.info("Channel({}) for Portal({}) blocks set to {}".format(channelId, portal, names))

    plexMessage = ""
    if wasAvailable != (channelId in availability.availableChannels(portals[portal], getBlocks())):
        _, plexMessage = syncPlex()
    return flask.jsonify(
        {"blocks": names, "allBlocks": sorted(availability.blockNames(portals)), "plex": plexMessage}
    )


@app.route("/block/favourite", methods=["POST"])
@authorise
def blockFavourite():
    """Make a channel a favourite within one of its blocks, or not. Overall favourites are separate."""
    portal = request.form["portal"]
    channelId = request.form["channelId"]
    block = request.form["block"]
    portals = getPortals()
    if portal not in portals:
        return flask.jsonify({"error": "Unknown portal"}), 404
    if block not in portals[portal].get("channel blocks", {}).get(channelId, []):
        return flask.jsonify({"error": "That channel isn't in {}".format(block)}), 400
    favourites = getBlockFavourites()
    channelIds = [c for c in favourites.get(block, {}).get(portal, []) if c != channelId]
    if request.form.get("favourite") == "true":
        channelIds.append(channelId)
    favourites.setdefault(block, {})[portal] = channelIds
    saveBlocks(getBlocks())  # tidies empty lists and saves
    logger.info("Channel({}) for Portal({}) {} favourite in Block({})".format(
        channelId, portal, "made a" if request.form.get("favourite") == "true" else "no longer a", block))
    return flask.jsonify({"blockFavourites": blockFavouritesOf(portal, channelId)})


@app.route("/channels/blocks", methods=["POST"])
@authorise
def channelsBlocks():
    """Add many channels to a block, or take them out of it, in one save.

    JSON: {"channels": [{"portal", "channelId"}, ...], "block": "name(s)", "action": "add"|"remove"}
    """
    data = request.get_json(force=True, silent=True) or {}
    names = availability.parseBlockNames(str(data.get("block", "")))
    action = data.get("action")
    if not names or action not in ("add", "remove"):
        return flask.jsonify({"error": "Give a block name and add or remove"}), 400

    portals = getPortals()
    blocks = getBlocks()
    before = {p: availability.availableChannels(portals[p], blocks) for p in portals}
    # Build new dicts rather than mutating: other threads may be iterating the old ones.
    newChannelBlocks = {}
    changed = []
    for channel in data.get("channels", []):
        portal = channel.get("portal")
        channelId = str(channel.get("channelId"))
        if portal not in portals:
            continue
        channelBlocks = newChannelBlocks.setdefault(portal, dict(portals[portal].get("channel blocks", {})))
        current = list(channelBlocks.get(channelId, []))
        if action == "add":
            current += [n for n in names if n not in current]
        else:
            current = [n for n in current if n not in names]
        if current:
            channelBlocks[channelId] = current
        else:
            channelBlocks.pop(channelId, None)
        changed.append({"portal": portal, "channelId": channelId, "blocks": current})
    for portal, channelBlocks in newChannelBlocks.items():
        portals[portal]["channel blocks"] = channelBlocks
    savePortals(portals)
    saveBlocks(availability.pruneBlocks(portals, blocks))
    logger.info("{} {} channel(s) {} block(s) {}".format(
        "Added" if action == "add" else "Removed", len(changed), "to" if action == "add" else "from", names))

    plexMessage = ""
    if {p: availability.availableChannels(portals[p], getBlocks()) for p in portals} != before:
        _, plexMessage = syncPlex()
    return flask.jsonify(
        {"channels": changed, "allBlocks": sorted(availability.blockNames(portals)), "plex": plexMessage}
    )


@app.route("/channel/favourite", methods=["POST"])
@authorise
def channelFavourite():
    portal = request.form["portal"]
    channelId = request.form["channelId"]
    favourite = request.form.get("favourite") == "true"
    portals = getPortals()
    if portal not in portals:
        return flask.jsonify({"error": "Unknown portal"}), 404

    favouriteChannels = [c for c in portals[portal].get("favourite channels", []) if c != channelId]
    if favourite:
        favouriteChannels.append(channelId)
    portals[portal]["favourite channels"] = favouriteChannels
    savePortals(portals)
    logger.info(
        "Channel({}) for Portal({}) {}".format(channelId, portal, "favourited" if favourite else "unfavourited")
    )
    return flask.jsonify({"favourite": favourite})


GUIDE_MAX_AGE = 3600
GUIDE_RETRY_AGE = 300
guideCache = {"loaded": 0, "time": None, "programmes": [], "channels": {}, "failed": [], "partial": []}
guideLock = threading.Lock()


def loadGuide(force=False):
    """The guide for every channel on the enabled portals, reloaded once it's an hour old."""
    global guideCache
    with guideLock:
        if not force and time.time() - guideCache["loaded"] < GUIDE_MAX_AGE:
            return guideCache

        now = int(time.time())
        programmes = []
        channels = {}
        failed = []
        partial = []
        portals = getPortals()
        for portal in portals:
            if portals[portal]["enabled"] != "true":
                continue
            name = portals[portal]["name"]
            url = portals[portal]["url"]
            proxy = portals[portal]["proxy"]
            allChannels = None
            epg = None
            short = False
            for mac in portals[portal]["macs"].keys():
                try:
                    token = stb.getToken(url, mac, proxy)
                    stb.getProfile(url, mac, token, proxy)
                    allChannels = stb.getAllChannels(url, mac, token, proxy, refresh=force)
                    epg = stb.getEpg(url, mac, token, 24, proxy)
                    if not epg:
                        # No bulk guide: fetching every channel one by one would take too long,
                        # so fall back to the channels in the lineup, as the XMLTV does.
                        short = True
                        epg = stb.getShortEpg(
                            url, mac, token, availability.availableChannels(portals[portal], getBlocks()), proxy
                        )
                    if allChannels and epg:
                        break
                except Exception:
                    allChannels = None
                    epg = None

            if not (allChannels and epg):
                logger.error("Error loading the guide for {}, skipping".format(name))
                failed.append(name)
                continue
            if short:
                partial.append(name)
            for c in allChannels:
                channels[(portal, str(c["id"]))] = {
                    "name": str(c["name"]),
                    "number": str(c["number"]),
                    "logo": str(c.get("logo") or ""),
                }
            programmes.extend(guide.programmes(portal, epg, now))

        logger.info("Guide loaded: {} programmes on {} channels".format(len(programmes), len(channels)))
        guideCache = {
            # Try a failed portal again sooner than the usual refresh.
            "loaded": time.time() - (GUIDE_MAX_AGE - GUIDE_RETRY_AGE if failed else 0),
            "time": time.time(),
            "programmes": programmes,
            "channels": channels,
            "failed": failed,
            "partial": partial,
        }
        return guideCache


# One channel's schedule, for the player and the channel lists. The portal's per-channel
# EPG is one quick request and often covers several days, unlike the 24 h bulk guide.
CHANNEL_GUIDE_TTL = 900
channelGuides = {}
channelGuidesLock = threading.Lock()


def channelProgrammes(portalId, channelId):
    key = (portalId, channelId)
    with channelGuidesLock:
        cached = channelGuides.get(key)
        if cached and time.time() - cached["time"] < CHANNEL_GUIDE_TTL:
            return cached["programmes"]

    portal = getPortals()[portalId]
    url = portal["url"]
    proxy = portal["proxy"]
    now = int(time.time())
    programmes = []
    for mac in portal["macs"].keys():
        try:
            token = stb.getToken(url, mac, proxy)
            if not token:
                continue
            stb.getProfile(url, mac, token, proxy)
            epg = stb.getShortEpg(url, mac, token, [channelId], proxy)
            if epg:
                programmes = guide.programmes(portalId, epg, now)
            break
        except Exception:
            continue
    if not programmes:
        # The portal had nothing for this channel: use the full guide if it's already loaded.
        programmes = [p for p in guideCache["programmes"] if p[4] == portalId and p[5] == channelId]
    programmes.sort()

    with channelGuidesLock:
        for k in [k for k, v in channelGuides.items() if time.time() - v["time"] >= CHANNEL_GUIDE_TTL]:
            del channelGuides[k]
        channelGuides[key] = {"time": time.time(), "programmes": programmes}
    return programmes


@app.route("/channel/guide", methods=["GET"])
@authorise
def channelGuide():
    portalId = request.args["portal"]
    channelId = request.args["channelId"]
    if portalId not in getPortals():
        return flask.jsonify({"error": "Unknown portal"}), 404
    now = int(time.time())
    upcoming = [p for p in channelProgrammes(portalId, channelId) if p[1] > now][:60]
    return flask.jsonify(
        {"programmes": [{"start": p[0], "stop": p[1], "title": p[2], "desc": p[3]} for p in upcoming]}
    )


@app.route("/guide", methods=["GET"])
@authorise
def guidePage():
    return render_template("guide.html", allBlocks=sorted(availability.blockNames(getPortals())))


@app.route("/multiview", methods=["GET"])
@authorise
def multiview():
    blocks = getBlocks()
    enabledBlocks = sorted(n for n in availability.blockNames(getPortals()) if blocks.get(n) == "true")
    return render_template("multiview.html", tuners=tunerCount(), enabledBlocks=enabledBlocks)


@app.route("/recordings", methods=["GET"])
@authorise
def recordingsPage():
    return render_template("recordings.html", folder=getSettings().get("recordings folder", "").strip())


@app.route("/recordings/list", methods=["GET"])
@authorise
def recordingsList():
    folder = getSettings().get("recordings folder", "").strip()
    free = None
    if folder:
        # The first recording makes the folder; until then, the space where it will be.
        path = os.path.abspath(folder)
        while not os.path.isdir(path) and os.path.dirname(path) != path:
            path = os.path.dirname(path)
        try:
            free = shutil.disk_usage(path).free
        except OSError:
            pass
    return flask.jsonify({"recordings": getRecorder().list(), "folder": folder, "free": free})


@app.route("/recordings/start", methods=["POST"])
@authorise
def recordingsStart():
    """Record a channel now. JSON: {portal, channelId, name, minutes?} or {..., until?}."""
    data = request.get_json(force=True, silent=True) or {}
    portal = str(data.get("portal", ""))
    channelId = str(data.get("channelId", ""))
    if portal not in getPortals() or not channelId:
        return flask.jsonify({"error": "Unknown channel"}), 404
    name = str(data.get("name") or channelId)[:100]
    stop = None
    try:
        if data.get("minutes") is not None:
            minutes = float(data["minutes"])
            if not 0 < minutes <= 24 * 60:
                raise ValueError
            stop = time.time() + minutes * 60
        elif data.get("until") is not None:
            stop = float(data["until"])
            if not time.time() < stop <= time.time() + 24 * 3600:
                raise ValueError
    except (TypeError, ValueError):
        return flask.jsonify({"error": "Record for up to 24 hours, ending in the future"}), 400
    try:
        rec = getRecorder().start(portal, channelId, name, stop=stop)
    except recordings.RecordingError as e:
        return flask.jsonify({"error": str(e)}), 503
    return flask.jsonify(rec)


@app.route("/recordings/<id>/stop", methods=["POST"])
@authorise
def recordingsStop(id):
    if not getRecorder().stop(id):
        return flask.jsonify({"error": "That recording isn't running"}), 404
    return flask.jsonify({"stopping": True})


@app.route("/recordings/<id>/delete", methods=["POST"])
@authorise
def recordingsDelete(id):
    rec = getRecorder().store.get(id)
    if not rec:
        return flask.jsonify({"error": "No such recording"}), 404
    if not getRecorder().delete(id):
        return flask.jsonify({"error": "Stop it before deleting it"}), 409
    logger.info("Recording({}) deleted".format(id))
    return flask.jsonify({"deleted": True})


@app.route("/recordings/<id>/watch", methods=["GET"])
@authorise
def recordingsWatch(id):
    """Watch a recording from its start, even while it's still recording."""
    rec = getRecorder().store.get(id)
    if rec and rec["status"] != "recording" and rec.get("file") and os.path.isfile(rec["file"]):
        return redirect("/recordings/{}/file".format(id), code=302)
    if not rec or rec["status"] != "recording":
        return flask.jsonify({"error": "No such recording"}), 404
    return Response(watchRecording(id), mimetype="application/octet-stream")


def watchRecording(id):
    """A recording so far, from its start, as fragmented MP4 for the browser (as previews
    are), following it as it grows. It reads the recording's files: no tuner."""
    remux = subprocess.Popen(PREVIEW_REMUX, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    stop = threading.Event()

    def feed():
        parts = getRecorder().follow(id)
        try:
            for chunk in parts:
                if stop.is_set():
                    break
                remux.stdin.write(chunk)
        except (OSError, ValueError):
            pass  # the viewer left
        finally:
            parts.close()
            try:
                remux.stdin.close()
            except (OSError, ValueError):
                pass

    threading.Thread(target=feed, daemon=True).start()
    try:
        while True:
            chunk = remux.stdout.read1(65536)
            if not chunk:
                break
            yield chunk
    finally:
        stop.set()
        remux.kill()
        remux.wait()


@app.route("/recordings/<id>/file", methods=["GET"])
@authorise
def recordingsFile(id):
    # Only a file the recorder wrote: the path comes from the recording, never the request.
    rec = getRecorder().store.get(id)
    if not rec or not rec.get("file") or not os.path.isfile(rec["file"]):
        return flask.jsonify({"error": "No such recording"}), 404
    return flask.send_file(rec["file"], mimetype="video/mp4", conditional=True,
                           as_attachment=request.args.get("download") == "1",
                           download_name=os.path.basename(rec["file"]))


@app.route("/guide/search", methods=["GET"])
@authorise
def guideSearch():
    query = request.args.get("q", "").strip()
    onNow = request.args.get("now") == "true"
    lineupOnly = request.args.get("lineup") == "true"
    favouritesOnly = request.args.get("favourites") == "true"
    hideDead = request.args.get("hideDead", "true") == "true"
    mode = request.args.get("mode", "prefix")
    if mode not in ("words", "prefix", "contains", "exact", "regex"):
        mode = "prefix"
    channelQuery = request.args.get("channel", "").strip()
    try:
        guide.parseQuery(query, mode)
        channelTest = guide.parseQuery(channelQuery, request.args.get("channelMode", "words"))
    except ValueError as e:
        return flask.jsonify({"error": str(e)}), 400

    cache = loadGuide(force=request.args.get("refresh") == "true")
    portals = getPortals()
    blocks = getBlocks()
    available = {p: availability.availableChannels(portals[p], blocks) for p in portals}

    def keep(portal, channelId):
        if portal not in portals or (portal, channelId) not in cache["channels"]:
            return False
        if hideDead and channelId in portals[portal].get("dead channels", []):
            return False
        if lineupOnly and channelId not in available[portal]:
            return False
        if favouritesOnly and channelId not in portals[portal].get("favourite channels", []):
            return False
        if channelTest:
            custom = portals[portal].get("custom channel names", {}).get(channelId, "")
            if not (channelTest(cache["channels"][(portal, channelId)]["name"]) or (custom and channelTest(custom))):
                return False
        return True

    matches, total = [], 0
    if query or onNow or lineupOnly or favouritesOnly or channelQuery:
        matches, total = guide.search(cache["programmes"], query, int(time.time()), keep, onNow, mode=mode)

    results = []
    for start, stop, title, desc, portal, channelId in matches:
        channel = cache["channels"][(portal, channelId)]
        p = portals[portal]
        results.append(
            {
                "start": start,
                "stop": stop,
                "title": title,
                "desc": desc,
                "portal": portal,
                "portalName": p["name"],
                "channelId": channelId,
                "channelName": channel["name"],
                "customChannelName": p.get("custom channel names", {}).get(channelId, ""),
                "channelNumber": p.get("custom channel numbers", {}).get(channelId) or channel["number"],
                "logo": channelLogo(p, channelId, channel.get("logo"), knownLogos(portal)),
                "dead": channelId in p.get("dead channels", []),
                "favourite": channelId in p.get("favourite channels", []),
                "blocks": p.get("channel blocks", {}).get(channelId, []),
                "available": channelId in available[portal],
                "link": previewLink(portal, channelId),
            }
        )

    return flask.jsonify(
        {
            "results": results,
            "total": total,
            "loadedAt": cache["time"],
            "programmes": len(cache["programmes"]),
            "failed": cache["failed"],
            "partial": cache["partial"],
        }
    )


@app.route("/settings", methods=["GET"])
@authorise
def settings():
    settings = getSettings()
    return render_template(
        "settings.html", settings=settings, defaultSettings=defaultSettings
    )


@app.route("/settings/save", methods=["POST"])
@authorise
def save():
    settings = {}

    for setting, _ in defaultSettings.items():
        value = request.form.get(setting, "false")
        settings[setting] = value

    settings["api token"] = getSettings()["api token"]  # changed only by "New token"
    settings["jellyfin url"] = request.form.get("jellyfin url", "").strip().rstrip("/")
    if request.form.get("clear jellyfin api key") == "true":
        settings["jellyfin api key"] = ""
    elif not request.form.get("jellyfin api key"):
        settings["jellyfin api key"] = getSettings()["jellyfin api key"]
    settings["plex url"] = request.form.get("plex url", "").strip().rstrip("/")
    # The token field is never pre-filled, so blank means "keep the saved token".
    if request.form.get("clear plex token") == "true":
        settings["plex token"] = ""
    elif not request.form.get("plex token"):
        settings["plex token"] = getSettings()["plex token"]

    settings["recordings folder"] = request.form.get("recordings folder", "").strip()

    saveSettings(settings)
    logger.info("Settings saved!")
    flash("Settings saved!", "success")
    return redirect("/settings", code=302)


@app.route("/settings/jellyfin-setup", methods=["POST"])
@authorise
def jellyfinSetup():
    settings = getSettings()
    if not jellyfinConfigured():
        flash("Save the Jellyfin address and API key first.", "danger")
        return redirect("/settings", code=302)
    try:
        # No Jellyfin-side stream limit: STB-Proxy knows what each portal account allows.
        message = jellyfin.setup(settings["jellyfin url"], settings["jellyfin api key"], "http://" + host)
        logger.info(message)
        flash(message + ".", "success")
    except jellyfin.JellyfinError as e:
        logger.error("Jellyfin setup failed: {}".format(e))
        flash("Couldn't set up Jellyfin: {}".format(e), "danger")
    return redirect("/settings", code=302)


@app.route("/settings/api-token", methods=["POST"])
@authorise
def newApiToken():
    settings = dict(getSettings())
    settings["api token"] = secrets.token_urlsafe(24)
    saveSettings(settings)
    logger.info("New API token made; the old one no longer works")
    flash("New API token made. Update it wherever you use the API (e.g. Home Assistant).", "success")
    return redirect("/settings", code=302)


@app.route("/playlist", methods=["GET"])
@authorise
def playlist():
    channels = []
    portals = getPortals()
    for portal in portals:
        if portals[portal]["enabled"] == "true":
            enabledChannels = availability.availableChannels(portals[portal], getBlocks())
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                proxy = portals[portal]["proxy"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customGenres = portals[portal].get("custom genres", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})
                customEpgIds = portals[portal].get("custom epg ids", {})

                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        stb.getProfile(url, mac, token, proxy)
                        allChannels = stb.getAllChannels(url, mac, token, proxy)
                        genres = stb.getGenreNames(url, mac, token, proxy)
                        break
                    except:
                        allChannels = None
                        genres = None

                if allChannels and genres:
                    matched = matchedLogos(portal, allChannels, genres)
                    for channel in allChannels:
                        channelId = str(channel.get("id"))
                        if channelId in enabledChannels:
                            logo = channelLogo(portals[portal], channelId, channel.get("logo"), matched)
                            channelName = customChannelNames.get(channelId)
                            if channelName == None:
                                channelName = str(channel.get("name"))
                            genre = customGenres.get(channelId)
                            if genre == None:
                                genreId = str(channel.get("tv_genre_id"))
                                genre = str(genres.get(genreId))
                            channelNumber = customChannelNumbers.get(channelId)
                            if channelNumber == None:
                                channelNumber = str(channel.get("number"))
                            epgId = customEpgIds.get(channelId)
                            if epgId == None:
                                epgId = defaultEpgId(portal, channelId)
                            channels.append(
                                "#EXTINF:-1"
                                + ' tvg-id="'
                                + epgId
                                + ('" tvg-logo="' + logo.replace('"', "%22") if logo else "")
                                + (
                                    '" tvg-chno="' + channelNumber
                                    if getSettings().get("use channel numbers", "true")
                                    == "true"
                                    else ""
                                )
                                + (
                                    '" group-title="' + genre
                                    if getSettings().get("use channel genres", "true")
                                    == "true"
                                    else ""
                                )
                                + '",'
                                + channelName
                                + "\n"
                                + "http://"
                                + host
                                + "/play/"
                                + portal
                                + "/"
                                + channelId
                            )
                else:
                    logger.error("Error making playlist for {}, skipping".format(name))

    if getSettings().get("sort playlist by channel name", "true") == "true":
        # The name follows the last '",' of the #EXTINF line (a logo URL may hold commas).
        channels.sort(key=lambda k: k.split("\n")[0].rsplit('",', 1)[1])
    if getSettings().get("use channel numbers", "true") == "true":
        if getSettings().get("sort playlist by channel number", "false") == "true":
            channels.sort(key=lambda k: k.split('tvg-chno="')[1].split('"')[0])
    if getSettings().get("use channel genres", "true") == "true":
        if getSettings().get("sort playlist by channel genre", "false") == "true":
            channels.sort(key=lambda k: k.split('group-title="')[1].split('"')[0])

    playlist = "#EXTM3U \n"
    playlist = playlist + "\n".join(channels)

    return Response(playlist, mimetype="text/plain")


@app.route("/xmltv", methods=["GET"])
@authorise
def xmltv():
    # The bulk EPG takes a few hundred MB to parse: never build this and the guide at once.
    with guideLock:
        return buildXmltv()


def buildXmltv():
    channels = ET.Element("tv")
    programmes = ET.Element("tv")
    portals = getPortals()
    for portal in portals:
        if portals[portal]["enabled"] == "true":
            enabledChannels = availability.availableChannels(portals[portal], getBlocks())
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                proxy = portals[portal]["proxy"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customEpgIds = portals[portal].get("custom epg ids", {})

                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        stb.getProfile(url, mac, token, proxy)
                        allChannels = stb.getAllChannels(url, mac, token, proxy)
                        genres = stb.getGenreNames(url, mac, token, proxy)
                        epg = stb.getEpg(url, mac, token, 24, proxy)
                        if not epg:
                            epg = stb.getShortEpg(url, mac, token, enabledChannels, proxy)
                        break
                    except:
                        allChannels = None
                        epg = None

                if allChannels and epg:
                    matched = matchedLogos(portal, allChannels, genres)
                    for c in allChannels:
                        try:
                            channelId = c.get("id")
                            if str(channelId) in enabledChannels:
                                channelName = customChannelNames.get(str(channelId))
                                if channelName == None:
                                    channelName = str(c.get("name"))
                                epgId = customEpgIds.get(channelId)
                                if epgId == None:
                                    epgId = defaultEpgId(portal, channelId)
                                channelEle = ET.SubElement(
                                    channels, "channel", id=epgId
                                )
                                ET.SubElement(
                                    channelEle, "display-name"
                                ).text = channelName
                                logo = channelLogo(portals[portal], str(channelId), c.get("logo"), matched)
                                if logo:
                                    ET.SubElement(channelEle, "icon", src=logo)
                                for p in epg.get(channelId) or []:
                                    try:
                                        start = (
                                            datetime.utcfromtimestamp(
                                                int(p.get("start_timestamp"))
                                            ).strftime("%Y%m%d%H%M%S")
                                            + " +0000"
                                        )
                                        stop = (
                                            datetime.utcfromtimestamp(
                                                int(p.get("stop_timestamp"))
                                            ).strftime("%Y%m%d%H%M%S")
                                            + " +0000"
                                        )
                                        programmeEle = ET.SubElement(
                                            programmes,
                                            "programme",
                                            start=start,
                                            stop=stop,
                                            channel=epgId,
                                        )
                                        ET.SubElement(
                                            programmeEle, "title"
                                        ).text = p.get("name")
                                        ET.SubElement(
                                            programmeEle, "desc"
                                        ).text = p.get("descr")
                                    except:
                                        pass
                        except:
                            pass
                else:
                    logger.error("Error making XMLTV for {}, skipping".format(name))

    xmltv = channels
    for programme in programmes.iter("programme"):
        xmltv.append(programme)

    return Response(
        ET.tostring(xmltv, encoding="unicode", xml_declaration=True),
        mimetype="text/xml",
    )


# One portal connection per channel: a request for a channel that's already streaming
# (from Plex, Jellyfin, an app or a browser preview) joins that stream instead of opening
# another, since portals limit connections per account.
SHARE_GRACE = 5  # seconds an unwatched shared stream stays open, for a quick reconnect
# Chunks (ffmpeg writes about 32 KB at a time) a viewer may fall behind before it's
# dropped: room for the burst a stream starts with, several seconds of 4K the portal
# had buffered. Memory is only used while a viewer is behind.
VIEWER_BACKLOG = 2048
sharedStreams = {}
sharedStreamsLock = threading.Lock()
# Each kind of viewer's claim on a tuner: a new channel may stop streams whose viewers all
# have a lower claim. Plex and other players come first, then recordings, then previews.
KIND_PRIORITY = {"preview": 0, "recording": 1, "client": 2}
TUNER_BUSY = recordings.TUNER_BUSY
# Why a tile's last preview ended or didn't start, by (viewer id, tile id), so the page can
# say: "busy" (no free tuner) or the kind of viewer that needed its tuner.
previewOutcomes = {}
OUTCOME_KEEP = 600  # seconds
admissionLock = threading.Lock()
# Previews still connecting to the portal, by (viewer id, tile id): (stream, viewer), so a
# tile that changes channel again before the last one started can give that one up.
pendingPreviews = {}


class SharedStream:
    """One ffmpeg reading a channel, its output copied to every viewer of that channel."""

    def __init__(self, key):
        self.key = key
        self.viewers = []
        self.lock = threading.Lock()
        self.process = None
        self.done = False
        self.idleSince = None
        self.entry = None  # its line in `occupied`
        self.onEnd = None
        self.created = time.time()
        self.closing = False  # being stopped to free its tuner: nobody new may join

    def join(self, ip, kind="client", tile=None):
        """kind: "client" (Plex, Jellyfin, apps), "recording" or "preview"; tile: a preview's
        (viewer id, tile id)."""
        viewer = {"queue": queue.Queue(VIEWER_BACKLOG), "ip": ip, "kind": kind, "tile": tile}
        with self.lock:
            if self.done or self.closing:
                return None
            self.viewers.append(viewer)
            self.idleSince = None
            self.count()
        return viewer

    def leave(self, viewer, linger=True):
        """linger: keep the stream open SHARE_GRACE seconds if that was its last viewer, in
        case it comes back; otherwise close it at once."""
        with self.lock:
            if viewer in self.viewers:
                self.viewers.remove(viewer)
            last = not self.viewers
            if last:
                self.idleSince = time.time()
            self.count()
        if last and not linger and self.process is not None:
            self.end()

    def count(self):
        if self.entry is not None:
            self.entry["viewers"] = len(self.viewers)
            self.entry["kinds"] = sorted({v["kind"] for v in self.viewers})

    def priority(self):
        """The highest claim among its viewers; a stream nobody watches has the lowest."""
        with self.lock:
            return max((KIND_PRIORITY[v["kind"]] for v in self.viewers), default=0)

    def start(self, cmd, entry, onEnd):
        """Start reading the channel. False if it was stopped while it was connecting."""
        with self.lock:
            if self.done or self.closing:
                return False
            self.entry, self.onEnd = entry, onEnd
            self.count()
            self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=self.pump, daemon=True).start()
        return True

    def abandon(self, viewer):
        """A viewer gave up while the stream was still connecting; stop connecting if it was the only one."""
        with self.lock:
            if viewer in self.viewers:
                self.viewers.remove(viewer)
            unwanted = not self.viewers and self.process is None
            self.count()
        if unwanted:
            self.end()

    def closeForRoom(self, kind):
        """Mark it closing if a viewer of this kind may take its tuner: only streams that
        nobody but previews watches can be stopped, and previews can't stop them. Returns
        its preview tiles, or None if it must stay."""
        with self.lock:
            if self.done:
                return []
            claim = max((KIND_PRIORITY[v["kind"]] for v in self.viewers), default=KIND_PRIORITY["preview"])
            if claim > KIND_PRIORITY["preview"] or KIND_PRIORITY[kind] <= claim:
                return None
            self.closing = True
            return [v["tile"] for v in self.viewers if v["tile"]]

    def pump(self):
        failed = False
        try:
            while True:
                chunk = self.process.stdout.read1(65536)
                if not chunk:
                    failed = self.process.wait(5) != 0
                    break
                with self.lock:
                    viewers = list(self.viewers)
                    idle = self.idleSince is not None and time.time() - self.idleSince > SHARE_GRACE
                if idle:
                    break  # nobody has watched for a while
                for viewer in viewers:
                    try:
                        viewer["queue"].put_nowait(chunk)
                    except queue.Full:
                        logger.info("A viewer ({}) fell too far behind Portal({}):Channel({}) and was dropped".format(viewer["ip"], *self.key))
                        self.leave(viewer)  # too far behind: let the others carry on
                        # Let go of its backlog now: a browser that stopped reading may keep
                        # its connection (and this queue) for many minutes.
                        backlog = viewer["queue"]
                        with backlog.mutex:
                            backlog.queue.clear()
                        backlog.put_nowait(None)
        except Exception:
            failed = True
        finally:
            self.end(failed)

    def end(self, failed=False):
        with self.lock:
            if self.done:
                return
            self.done = True
            viewers = list(self.viewers)
        if self.process:
            self.process.kill()
            self.process.wait()
        with sharedStreamsLock:
            if sharedStreams.get(self.key) is self:
                del sharedStreams[self.key]
        for viewer in viewers:
            try:
                viewer["queue"].put_nowait(None)
            except queue.Full:
                pass
        if self.onEnd:
            self.onEnd(failed)


def watchShared(stream, viewer):
    try:
        while True:
            try:
                chunk = viewer["queue"].get(timeout=30)
            except queue.Empty:
                break
            if chunk is None:
                break
            yield chunk
    finally:
        stream.leave(viewer)


# Browsers play fragmented MP4, so a preview remuxes its copy of the shared stream here.
# Half-second fragments as well as one per keyframe: the browser can start once it has a
# whole fragment, and keyframes can be seconds apart.
PREVIEW_REMUX = [
    "ffmpeg", "-loglevel", "panic", "-hide_banner", "-f", "mpegts", "-i", "pipe:0",
    "-vcodec", "copy", "-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
    "-frag_duration", "500000", "pipe:1",
]


def watchPreview(stream, viewer, tile):
    """A browser preview of a shared stream, as fragmented MP4, in tile (viewer id, tile id).
    The tile's next preview stops it (see stopPreview), and the stream closes at once if
    nobody else watches."""
    previewOutcomes.pop(tile, None)  # it's playing: nothing to explain
    preview = {
        "stop": threading.Event(),
        "process": None,
        "leave": lambda: stream.leave(viewer, linger=False),  # the next channel may need the connection now
    }
    previews[tile] = preview
    remux = None
    try:
        remux = subprocess.Popen(PREVIEW_REMUX, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        preview["process"] = remux
        threading.Thread(target=feedPreview, args=(viewer, remux, preview), daemon=True).start()
        while not preview["stop"].is_set():
            chunk = remux.stdout.read1(65536)
            if not chunk:
                break
            yield chunk
    finally:
        if remux:
            remux.kill()
            remux.wait()
        preview["leave"]()
        try:
            viewer["queue"].put_nowait(None)  # let feedPreview finish
        except queue.Full:
            pass
        if previews.get(tile) is preview:
            previews.pop(tile, None)


def feedPreview(viewer, remux, preview):
    try:
        while not preview["stop"].is_set():
            try:
                chunk = viewer["queue"].get(timeout=30)
            except queue.Empty:
                break
            if chunk is None:
                break
            remux.stdin.write(chunk)
            remux.stdin.flush()
    except (OSError, ValueError):
        pass  # the preview stopped
    finally:
        try:
            remux.stdin.close()
        except (OSError, ValueError):
            pass


def ffmpegCommand(link, proxy, realTime=True):
    """The ffmpeg command from Settings for a stream at link, as a list."""
    cmd = str(getSettings()["ffmpeg command"]).replace("<url>", link)
    cmd = cmd.replace("<timeout>", str(int(getSettings()["ffmpeg timeout"]) * int(1000000)))
    if proxy:
        cmd = cmd.replace("<proxy>", proxy)
    else:
        cmd = cmd.replace("-http_proxy <proxy>", "")
    cmd = cmd.split()
    if not realTime:
        # Without -re ffmpeg passes on what the portal has buffered at once, so a
        # preview starts sooner; after that a live stream comes in real time anyway.
        cmd = [part for part in cmd if part != "-re"]
    return cmd


def startShared(shared, cmd, portalId, portalName, mac, channelId, channelName, ip):
    """Start shared reading the channel. False if it was stopped while it was connecting."""
    entry = {
        "mac": mac,
        "channel id": channelId,
        "channel name": channelName,
        "client": ip,
        "portal name": portalName,
        "start time": datetime.now(timezone.utc).timestamp(),
    }
    occupied.setdefault(portalId, []).append(entry)
    logger.info("Occupied Portal({}):MAC({})".format(portalId, mac))

    def onEnd(failed):
        entries = occupied.get(portalId, [])
        for i, e in enumerate(entries):
            if e is entry:
                del entries[i]
                break
        logger.info("Unoccupied Portal({}):MAC({})".format(portalId, mac))
        if failed:
            logger.info("Ffmpeg closed with error. Moving MAC({}) for Portal({})".format(mac, portalName))
            moveMac(portalId, mac)

    if not shared.start(cmd, entry, onEnd):
        onEnd(False)
        return False
    return True


def stopPreview(tile):
    """Stop the preview playing (or still connecting) in tile, (viewer id, tile id), so its
    portal connection is free."""
    pending = pendingPreviews.pop(tile, None)
    if pending:
        stream, viewer = pending
        stream.abandon(viewer)
    preview = previews.pop(tile, None)
    if not preview:
        return
    preview["stop"].set()
    process = preview["process"]
    if process:
        process.kill()
    # Here rather than waiting for the preview's response to notice: it may be stuck
    # sending to the browser.
    preview["leave"]()


def tunerCount():
    """The Tuners setting: how many channels may be open at once, across all portals."""
    try:
        return max(1, int(getSettings()["hdhr tuners"]))
    except (KeyError, TypeError, ValueError):
        return 1


def portalHasFreeSlot(portalId):
    portal = getPortals()[portalId]
    perMac = int(portal.get("streams per mac"))
    if perMac == 0:
        return True
    entries = occupied.get(portalId, [])
    return any(sum(1 for e in entries if e["mac"] == mac) < perMac for mac in portal["macs"])


def noteOutcome(tile, reason):
    now = time.time()
    for key in [k for k, v in previewOutcomes.items() if now - v["time"] > OUTCOME_KEEP]:
        previewOutcomes.pop(key, None)
    previewOutcomes[tile] = {"reason": reason, "time": now}


def stopForRoom(stream, kind):
    """Stop stream so a viewer of this kind can have its tuner, telling its previews why.
    False if someone it may not stop started watching it meanwhile."""
    tiles = stream.closeForRoom(kind)
    if tiles is None:
        return False
    logger.info("Stopping Portal({}):Channel({}) to free a tuner for a {}".format(stream.key[0], stream.key[1], kind))
    for tile in tiles:
        noteOutcome(tile, kind)
        stopPreview(tile)
    stream.end()
    return True


def makeRoom(portalId, kind, starting):
    """Make sure a new channel for a viewer of this kind fits within the Tuners setting and
    the portal's streams per MAC, stopping streams with a lower claim, oldest first, if it
    doesn't. starting is the new channel's own shared stream. True if it fits."""
    with admissionLock:
        while True:
            with sharedStreamsLock:
                others = [s for s in sharedStreams.values() if s is not starting and not s.done]
            tunersFull = len(others) >= tunerCount()
            portalFull = not portalHasFreeSlot(portalId)
            if not tunersFull and not portalFull:
                return True
            # Only streams nobody but previews watches (or nobody at all), including ones
            # still connecting; and only for a recording or a player.
            victims = [
                s for s in others
                if s.priority() == KIND_PRIORITY["preview"] < KIND_PRIORITY[kind]
                and (not portalFull or s.key[0] == portalId)
            ]
            if not victims:
                return False
            stopForRoom(min(victims, key=lambda s: s.created), kind)


@app.route("/play/<portalId>/<channelId>", methods=["GET"])
def channel(portalId, channelId):
    try:
        return playChannel(portalId, channelId)
    finally:
        # A shared stream set up for this request that never started: let anyone who
        # joined it in the meantime go, and stop others joining it.
        shared = flask.g.pop("startingShare", None)
        if shared is not None:
            for tile, (stream, _) in list(pendingPreviews.items()):
                if stream is shared:
                    pendingPreviews.pop(tile, None)
            if shared.process is None:
                shared.end()


@app.route("/preview/status", methods=["GET"])
@authorise
def previewStatus():
    """Why a tile's last preview stopped or didn't start, if STB-Proxy knows."""
    tile = (request.args.get("viewer") or request.remote_addr, request.args.get("tile") or "player")
    outcome = previewOutcomes.get(tile)
    fresh = outcome is not None and time.time() - outcome["time"] < OUTCOME_KEEP
    return flask.jsonify({"reason": outcome["reason"] if fresh else None})


def playChannel(portalId, channelId):
    def streamData():
        def occupy():
            occupied.setdefault(portalId, [])
            occupied.get(portalId, []).append(
                {
                    "mac": mac,
                    "channel id": channelId,
                    "channel name": channelName,
                    "client": ip,
                    "portal name": portalName,
                    "start time": startTime,
                }
            )
            logger.info("Occupied Portal({}):MAC({})".format(portalId, mac))

        def unoccupy():
            occupied.get(portalId, []).remove(
                {
                    "mac": mac,
                    "channel id": channelId,
                    "channel name": channelName,
                    "client": ip,
                    "portal name": portalName,
                    "start time": startTime,
                }
            )
            logger.info("Unoccupied Portal({}):MAC({})".format(portalId, mac))

        try:
            startTime = datetime.now(timezone.utc).timestamp()
            occupy()
            with subprocess.Popen(
                ffmpegcmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ) as ffmpeg_sp:
                while True:
                    chunk = ffmpeg_sp.stdout.read(1024)
                    if len(chunk) == 0:
                        if ffmpeg_sp.poll() != 0:
                            logger.info("Ffmpeg closed with error({}). Moving MAC({}) for Portal({})".format(str(ffmpeg_sp.poll()), mac, portalName))
                            moveMac(portalId, mac)
                        break
                    yield chunk
        except:
            pass
        finally:
            unoccupy()
            ffmpeg_sp.kill()

    def testStream():
        timeout = int(getSettings()["ffmpeg timeout"]) * int(1000000)
        ffprobecmd = ["ffprobe", "-timeout", str(timeout), "-i", link]

        if proxy:
            ffprobecmd.insert(1, "-http_proxy")
            ffprobecmd.insert(2, proxy)

        with subprocess.Popen(
            ffprobecmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as ffprobe_sb:
            ffprobe_sb.communicate()
            if ffprobe_sb.returncode == 0:
                return True
            else:
                return False

    def isMacFree():
        count = 0
        for i in occupied.get(portalId, []):
            if i["mac"] == mac:
                count = count + 1
        if count < streamsPerMac:
            return True
        else:
            return False

    portal = getPortals().get(portalId)
    portalName = portal.get("name")
    url = portal.get("url")
    macs = list(portal["macs"].keys())
    streamsPerMac = int(portal.get("streams per mac"))
    proxy = portal.get("proxy")
    web = request.args.get("web")
    recording = request.args.get("recording")
    kind = "preview" if web else "recording" if recording else "client"
    ip = request.remote_addr
    # Each browser sends its own ID: behind a reverse proxy every viewer has the proxy's IP.
    viewer = request.args.get("viewer") or ip
    tile = (viewer, request.args.get("tile") or "player") if web else None

    logger.info(
        "IP({}) requested Portal({}):Channel({})".format(ip, portalId, channelId)
    )

    if web:
        stopPreview(tile)
        previewOutcomes.pop(tile, None)  # a new try: whatever stopped the last one may be over

    channelName = None  # set once a MAC is free; the fallback search below reads it
    shared = None
    if web or recording or getSettings().get("stream method", "ffmpeg") == "ffmpeg":
        key = (portalId, channelId)
        with sharedStreamsLock:
            existing = sharedStreams.get(key)
            if existing is not None and not existing.done:
                joined = existing.join(ip, kind, tile)
                if joined:
                    logger.info("IP({}) shares the stream already open for Portal({}):Channel({})".format(ip, portalId, channelId))
                    if web:
                        return Response(watchPreview(existing, joined, tile), mimetype="application/octet-stream")
                    return Response(watchShared(existing, joined), mimetype="application/octet-stream")
            shared = SharedStream(key)
            sharedStreams[key] = shared
        flask.g.startingShare = shared
        firstViewer = shared.join(ip, kind, tile)
        if not makeRoom(portalId, kind, shared):
            logger.info("No free tuner for Portal({}):Channel({})".format(portalId, channelId))
            if tile:
                noteOutcome(tile, "busy")
            return flask.jsonify({"error": TUNER_BUSY}), 503
        if tile:
            pendingPreviews[tile] = (shared, firstViewer)

    freeMac = False

    for mac in macs:
        channels = None
        cmd = None
        link = None
        if streamsPerMac == 0 or isMacFree():
            logger.info(
                "Trying Portal({}):MAC({}):Channel({})".format(portalId, mac, channelId)
            )
            freeMac = True
            token = stb.getToken(url, mac, proxy)
            if token:
                stb.getProfile(url, mac, token, proxy)
                channels = stb.getAllChannels(url, mac, token, proxy)
                if channels and not any(str(c["id"]) == channelId for c in channels):
                    # The cached list may be older than the channel.
                    channels = stb.getAllChannels(url, mac, token, proxy, refresh=True)

        if channels:
            for c in channels:
                if str(c["id"]) == channelId:
                    channelName = portal.get("custom channel names", {}).get(channelId)
                    if channelName == None:
                        channelName = c["name"]
                    cmd = c["cmd"]
                    break

        if cmd:
            if "http://localhost/" in cmd:
                link = stb.getLink(url, mac, token, cmd, proxy)
            else:
                link = cmd.split(" ")[1]

        if link:
            # Previews skip the test: the browser retries, then offers Mark dead, by itself.
            if web or getSettings().get("test streams", "true") == "false" or testStream():
                if web:
                    cmd = ffmpegCommand(link, proxy, realTime=False)
                    if not startShared(shared, cmd, portalId, portalName, mac, channelId, channelName, ip):
                        return flask.jsonify({"error": TUNER_BUSY}), 503  # stopped while connecting
                    return Response(watchPreview(shared, firstViewer, tile), mimetype="application/octet-stream")

                else:
                    if recording or getSettings().get("stream method", "ffmpeg") == "ffmpeg":
                        cmd = ffmpegCommand(link, proxy)
                        if not startShared(shared, cmd, portalId, portalName, mac, channelId, channelName, ip):
                            return flask.jsonify({"error": TUNER_BUSY}), 503  # stopped while connecting
                        return Response(watchShared(shared, firstViewer), mimetype="application/octet-stream")
                    else:
                        logger.info("Redirect sent")
                        return redirect(link)

        logger.info(
            "Unable to connect to Portal({}) using MAC({})".format(portalId, mac)
        )
        logger.info("Moving MAC({}) for Portal({})".format(mac, portalName))
        moveMac(portalId, mac)

        if not getSettings().get("try all macs", "false") == "true":
            break

    if not web:
        logger.info(
            "Portal({}):Channel({}) is not working. Looking for fallbacks...".format(
                portalId, channelId
            )
        )

        portals = getPortals()
        for portal in portals:
            if portals[portal]["enabled"] == "true":
                fallbackChannels = portals[portal]["fallback channels"]
                if channelName in fallbackChannels.values():
                    url = portals[portal].get("url")
                    macs = list(portals[portal]["macs"].keys())
                    proxy = portals[portal].get("proxy")
                    for mac in macs:
                        channels = None
                        cmd = None
                        link = None
                        if streamsPerMac == 0 or isMacFree():
                            for k, v in fallbackChannels.items():
                                if v == channelName:
                                    try:
                                        token = stb.getToken(url, mac, proxy)
                                        stb.getProfile(url, mac, token, proxy)
                                        channels = stb.getAllChannels(
                                            url, mac, token, proxy
                                        )
                                    except:
                                        logger.info(
                                            "Unable to connect to fallback Portal({}) using MAC({})".format(
                                                portalId, mac
                                            )
                                        )
                                    if channels:
                                        fChannelId = k
                                        for c in channels:
                                            if str(c["id"]) == fChannelId:
                                                cmd = c["cmd"]
                                                break
                                        if cmd:
                                            if "http://localhost/" in cmd:
                                                link = stb.getLink(
                                                    url, mac, token, cmd, proxy
                                                )
                                            else:
                                                link = cmd.split(" ")[1]
                                            if link:
                                                if testStream():
                                                    logger.info(
                                                        "Fallback found for Portal({}):Channel({})".format(
                                                            portalId, channelId
                                                        )
                                                    )
                                                    if (
                                                        getSettings().get(
                                                            "stream method", "ffmpeg"
                                                        )
                                                        == "ffmpeg"
                                                    ):
                                                        ffmpegcmd = str(
                                                            getSettings()[
                                                                "ffmpeg command"
                                                            ]
                                                        )
                                                        ffmpegcmd = ffmpegcmd.replace(
                                                            "<url>", link
                                                        )
                                                        ffmpegcmd = ffmpegcmd.replace(
                                                            "<timeout>",
                                                            str(
                                                                int(
                                                                    getSettings()[
                                                                        "ffmpeg timeout"
                                                                    ]
                                                                )
                                                                * int(1000000)
                                                            ),
                                                        )
                                                        if proxy:
                                                            ffmpegcmd = (
                                                                ffmpegcmd.replace(
                                                                    "<proxy>", proxy
                                                                )
                                                            )
                                                        else:
                                                            ffmpegcmd = ffmpegcmd.replace(
                                                                "-http_proxy <proxy>",
                                                                "",
                                                            )
                                                        " ".join(
                                                            ffmpegcmd.split()
                                                        )  # cleans up multiple whitespaces
                                                        ffmpegcmd = ffmpegcmd.split()
                                                        return Response(
                                                            streamData(),
                                                            mimetype="application/octet-stream",
                                                        )
                                                    else:
                                                        logger.info("Redirect sent")
                                                        return redirect(link)

    if freeMac:
        logger.info(
            "No working streams found for Portal({}):Channel({})".format(
                portalId, channelId
            )
        )
    else:
        logger.info(
            "No free MAC for Portal({}):Channel({})".format(portalId, channelId)
        )

    return make_response("No streams available", 503)


ACTIVITY_WINDOW = 24 * 3600
NOW_PLAYING_TYPES = {"1": "TV", "2": "Video", "3": "Karaoke", "4": "Audio", "5": "Radio"}


def macActivity(portal, mac):
    """What the portal has told us about other use of this MAC, from our profile requests."""
    log = stb.profileLog.get((portal["url"], mac))
    if not log:
        return {"mac": mac, "checked": None}
    profile = log["profile"]
    timezone = log["timezone"]
    now = time.time()
    watchdog = stb.portalTime(profile.get("last_watchdog"), timezone)
    try:
        timeout = int(profile.get("watchdog_timeout") or 900)
    except ValueError:
        timeout = 900
    content = re.sub(r"<[^>]+>", "", str(profile.get("now_playing_content") or ""))
    content = re.sub(r"^\w+:\s*", "", content)
    content = re.sub(r"\s+from\s+\d{4}-.*$", "", content).strip()
    return {
        "mac": mac,
        "checked": log.get("checked"),
        # Logins by other devices or apps (another STB-Proxy, a box) since we started watching.
        "otherLogins": [t for t in log["others"] if now - t < ACTIVITY_WINDOW],
        "watchingSince": log["ours"][0] if log["ours"] else None,
        # Only a real box or emulator checks in, so a recent check-in means one is on.
        "boxCheckIn": watchdog,
        "boxOn": bool(watchdog and log["checked"] - watchdog < timeout),
        "boxWatching": content,
        "boxWatchingType": NOW_PLAYING_TYPES.get(str(profile.get("now_playing_type")), ""),
        "boxWatchingSince": stb.portalTime(profile.get("now_playing_start"), timezone),
    }


@app.route("/account/activity", methods=["GET"])
@authorise
def accountActivity():
    portals = getPortals()
    return flask.jsonify([
        {"portal": portals[p]["name"], "macs": [macActivity(portals[p], mac) for mac in portals[p]["macs"]]}
        for p in portals if portals[p]["enabled"] == "true"
    ])


@app.route("/account/check", methods=["POST"])
@authorise
def accountCheck():
    """Ask the portal now (one profile request per MAC; a login only if ours has expired)."""
    for portal in getPortals().values():
        if portal["enabled"] != "true":
            continue
        for mac in portal["macs"]:
            token = stb.getToken(portal["url"], mac, portal["proxy"])
            if token:
                stb.getProfile(portal["url"], mac, token, portal["proxy"], refresh=True)
    return accountActivity()


# Named filters for the editor and guide pages, kept in config.json so every browser sees them.
FILTER_PAGES = ("editor", "guide")


@app.route("/filters/<page>", methods=["GET"])
@authorise
def savedFilters(page):
    if page not in FILTER_PAGES:
        return flask.jsonify({"error": "Unknown page"}), 404
    return flask.jsonify(getSavedFilters().get(page, {}))


@app.route("/filters/<page>", methods=["POST"])
@authorise
def saveFilter(page):
    data = request.get_json(force=True, silent=True) or {}
    name = str(data.get("name", "")).strip()[:60]
    filters = data.get("filters")
    if page not in FILTER_PAGES or not name or not isinstance(filters, dict) or len(json.dumps(filters)) > 4000:
        return flask.jsonify({"error": "Give a name and the filters to save"}), 400
    saved = json.loads(json.dumps(getSavedFilters()))
    pageFilters = saved.setdefault(page, {})
    if data.get("delete"):
        pageFilters.pop(name, None)
    else:
        pageFilters[name] = filters
    saveSavedFilters(saved)
    return flask.jsonify(pageFilters)


# ---- API for integrations such as Home Assistant. JSON in and out, and every call needs
# the API token from Settings: "Authorization: Bearer <token>" (or an "X-API-Key" header).
def apiAuth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = getSettings()["api token"]
        given = request.headers.get("X-API-Key") or ""
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            given = auth[7:].strip()
        if not token or not secrets.compare_digest(given, token):
            return flask.jsonify({"error": "Missing or wrong API token (see Settings)"}), 401
        return f(*args, **kwargs)

    return decorated


def plexStatus():
    return {
        "configured": plexConfigured(),
        "ok": lastPlexSync["ok"],
        "message": lastPlexSync["message"],
        "time": lastPlexSync["time"],
        "retryAt": syncRetry["at"],
    }


def jellyfinStatus():
    return {
        "configured": jellyfinConfigured(),
        "ok": lastJellyfinSync["ok"],
        "message": lastJellyfinSync["message"],
        "time": lastJellyfinSync["time"],
        "retryAt": syncRetry["at"],
    }


def blockStates():
    """Every block the API shows: hidden ones are left out."""
    return [
        {"name": b["name"], "enabled": b["enabled"], "channels": b["channels"], "dead": b["dead"]}
        for b in availability.blockSummaries(getPortals(), getBlocks(), getHiddenBlocks())
        if not b["hidden"]
    ]


def findBlock(name):
    """The block called name, ignoring case if there's exactly one such; else None. Hidden blocks aren't found."""
    names = availability.blockNames(getPortals()) - set(getHiddenBlocks())
    if name in names:
        return name
    matches = [n for n in names if n.lower() == name.lower()]
    return matches[0] if len(matches) == 1 else None


def setBlock(name, enabled):
    blocks = getBlocks()
    changed = (blocks.get(name) == "true") != enabled
    if changed:
        blocks = dict(blocks)
        blocks[name] = "true" if enabled else "false"
        saveBlocks(blocks)
        logger.info("Block({}) switched {} (API)".format(name, "on" if enabled else "off"))
        syncPlex()
    block = next(b for b in blockStates() if b["name"] == name)
    return dict(block, changed=changed, plex=plexStatus(), jellyfin=jellyfinStatus())


@app.route("/api/status", methods=["GET"])
@apiAuth
def apiStatus():
    portals = getPortals()
    blocks = getBlocks()
    lineup = sum(len(availability.availableChannels(portals[p], blocks)) for p in portals if portals[p]["enabled"] == "true")
    activity = [macActivity(portals[p], mac) for p in portals if portals[p]["enabled"] == "true" for mac in portals[p]["macs"]]
    with sharedStreamsLock:
        streams = [s for s in sharedStreams.values() if not s.done]
    viewers = {kind: 0 for kind in KIND_PRIORITY}
    for stream in streams:
        with stream.lock:
            for v in stream.viewers:
                viewers[v["kind"]] += 1
    return flask.jsonify({
        "lineup": lineup,
        "streams": sum(len(v) for v in occupied.values()),
        "tuners": {"total": tunerCount(), "used": len(streams)},
        "viewers": viewers,
        "blocks": blockStates(),
        "plex": plexStatus(),
        "jellyfin": jellyfinStatus(),
        "otherLogins": sum(len(a.get("otherLogins", [])) for a in activity),
        "boxOn": any(a.get("boxOn") for a in activity),
    })


@app.route("/api/blocks", methods=["GET"])
@apiAuth
def apiBlocks():
    return flask.jsonify(blockStates())


@app.route("/api/blocks/<path:name>", methods=["GET", "POST"])
@apiAuth
def apiBlock(name):
    found = findBlock(name)
    if not found:
        return flask.jsonify({"error": "No block called {}".format(name)}), 404
    if request.method == "GET":
        return flask.jsonify(next(b for b in blockStates() if b["name"] == found))
    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data.get("enabled"), bool):
        return flask.jsonify({"error": 'Send {"enabled": true} or {"enabled": false}'}), 400
    return flask.jsonify(setBlock(found, data["enabled"]))


@app.route("/api/blocks/<path:name>/<any(on, off, toggle):action>", methods=["POST"])
@apiAuth
def apiBlockAction(name, action):
    found = findBlock(name)
    if not found:
        return flask.jsonify({"error": "No block called {}".format(name)}), 404
    enabled = {"on": True, "off": False}.get(action, getBlocks().get(found) != "true")
    return flask.jsonify(setBlock(found, enabled))


@app.route("/api/plex", methods=["GET"])
@apiAuth
def apiPlex():
    return flask.jsonify(plexStatus())


@app.route("/api/jellyfin", methods=["GET"])
@apiAuth
def apiJellyfin():
    return flask.jsonify(jellyfinStatus())


@app.route("/api/sync", methods=["POST"])
@app.route("/api/plex/sync", methods=["POST"])
@apiAuth
def apiPlexSync():
    """Sync every configured media server (Plex and Jellyfin) now."""
    syncPlex()
    return flask.jsonify({"plex": plexStatus(), "jellyfin": jellyfinStatus(), **plexStatus()})


@app.route("/dashboard")
@authorise
def dashboard():
    return render_template("dashboard.html")


@app.route("/streaming")
@authorise
def streaming():
    return flask.jsonify(occupied)


@app.route("/log")
@authorise
def log():
    with open("STB-Proxy.log") as f:
        log = f.read()
    return log


# HD Homerun #


def hdhr(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        settings = getSettings()
        security = settings["enable security"]
        username = settings["username"]
        password = settings["password"]
        hdhrenabled = settings["enable hdhr"]
        if (
            security == "false"
            or auth
            and auth.username == username
            and auth.password == password
        ):
            if hdhrenabled:
                return f(*args, **kwargs)
        return make_response("Error", 404)

    return decorated


@app.route("/discover.json", methods=["GET"])
@hdhr
def discover():
    settings = getSettings()
    name = settings["hdhr name"]
    id = settings["hdhr id"]
    tuners = settings["hdhr tuners"]
    data = {
        "BaseURL": host,
        "DeviceAuth": name,
        "DeviceID": id,
        "FirmwareName": "STB-Proxy",
        "FirmwareVersion": "1337",
        "FriendlyName": name,
        "LineupURL": host + "/lineup.json",
        "Manufacturer": "Chris",
        "ModelNumber": "1337",
        "TunerCount": int(tuners),
    }
    return flask.jsonify(data)


@app.route("/lineup_status.json", methods=["GET"])
@hdhr
def status():
    data = {
        "ScanInProgress": 0,
        "ScanPossible": 0,
        "Source": "Antenna",
        "SourceList": ["Antenna"],
    }
    return flask.jsonify(data)


def buildLineup():
    """Every available channel as an HDHomeRun lineup entry plus its XMLTV id.

    Returns (entries, failedPortals). failedPortals names the portals whose
    channel list couldn't be fetched, so callers can tell an empty lineup from
    a failed one.
    """
    entries = []
    failedPortals = []
    portals = getPortals()
    blocks = getBlocks()
    for portal in portals:
        if portals[portal]["enabled"] == "true":
            enabledChannels = availability.availableChannels(portals[portal], blocks)
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                proxy = portals[portal]["proxy"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})
                customEpgIds = portals[portal].get("custom epg ids", {})

                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        stb.getProfile(url, mac, token, proxy)
                        allChannels = stb.getAllChannels(url, mac, token, proxy)
                        break
                    except:
                        allChannels = None

                if allChannels:
                    for channel in allChannels:
                        channelId = str(channel.get("id"))
                        if channelId in enabledChannels:
                            channelName = customChannelNames.get(channelId)
                            if channelName == None:
                                channelName = str(channel.get("name"))
                            channelNumber = customChannelNumbers.get(channelId)
                            if channelNumber == None:
                                channelNumber = str(channel.get("number"))

                            entries.append(
                                {
                                    "GuideNumber": channelNumber,
                                    "GuideName": channelName,
                                    "URL": "http://"
                                    + host
                                    + "/play/"
                                    + portal
                                    + "/"
                                    + channelId,
                                    "epgId": customEpgIds.get(channelId)
                                    or defaultEpgId(portal, channelId),
                                }
                            )
                else:
                    logger.error("Error making lineup for {}, skipping".format(name))
                    failedPortals.append(name)

    return entries, failedPortals


lastPlexSync = {"time": None, "message": "Not synced since STB-Proxy started", "ok": None}
lastJellyfinSync = {"time": None, "message": "Not refreshed since STB-Proxy started", "ok": None}
syncRetry = {"at": None}
# Syncs run one at a time. A failed one is retried in the background (Plex may be restarting)
# after each of these delays in turn, about an hour in all; any new sync starts the count again.
PLEX_RETRY_DELAYS = [60, 120, 300, 600, 900, 1200]
plexSyncLock = threading.Lock()
plexRetry = {"timer": None, "attempt": 0}


def plexConfigured():
    settings = getSettings()
    return bool(settings["plex url"] and settings["plex token"])


def cancelPlexRetry():
    if plexRetry["timer"]:
        plexRetry["timer"].cancel()
    plexRetry["timer"] = None
    syncRetry["at"] = None


def schedulePlexRetry():
    if plexRetry["attempt"] >= len(PLEX_RETRY_DELAYS):
        logger.error("Media servers still not updated after retrying for an hour; giving up until the next change")
        syncRetry["at"] = None
        return
    delay = PLEX_RETRY_DELAYS[plexRetry["attempt"]]
    plexRetry["attempt"] += 1
    timer = threading.Timer(delay, syncPlex, kwargs={"retry": True})
    timer.daemon = True
    plexRetry["timer"] = timer
    syncRetry["at"] = time.time() + delay
    timer.start()
    logger.info("Retrying the media server sync in {} min".format(delay // 60))


def jellyfinConfigured():
    settings = getSettings()
    return bool(settings["jellyfin url"] and settings["jellyfin api key"])


def syncPlex(retry=False):
    """Bring the media servers (Plex's DVR, Jellyfin's Live TV) in step with the available
    channels. Returns (flashCategory, message).

    One sync at a time: callers wait for a running one, then sync again with the latest
    state. If any server fails, all are tried again later (see PLEX_RETRY_DELAYS).
    """
    servers = [run for run, on in ((runPlexSync, plexConfigured()), (runJellyfinSync, jellyfinConfigured())) if on]
    if not servers:
        cancelPlexRetry()
        return "info", "Plex sync is off (add Plex or Jellyfin in Settings)"
    with plexSyncLock:
        if not retry:
            plexRetry["attempt"] = 0
        cancelPlexRetry()
        results = [run() for run in servers]  # each (category, message, retryable)
        failed = any(category != "success" for category, _, _ in results)
        # Retry only what waiting can fix (a server that's down), not a rejected request.
        if any(category != "success" and retryable for category, _, retryable in results):
            schedulePlexRetry()
        return ("danger" if failed else "success"), " ".join(message for _, message, _ in results)


def runJellyfinSync():
    settings = getSettings()
    try:
        message = jellyfin.refresh(settings["jellyfin url"], settings["jellyfin api key"])
        ok, retryable = True, False
    except jellyfin.JellyfinError as e:
        message = "Jellyfin not refreshed: {}".format(e)
        ok, retryable = False, e.retry
    lastJellyfinSync.update({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "message": message, "ok": ok})
    if ok:
        logger.info(message)
        return "success", message, False
    logger.error(message)
    return "danger", message, retryable


def runPlexSync():
    settings = getSettings()
    entries, failedPortals = buildLineup()
    try:
        if failedPortals:
            raise plex.PlexSyncError(
                "couldn't load channels from {}, so Plex was left unchanged".format(
                    ", ".join(failedPortals)
                )
            )
        message = plex.sync(settings["plex url"], settings["plex token"], "http://" + host, entries)
        ok, retryable = True, False
    except plex.PlexSyncError as e:
        message = "Plex not updated: {}".format(e)
        ok, retryable = False, e.retry

    lastPlexSync.update(
        {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "message": message, "ok": ok}
    )
    if ok:
        logger.info(message)
        return "success", message, False
    logger.error(message)
    return "danger", message, retryable


@app.route("/lineup.json", methods=["GET"])
@app.route("/lineup.post", methods=["POST"])
@hdhr
def lineup():
    entries, _ = buildLineup()
    return flask.jsonify(
        [{k: v for k, v in entry.items() if k != "epgId"} for entry in entries]
    )


if __name__ == "__main__":
    config = loadConfig()
    # Carry on recordings that were running when STB-Proxy stopped, once it's listening:
    # they read from its own /play.
    threading.Timer(3, getRecorder().resume).start()
    if any(looksUpLogos(p) for p in config["portals"].values()):
        currentLogoIndex()  # start fetching channel logos in the background
    if config.get("xmltv ids") != "short":
        # Channel guide ids got shorter: once Plex and Jellyfin can reach us, map them again.
        config["xmltv ids"] = "short"
        writeConfig(config)
        threading.Timer(15, syncPlex).start()
    if "TERM_PROGRAM" in os.environ.keys() and os.environ["TERM_PROGRAM"] == "vscode":
        app.run(host="0.0.0.0", port=8001, debug=True)
    else:
        waitress.serve(app, port=8001, _quiet=True, threads=24)