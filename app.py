import flask
import stb
import availability
import plex
import guide
import os
import json
import subprocess
import uuid
import logging
import threading
import time
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
# The browser preview each viewer is watching, by (portal, viewer IP), so picking
# another channel can stop it at once instead of waiting for its connection to close.
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

    settings = data["settings"]
    settingsOut = {}

    for setting, default in defaultSettings.items():
        value = settings.get(setting)
        if not value or type(default) != type(value):
            value = default
        settingsOut[setting] = value

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


def getBlocks():
    return config["blocks"]


def saveBlocks(blocks):
    config["blocks"] = blocks
    writeConfig(config)


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
    return render_template("portals.html", portals=getPortals(), devices=devices)


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
        savePortals(portals)
        logger.info("Portal({}) updated!".format(name))
        flash("Portal({}) updated!".format(name), "success")

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
            fallbackChannels = portals[portal].get("fallback channels", {})
            channelBlocks = portals[portal].get("channel blocks", {})
            deadChannels = portals[portal].get("dead channels", [])
            favouriteChannels = portals[portal].get("favourite channels", [])

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
                            "fallbackChannel": fallbackChannel,
                            "blocks": channelBlocks.get(channelId, []),
                            "dead": channelId in deadChannels,
                            "favourite": channelId in favouriteChannels,
                            "link": "http://"
                            + host
                            + "/play/"
                            + portal
                            + "/"
                            + channelId
                            + "?web=true",
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

    savePortals(portals)
    logger.info("Playlist reset!")
    flash("Playlist reset!", "success")

    return redirect("/editor", code=302)


@app.route("/blocks", methods=["GET"])
@authorise
def blocksPage():
    return render_template(
        "blocks.html",
        blocks=availability.blockSummaries(getPortals(), getBlocks()),
        allBlocks=sorted(availability.blockNames(getPortals())),
        favourites=sum(
            len(p.get("favourite channels", [])) for p in getPortals().values() if p["enabled"] == "true"
        ),
        lastPlexSync=lastPlexSync,
        plexConfigured=plexConfigured(),
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
                channels[(portal, str(c["id"]))] = {"name": str(c["name"]), "number": str(c["number"])}
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


@app.route("/guide", methods=["GET"])
@authorise
def guidePage():
    return render_template("guide.html", allBlocks=sorted(availability.blockNames(getPortals())))


@app.route("/guide/search", methods=["GET"])
@authorise
def guideSearch():
    query = request.args.get("q", "").strip()
    onNow = request.args.get("now") == "true"
    lineupOnly = request.args.get("lineup") == "true"
    favouritesOnly = request.args.get("favourites") == "true"
    hideDead = request.args.get("hideDead", "true") == "true"

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
        return True

    matches, total = [], 0
    if query or onNow or lineupOnly or favouritesOnly:
        matches, total = guide.search(cache["programmes"], query, int(time.time()), keep, onNow)

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
                "dead": channelId in p.get("dead channels", []),
                "favourite": channelId in p.get("favourite channels", []),
                "blocks": p.get("channel blocks", {}).get(channelId, []),
                "available": channelId in available[portal],
                "link": "http://" + host + "/play/" + portal + "/" + channelId + "?web=true",
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

    settings["plex url"] = request.form.get("plex url", "").strip().rstrip("/")
    # The token field is never pre-filled, so blank means "keep the saved token".
    if request.form.get("clear plex token") == "true":
        settings["plex token"] = ""
    elif not request.form.get("plex token"):
        settings["plex token"] = getSettings()["plex token"]

    saveSettings(settings)
    logger.info("Settings saved!")
    flash("Settings saved!", "success")
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
                    for channel in allChannels:
                        channelId = str(channel.get("id"))
                        if channelId in enabledChannels:
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
                                epgId = portal + channelId
                            channels.append(
                                "#EXTINF:-1"
                                + ' tvg-id="'
                                + epgId
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
        channels.sort(key=lambda k: k.split(",")[1].split("\n")[0])
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
                        epg = stb.getEpg(url, mac, token, 24, proxy)
                        if not epg:
                            epg = stb.getShortEpg(url, mac, token, enabledChannels, proxy)
                        break
                    except:
                        allChannels = None
                        epg = None

                if allChannels and epg:
                    for c in allChannels:
                        try:
                            channelId = c.get("id")
                            if str(channelId) in enabledChannels:
                                channelName = customChannelNames.get(str(channelId))
                                if channelName == None:
                                    channelName = str(c.get("name"))
                                epgId = customEpgIds.get(channelId)
                                if epgId == None:
                                    epgId = portal + channelId
                                channelEle = ET.SubElement(
                                    channels, "channel", id=epgId
                                )
                                ET.SubElement(
                                    channelEle, "display-name"
                                ).text = channelName
                                ET.SubElement(channelEle, "icon", src=c.get("logo"))
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


def stopPreview(portalId, ip):
    """Stop this viewer's last preview so its portal connection is free for the next one."""
    preview = previews.get((portalId, ip))
    if not preview:
        return
    preview["stop"].set()
    process = preview["process"]
    if process:
        process.kill()
    preview["done"].wait(3)


@app.route("/play/<portalId>/<channelId>", methods=["GET"])
def channel(portalId, channelId):
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

        preview = None
        if web:
            preview = {"stop": threading.Event(), "done": threading.Event(), "process": None}
            previews[(portalId, ip)] = preview

        def stopped():
            return preview is not None and preview["stop"].is_set()

        try:
            startTime = datetime.now(timezone.utc).timestamp()
            occupy()
            with subprocess.Popen(
                ffmpegcmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ) as ffmpeg_sp:
                if preview:
                    preview["process"] = ffmpeg_sp
                while not stopped():
                    chunk = ffmpeg_sp.stdout.read(1024)
                    if len(chunk) == 0:
                        # A preview stopped for the next channel isn't a fault of the MAC.
                        if ffmpeg_sp.poll() != 0 and not stopped():
                            logger.info("Ffmpeg closed with error({}). Moving MAC({}) for Portal({})".format(str(ffmpeg_sp.poll()), mac, portalName))
                            moveMac(portalId, mac)
                        break
                    yield chunk
        except:
            pass
        finally:
            unoccupy()
            ffmpeg_sp.kill()
            if preview:
                if previews.get((portalId, ip)) is preview:
                    previews.pop((portalId, ip), None)
                preview["done"].set()

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
    ip = request.remote_addr

    logger.info(
        "IP({}) requested Portal({}):Channel({})".format(ip, portalId, channelId)
    )

    if web:
        stopPreview(portalId, ip)

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
                    ffmpegcmd = [
                        "ffmpeg",
                        "-loglevel",
                        "panic",
                        "-hide_banner",
                        "-i",
                        link,
                        "-vcodec",
                        "copy",
                        "-f",
                        "mp4",
                        # Half-second fragments as well as one per keyframe: the browser
                        # can start once it has a whole fragment, and keyframes can be
                        # seconds apart.
                        "-movflags",
                        "frag_keyframe+empty_moov+default_base_moof",
                        "-frag_duration",
                        "500000",
                        "pipe:",
                    ]
                    if proxy:
                        ffmpegcmd.insert(1, "-http_proxy")
                        ffmpegcmd.insert(2, proxy)
                    return Response(streamData(), mimetype="application/octet-stream")

                else:
                    if getSettings().get("stream method", "ffmpeg") == "ffmpeg":
                        ffmpegcmd = str(getSettings()["ffmpeg command"])
                        ffmpegcmd = ffmpegcmd.replace("<url>", link)
                        ffmpegcmd = ffmpegcmd.replace(
                            "<timeout>",
                            str(int(getSettings()["ffmpeg timeout"]) * int(1000000)),
                        )
                        if proxy:
                            ffmpegcmd = ffmpegcmd.replace("<proxy>", proxy)
                        else:
                            ffmpegcmd = ffmpegcmd.replace("-http_proxy <proxy>", "")
                        " ".join(ffmpegcmd.split())  # cleans up multiple whitespaces
                        ffmpegcmd = ffmpegcmd.split()
                        return Response(
                            streamData(), mimetype="application/octet-stream"
                        )
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
                                    or portal + channelId,
                                }
                            )
                else:
                    logger.error("Error making lineup for {}, skipping".format(name))
                    failedPortals.append(name)

    return entries, failedPortals


lastPlexSync = {"time": None, "message": "Not synced since STB-Proxy started", "ok": None}


def plexConfigured():
    settings = getSettings()
    return bool(settings["plex url"] and settings["plex token"])


def syncPlex():
    """Make the Plex DVR match the available channels. Returns (flashCategory, message)."""
    if not plexConfigured():
        return "info", "Plex sync is off (add the Plex address and token in Settings)"

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
        ok = True
    except plex.PlexSyncError as e:
        message = "Plex not updated: {}".format(e)
        ok = False

    lastPlexSync.update(
        {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "message": message, "ok": ok}
    )
    if ok:
        logger.info(message)
        return "success", message
    logger.error(message)
    return "danger", message


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
    if "TERM_PROGRAM" in os.environ.keys() and os.environ["TERM_PROGRAM"] == "vscode":
        app.run(host="0.0.0.0", port=8001, debug=True)
    else:
        waitress.serve(app, port=8001, _quiet=True, threads=24)