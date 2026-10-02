# Channel Blocks, Dead Channels and Plex Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user switch named blocks of channels on and off, mark channels dead while previewing them, and have every change that alters which channels are available update the Plex DVR automatically.

**Architecture:** One pure module (`availability.py`) decides which channels are available. `app.py` uses it everywhere it used to read `"enabled channels"` directly. A new `buildLineup()` produces the HDHomeRun lineup, including each channel's XMLTV id. A small Flask-free `plex.py` turns that lineup into a Plex channel map, sends it, and reloads the guide. The routes and templates add the Blocks page, the Block column, dead marking, and Plex settings.

**Tech Stack:** Python 3.11 (Debian 12 in the LXC), Flask 2.2.2, Werkzeug 2.2.2, requests 2.28.1, Waitress, Bootstrap 5.0.1, jQuery 3.6.0, DataTables 1.11.3, `unittest` with `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-10-02-channel-blocks-design.md`

## Global Constraints

- Runtime: Python 3.11 in LXC 115. Don't use syntax newer than 3.11. Add no new runtime dependencies (the LXC has Debian's `python3-flask`, `python3-requests`, `python3-waitress`).
- Local test environment: `.venv` with `flask==2.2.2 werkzeug==2.2.2 requests==2.28.1 waitress`, matching the LXC.
- Line endings: `stb.py` uses CRLF. `app.py`, templates and all new files use LF. Keep them as they are.
- Style: match `app.py`. camelCase function names, `"...{}".format()` strings, `logger.info` / `logger.error` for events, `flash(message, category)` for user feedback.
- Config flags are strings `"true"` / `"false"`, never booleans.
- A key not declared in `defaultPortal` / `defaultSettings` is dropped by `loadConfig()`. Declare every new key.
- Every new route uses `@authorise`.
- The Plex token is never rendered into any page or JSON response.
- STB-Proxy finds its DVR in Plex by the tuner URI `"http://" + host`, where `host` is the `HOST` env var (`192.168.5.71:8001` in production).
- Availability rule (spec): `(individually enabled OR in a block that is on) AND NOT dead`.

## Review Focus

1. **A portal fails to return its channel list during a sync** (the portal rate-limits and has glitches): Plex must be left unchanged rather than stripped of every channel. Test: Task 4, `test_sync_aborts_when_a_portal_fails`.
2. **No channel available at all** (every block off, nothing enabled): Plex is left unchanged, and the user is told why. Test: Task 3, `test_refuses_empty_lineup`.
3. **Plex unreachable, or the token rejected**: the STB-Proxy change is still saved, and the message says what went wrong. Tests: Task 3, `test_connection_error_*` and `test_rejected_token`; Task 6, `test_toggle_saves_even_when_plex_fails`.
4. **Settings saved with the token field blank** (it is never pre-filled): the saved token is kept. Test: Task 4, `test_blank_token_field_keeps_saved_token`.
5. **Block names with stray spaces or HTML characters**: `"NHL "` and `"NHL"` are the same block, and `<b>` is shown as text. Tests: Task 5, `test_block_names_are_trimmed`; Task 6, `test_block_names_are_escaped`.

---

## File Structure

| File | Responsibility |
|---|---|
| `availability.py` (create) | Pure rules: which channels are available, what blocks exist, block summaries, pruning stale block states. No Flask or IO. |
| `plex.py` (create) | Plex API client: find the DVR for this tuner, build and send the channel map, reload the guide. No Flask. |
| `app.py` (modify) | Config defaults, `getBlocks`/`saveBlocks`, `buildLineup()`, `syncPlex()`, the new routes, and changes to editor, settings, lineup, xmltv and playlist. |
| `templates/blocks.html` (create) | Blocks page. |
| `templates/editor.html` (modify) | Block column, dead badge, "Hide dead" filter, dead marking in the preview pop-up. |
| `templates/settings.html` (modify) | Plex section. |
| `templates/base.html` (modify) | "Blocks" nav item. |
| `tests/__init__.py`, `tests/support.py` (create) | Test package; a helper that imports `app.py` with a temporary config and stubbed portal calls. |
| `tests/test_*.py` (create) | One test file per task. |
| `.gitignore`, `requirements-test.txt` (create) | Ignore `.venv/`, `__pycache__/`, `STB-Proxy.log`; pin the test dependencies. |

Run all tests from the repo root with:

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
```

---

### Task 1: Availability rules and test setup

**Files:**
- Create: `.gitignore`, `requirements-test.txt`, `tests/__init__.py`, `availability.py`
- Test: `tests/test_availability.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`availability.py`):
  - `availableChannels(portal: dict, blocks: dict) -> set[str]`
  - `blockNames(portals: dict) -> set[str]`
  - `pruneBlocks(portals: dict, blocks: dict) -> dict`
  - `blockSummaries(portals: dict, blocks: dict) -> list[dict]`. Each item is `{"name": str, "enabled": bool, "channels": int, "dead": int}`, sorted by name.
  - Types: `portal` is one entry of `config["portals"]`; `blocks` is `config["blocks"]` (`{name: "true"|"false"}`).

- [ ] **Step 1: Create the test environment**

```bash
cd /code/stb-proxy
cat > .gitignore <<'EOF'
.venv/
__pycache__/
STB-Proxy.log
EOF
cat > requirements-test.txt <<'EOF'
# Matches the Debian 12 packages in the LXC.
flask==2.2.2
werkzeug==2.2.2
requests==2.28.1
waitress
EOF
python3 -m venv .venv && .venv/bin/pip install -q -r requirements-test.txt
mkdir -p tests && touch tests/__init__.py
.venv/bin/python -c "import flask, requests, waitress; print(flask.__version__)"
```

Expected: prints `2.2.2`.

- [ ] **Step 2: Write the failing tests**

`tests/test_availability.py`:

```python
import unittest

import availability


def portal(enabled=(), blocks=None, dead=()):
    return {
        "enabled channels": list(enabled),
        "channel blocks": dict(blocks or {}),
        "dead channels": list(dead),
    }


class AvailableChannelsTest(unittest.TestCase):
    def test_individually_enabled(self):
        self.assertEqual(availability.availableChannels(portal(["1", "2"]), {}), {"1", "2"})

    def test_block_on_adds_its_channels(self):
        p = portal(["1"], {"2": "NHL", "3": "NHL"})
        self.assertEqual(availability.availableChannels(p, {"NHL": "true"}), {"1", "2", "3"})

    def test_block_off_or_unknown_adds_nothing(self):
        p = portal(["1"], {"2": "NHL", "3": "NBA"})
        self.assertEqual(availability.availableChannels(p, {"NHL": "false"}), {"1"})

    def test_enabled_channel_stays_when_its_block_is_off(self):
        p = portal(["2"], {"2": "NHL"})
        self.assertEqual(availability.availableChannels(p, {"NHL": "false"}), {"2"})

    def test_dead_channel_hidden_even_if_enabled_and_in_block_that_is_on(self):
        p = portal(["1", "2"], {"2": "NHL", "3": "NHL"}, dead=["2", "3"])
        self.assertEqual(availability.availableChannels(p, {"NHL": "true"}), {"1"})

    def test_missing_keys_mean_nothing_extra(self):
        self.assertEqual(availability.availableChannels({"enabled channels": ["1"]}, {}), {"1"})


class BlocksTest(unittest.TestCase):
    def setUp(self):
        self.portals = {
            "a": portal(blocks={"1": "NHL", "2": "NHL", "3": "NBA"}, dead=["2"]),
            "b": portal(blocks={"9": "NHL"}),
        }

    def test_block_names_across_portals(self):
        self.assertEqual(availability.blockNames(self.portals), {"NHL", "NBA"})

    def test_prune_drops_blocks_no_channel_names(self):
        blocks = {"NHL": "true", "Old": "true", "NBA": "false"}
        self.assertEqual(availability.pruneBlocks(self.portals, blocks), {"NHL": "true", "NBA": "false"})

    def test_summaries_count_channels_and_dead_sorted_by_name(self):
        self.assertEqual(
            availability.blockSummaries(self.portals, {"NHL": "true"}),
            [
                {"name": "NBA", "enabled": False, "channels": 1, "dead": 0},
                {"name": "NHL", "enabled": True, "channels": 3, "dead": 1},
            ],
        )

    def test_no_blocks(self):
        self.assertEqual(availability.blockSummaries({"a": portal()}, {}), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: ERROR `ModuleNotFoundError: No module named 'availability'`

- [ ] **Step 4: Implement `availability.py`**

```python
"""Which channels STB-Proxy offers, given enabled channels, blocks and dead marks.

A channel is available when it is (individually enabled OR in a block that is
on) AND not marked dead. Blocks are named in each portal's "channel blocks"
({channelId: blockName}); whether a block is on lives in config["blocks"]
({blockName: "true"|"false"}).
"""


def availableChannels(portal, blocks):
    channels = set(portal.get("enabled channels", []))
    for channelId, block in portal.get("channel blocks", {}).items():
        if blocks.get(block) == "true":
            channels.add(channelId)
    return channels - set(portal.get("dead channels", []))


def blockNames(portals):
    names = set()
    for portal in portals.values():
        names.update(portal.get("channel blocks", {}).values())
    return names


def pruneBlocks(portals, blocks):
    names = blockNames(portals)
    return {name: state for name, state in blocks.items() if name in names}


def blockSummaries(portals, blocks):
    summaries = {}
    for portal in portals.values():
        dead = set(portal.get("dead channels", []))
        for channelId, name in portal.get("channel blocks", {}).items():
            summary = summaries.setdefault(
                name,
                {"name": name, "enabled": blocks.get(name) == "true", "channels": 0, "dead": 0},
            )
            summary["channels"] += 1
            if channelId in dead:
                summary["dead"] += 1
    return [summaries[name] for name in sorted(summaries)]
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 10 tests, OK.

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements-test.txt tests/__init__.py tests/test_availability.py availability.py
git commit -m "Add channel availability rules for blocks and dead channels"
```

---

### Task 2: Config schema and shared lineup builder

**Files:**
- Modify: `app.py`. The changes are: `defaultSettings`, `defaultPortal`, `loadConfig()`, new `getBlocks`/`saveBlocks` after `saveSettings`, `playlist()`, `xmltv()`, and `lineup()` plus a new `buildLineup()` above it.
- Create: `tests/support.py`
- Test: `tests/test_app_lineup.py`

**Interfaces:**
- Consumes: `availability.availableChannels(portal, blocks)`
- Produces (`app.py`):
  - `getBlocks() -> dict`
  - `saveBlocks(blocks: dict) -> None`
  - `buildLineup() -> tuple[list[dict], list[str]]`. Returns `(entries, failedPortalNames)`. Each entry is `{"GuideNumber": str, "GuideName": str, "URL": str, "epgId": str}`.
  - New config keys: per portal `"channel blocks": {}` and `"dead channels": []`; top level `"blocks": {}`; settings `"plex url": ""` and `"plex token": ""`.
  - `tests/support.py`: `loadApp(testCase, config) -> module`, `portalConfig(**overrides) -> dict`, `PORTAL = "p1"`, `PORTAL_CHANNELS` (channel ids `"1"`, `"2"`, `"3"`, numbers `"101"`, `"102"`, `"103"`).

- [ ] **Step 1: Write the test helper**

`tests/support.py`:

```python
"""Import app.py against a throwaway config, with every portal call stubbed out."""
import importlib
import json
import os
import sys
import tempfile
from unittest import mock

PORTAL = "p1"

PORTAL_CHANNELS = [
    {"id": "1", "name": "One", "number": "101", "tv_genre_id": "9", "logo": ""},
    {"id": "2", "name": "Two", "number": "102", "tv_genre_id": "9", "logo": ""},
    {"id": "3", "name": "Three", "number": "103", "tv_genre_id": "9", "logo": ""},
]


def portalConfig(**overrides):
    portal = {
        "enabled": "true",
        "name": "Test portal",
        "url": "http://portal.test/stalker_portal/server/load.php",
        "macs": {"00:1A:79:00:00:01": "10.19.2026"},
        "streams per mac": "1",
        "proxy": "",
        "enabled channels": ["1"],
        "custom channel names": {},
        "custom channel numbers": {},
        "custom genres": {},
        "custom epg ids": {},
        "fallback channels": {},
        "channel blocks": {},
        "dead channels": [],
    }
    portal.update(overrides)
    return portal


def loadApp(testCase, config):
    tmp = tempfile.TemporaryDirectory()
    testCase.addCleanup(tmp.cleanup)
    path = os.path.join(tmp.name, "config.json")
    with open(path, "w") as f:
        json.dump(config, f)

    env = mock.patch.dict(os.environ, {"CONFIG": path, "HOST": "proxy.test:8001"})
    env.start()
    testCase.addCleanup(env.stop)

    sys.modules.pop("app", None)
    appModule = importlib.import_module("app")
    appModule.config = appModule.loadConfig()
    appModule.app.config["TESTING"] = True

    stubs = {
        "getToken": "token",
        "getProfile": {"status": 0},
        "getAllChannels": PORTAL_CHANNELS,
        "getGenreNames": {"9": "Sports"},
        "getEpg": None,
        "getShortEpg": {"1": [], "2": [], "3": []},
    }
    for name, value in stubs.items():
        patcher = mock.patch.object(appModule.stb, name, return_value=value)
        patcher.start()
        testCase.addCleanup(patcher.stop)
    return appModule
```

- [ ] **Step 2: Write the failing tests**

`tests/test_app_lineup.py`:

```python
import json
import unittest

from tests.support import PORTAL, loadApp, portalConfig


def numbers(entries):
    return sorted(e["GuideNumber"] for e in entries)


class ConfigTest(unittest.TestCase):
    def test_new_keys_survive_load(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{"channel blocks": {"2": "NHL"}, "dead channels": ["3"]})},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "secret"},
            "blocks": {"NHL": "true"},
        }
        app = loadApp(self, cfg)
        portal = app.getPortals()[PORTAL]
        self.assertEqual(portal["channel blocks"], {"2": "NHL"})
        self.assertEqual(portal["dead channels"], ["3"])
        self.assertEqual(app.getBlocks(), {"NHL": "true"})
        self.assertEqual(app.getSettings()["plex url"], "http://plex.test:32400")
        self.assertEqual(app.getSettings()["plex token"], "secret")

    def test_blocks_default_to_empty(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        self.assertEqual(app.getBlocks(), {})

    def test_save_blocks_persists(self):
        app = loadApp(self, {"portals": {PORTAL: portalConfig()}})
        app.saveBlocks({"NHL": "true"})
        with open(app.configFile) as f:
            self.assertEqual(json.load(f)["blocks"], {"NHL": "true"})


class LineupTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {
                PORTAL: portalConfig(
                    **{
                        "enabled channels": ["1", "3"],
                        "channel blocks": {"2": "NHL"},
                        "dead channels": ["3"],
                        "custom epg ids": {"2": "custom.two"},
                    }
                )
            },
            "blocks": {"NHL": "true"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def test_build_lineup_applies_availability_and_epg_ids(self):
        entries, failed = self.app.buildLineup()
        self.assertEqual(failed, [])
        self.assertEqual(numbers(entries), ["101", "102"])
        byNumber = {e["GuideNumber"]: e for e in entries}
        self.assertEqual(byNumber["101"]["epgId"], PORTAL + "1")
        self.assertEqual(byNumber["102"]["epgId"], "custom.two")
        self.assertEqual(byNumber["101"]["URL"], "http://proxy.test:8001/play/p1/1")

    def test_build_lineup_reports_failed_portal(self):
        self.app.stb.getAllChannels.return_value = None
        entries, failed = self.app.buildLineup()
        self.assertEqual(entries, [])
        self.assertEqual(failed, ["Test portal"])

    def test_lineup_json_has_no_epg_id(self):
        data = self.client.get("/lineup.json").get_json()
        self.assertEqual(numbers(data), ["101", "102"])
        self.assertNotIn("epgId", data[0])

    def test_xmltv_uses_availability(self):
        body = self.client.get("/xmltv").get_data(as_text=True)
        self.assertIn('id="p11"', body)
        self.assertIn('id="custom.two"', body)
        self.assertNotIn('id="p13"', body)

    def test_playlist_uses_availability(self):
        body = self.client.get("/playlist").get_data(as_text=True)
        self.assertIn("/play/p1/1", body)
        self.assertIn("/play/p1/2", body)
        self.assertNotIn("/play/p1/3", body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `.venv/bin/python -m unittest tests.test_app_lineup -v`
Expected: failures and errors, including `AttributeError: module 'app' has no attribute 'getBlocks'`.

- [ ] **Step 4: Implement the config schema**

In `app.py`:

1. Add `import availability` after `import stb`.
2. Add to `defaultSettings`, after `"hdhr tuners": "1",`:

```python
    "plex url": "",
    "plex token": "",
```

3. Add to `defaultPortal`, after `"fallback channels": {},`:

```python
    "channel blocks": {},
    "dead channels": [],
```

4. In `loadConfig()`, after `data.setdefault("settings", {})`:

```python
    data.setdefault("blocks", {})
```

5. After `saveSettings()`:

```python
def getBlocks():
    return config["blocks"]


def saveBlocks(blocks):
    with open(configFile, "w") as f:
        config["blocks"] = blocks
        json.dump(config, f, indent=4)
```

- [ ] **Step 5: Implement `buildLineup()` and use it in `lineup()`**

Replace the whole body of `lineup()` (from `lineup = []` to `return flask.jsonify(lineup)`) with:

```python
    entries, _ = buildLineup()
    return flask.jsonify(
        [{k: v for k, v in entry.items() if k != "epgId"} for entry in entries]
    )
```

Insert above the `@app.route("/lineup.json", ...)` decorators:

```python
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
```

- [ ] **Step 6: Use availability in `playlist()` and `xmltv()`**

In both functions, replace:

```python
            enabledChannels = portals[portal].get("enabled channels", [])
```

with:

```python
            enabledChannels = availability.availableChannels(portals[portal], getBlocks())
```

Nothing else changes: both functions only test membership (`in enabledChannels`), and `xmltv()` iterates it for `stb.getShortEpg`. A set handles both.

- [ ] **Step 7: Run all the tests and confirm they pass**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 18 tests, OK.

- [ ] **Step 8: Commit**

```bash
git add app.py tests/support.py tests/test_app_lineup.py
git commit -m "Use availability rules in lineup, XMLTV and playlist; add buildLineup"
```

---

### Task 3: Plex client

**Files:**
- Create: `plex.py`
- Test: `tests/test_plex.py`

**Interfaces:**
- Consumes: lineup entries shaped like `buildLineup()`'s (`GuideNumber`, `epgId`; other keys ignored).
- Produces (`plex.py`):
  - `class PlexSyncError(Exception)`
  - `findDvr(plexUrl, token, tunerUri) -> tuple[str, str]`. Returns `(dvrKey, deviceKey)`.
  - `channelMapParams(lineupEntries) -> list[tuple[str, str]]`
  - `sync(plexUrl, token, tunerUri, lineupEntries) -> str`. Returns a success message and raises `PlexSyncError` on failure.

Facts verified against the live Plex (1.43.4) on 2026-10-02:
- Plex reads the tuner's channel list live, so no rescan is needed before mapping a new channel.
- A `PUT` channel map replaces the whole map: channels left out are removed from Plex.
- Brackets in the parameter names are sent percent-encoded (`channelMapping%5B3597%5D`), which is what `requests` does with tuple params.

- [ ] **Step 1: Write the failing tests**

`tests/test_plex.py`:

```python
import unittest
from unittest import mock

import requests

import plex

DVRS = {
    "MediaContainer": {
        "Dvr": [
            {"key": "7", "Device": [{"key": "3", "uri": "http://other:5004"}]},
            {"key": "2", "Device": [{"key": "1", "uri": "http://proxy.test:8001"}]},
        ]
    }
}

ENTRIES = [
    {"GuideNumber": "101", "GuideName": "One", "URL": "u1", "epgId": "p11"},
    {"GuideNumber": "102", "GuideName": "Two", "URL": "u2", "epgId": "custom.two"},
]


def response(status=200, json=None):
    r = mock.Mock(status_code=status)
    r.json.return_value = json
    return r


class PlexTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("plex.requests.request")
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def calls(self):
        return [(c.args[0], c.args[1]) for c in self.request.call_args_list]

    def test_find_dvr_by_tuner_uri(self):
        self.request.return_value = response(json=DVRS)
        self.assertEqual(plex.findDvr("http://plex.test:32400", "tok", "http://proxy.test:8001"), ("2", "1"))
        kwargs = self.request.call_args.kwargs
        self.assertEqual(kwargs["headers"], {"X-Plex-Token": "tok", "Accept": "application/json"})
        self.assertEqual(kwargs["timeout"], 30)

    def test_find_dvr_no_match(self):
        self.request.return_value = response(json=DVRS)
        with self.assertRaisesRegex(plex.PlexSyncError, "no Plex DVR uses this tuner"):
            plex.findDvr("http://plex.test:32400", "tok", "http://elsewhere:8001")

    def test_find_dvr_unexpected_reply(self):
        self.request.return_value = response(json={"unexpected": True})
        with self.assertRaisesRegex(plex.PlexSyncError, "unexpected reply"):
            plex.findDvr("http://plex.test:32400", "tok", "http://proxy.test:8001")

    def test_channel_map_params(self):
        self.assertEqual(
            plex.channelMapParams(ENTRIES),
            [
                ("channelMappingByKey[101]", "p11"),
                ("channelMapping[101]", "p11"),
                ("channelMappingByKey[102]", "custom.two"),
                ("channelMapping[102]", "custom.two"),
                ("channelsEnabled", "101,102"),
            ],
        )

    def test_sync_maps_then_reloads_guide(self):
        self.request.side_effect = [response(json=DVRS), response(), response()]
        message = plex.sync("http://plex.test:32400/", "tok", "http://proxy.test:8001", ENTRIES)
        self.assertEqual(message, "Plex updated: 2 channels enabled")
        self.assertEqual(
            self.calls(),
            [
                ("GET", "http://plex.test:32400/livetv/dvrs"),
                ("PUT", "http://plex.test:32400/media/grabbers/devices/1/channelmap"),
                ("POST", "http://plex.test:32400/livetv/dvrs/2/reloadGuide"),
            ],
        )
        self.assertEqual(self.request.call_args_list[1].kwargs["params"], plex.channelMapParams(ENTRIES))

    def test_refuses_empty_lineup(self):
        with self.assertRaisesRegex(plex.PlexSyncError, "no channels are available"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", [])
        self.request.assert_not_called()

    def test_connection_error_is_readable(self):
        self.request.side_effect = requests.ConnectionError("boom")
        with self.assertRaisesRegex(plex.PlexSyncError, "couldn't reach Plex at http://plex.test:32400"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)

    def test_connection_error_on_timeout(self):
        self.request.side_effect = requests.Timeout("slow")
        with self.assertRaisesRegex(plex.PlexSyncError, "couldn't reach Plex"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)

    def test_rejected_token(self):
        self.request.return_value = response(status=401)
        with self.assertRaisesRegex(plex.PlexSyncError, "Plex rejected the token"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)

    def test_other_http_error_names_status(self):
        self.request.side_effect = [response(json=DVRS), response(status=500)]
        with self.assertRaisesRegex(plex.PlexSyncError, "HTTP 500"):
            plex.sync("http://plex.test:32400", "tok", "http://proxy.test:8001", ENTRIES)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m unittest tests.test_plex -v`
Expected: ERROR `ModuleNotFoundError: No module named 'plex'`

- [ ] **Step 3: Implement `plex.py`**

```python
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
```

- [ ] **Step 4: Run all the tests and confirm they pass**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 28 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add plex.py tests/test_plex.py
git commit -m "Add Plex client that syncs the DVR channel map"
```

---

### Task 4: Plex settings and `syncPlex()`

**Files:**
- Modify: `app.py`. Add `import plex` after `import availability`, change `save()` (route `/settings/save`), and add `lastPlexSync`, `plexConfigured()` and `syncPlex()` after `buildLineup()`.
- Modify: `templates/settings.html`. Add a Plex section after the HDHomeRun section.
- Test: `tests/test_app_plex.py`

**Interfaces:**
- Consumes: `buildLineup()` (Task 2), `plex.sync`, `plex.PlexSyncError` (Task 3)
- Produces (`app.py`):
  - `plexConfigured() -> bool`
  - `syncPlex() -> tuple[str, str]`. Returns `(flashCategory, message)`, where the category is `"success"`, `"danger"` or `"info"`.
  - `lastPlexSync: dict`. Keys `time` (str or None), `message` (str), `ok` (bool or None).

- [ ] **Step 1: Write the failing tests**

`tests/test_app_plex.py`:

```python
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig

SETTINGS_FORM = {
    "stream method": "ffmpeg",
    "ffmpeg command": "ffmpeg",
    "ffmpeg timeout": "5",
    "username": "admin",
    "password": "12345",
    "hdhr name": "STB-Proxy",
    "hdhr id": "abc",
    "hdhr tuners": "1",
}


class SettingsTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig()},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "tok-s3cret-123"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()

    def post(self, **fields):
        form = dict(SETTINGS_FORM, **fields)
        return self.client.post("/settings/save", data=form)

    def test_blank_token_field_keeps_saved_token(self):
        self.post(**{"plex url": "http://plex.test:32400", "plex token": ""})
        self.assertEqual(self.app.getSettings()["plex token"], "tok-s3cret-123")

    def test_new_token_replaces_saved_one(self):
        self.post(**{"plex url": "http://plex.test:32400", "plex token": "new"})
        self.assertEqual(self.app.getSettings()["plex token"], "new")

    def test_clear_token(self):
        self.post(**{"plex url": "http://plex.test:32400", "plex token": "", "clear plex token": "true"})
        self.assertEqual(self.app.getSettings()["plex token"], "")

    def test_plex_url_trimmed(self):
        self.post(**{"plex url": " http://plex.test:32400/ ", "plex token": ""})
        self.assertEqual(self.app.getSettings()["plex url"], "http://plex.test:32400")

    def test_settings_page_never_shows_token(self):
        body = self.client.get("/settings").get_data(as_text=True)
        self.assertIn("http://plex.test:32400", body)
        self.assertNotIn("tok-s3cret-123", body)


class SyncPlexTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig()},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "tok"},
        }
        self.app = loadApp(self, cfg)
        patcher = mock.patch.object(self.app.plex, "sync", return_value="Plex updated: 1 channels enabled")
        self.sync = patcher.start()
        self.addCleanup(patcher.stop)

    def test_success(self):
        self.assertEqual(self.app.syncPlex(), ("success", "Plex updated: 1 channels enabled"))
        args = self.sync.call_args.args
        self.assertEqual(args[:3], ("http://plex.test:32400", "tok", "http://proxy.test:8001"))
        self.assertEqual([e["GuideNumber"] for e in args[3]], ["101"])
        self.assertTrue(self.app.lastPlexSync["ok"])
        self.assertIsNotNone(self.app.lastPlexSync["time"])

    def test_plex_error_reported(self):
        self.sync.side_effect = self.app.plex.PlexSyncError("Plex rejected the token (HTTP 401)")
        category, message = self.app.syncPlex()
        self.assertEqual(category, "danger")
        self.assertEqual(message, "Plex not updated: Plex rejected the token (HTTP 401)")
        self.assertFalse(self.app.lastPlexSync["ok"])

    def test_sync_aborts_when_a_portal_fails(self):
        self.app.stb.getAllChannels.return_value = None
        category, message = self.app.syncPlex()
        self.assertEqual(category, "danger")
        self.assertIn("couldn't load channels from Test portal", message)
        self.sync.assert_not_called()

    def test_not_configured(self):
        self.app.getSettings()["plex token"] = ""
        category, message = self.app.syncPlex()
        self.assertEqual(category, "info")
        self.assertIn("Plex sync is off", message)
        self.sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m unittest tests.test_app_plex -v`
Expected: failures and errors, including `AttributeError: module 'app' has no attribute 'plex'`.

- [ ] **Step 3: Implement `syncPlex()`**

In `app.py`, add `import plex` after `import availability`. After `buildLineup()`, add:

```python
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
```

- [ ] **Step 4: Keep the token when its field is blank**

In `save()` (route `/settings/save`), replace:

```python
    settings = {}

    for setting, _ in defaultSettings.items():
        value = request.form.get(setting, "false")
        settings[setting] = value

    saveSettings(settings)
```

with:

```python
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
```

- [ ] **Step 5: Add the Plex section to Settings**

In `templates/settings.html`, insert immediately before the final `</div>` that closes `<div class="container-fluid text-light p-lg-5">`, after the HDHomeRun section's closing `</div>`:

```html
    <br>

    <h4>Plex</h4>
    <hr>
    <div class="p-sm-3">

        <h6>Plex address:</h6>
        <div class="col-md-4">
            <input form="save" type="text" name="plex url" id="plex url" class="form-control"
                placeholder="http://192.168.5.3:32400" value="{{ settings['plex url'] }}">
        </div>
        <span class="text-muted">Lets block switches and dead marks update the Plex DVR. Leave blank to turn this off.</span>

        <br>
        <br>

        <h6>Plex token:</h6>
        <div class="col-md-4">
            <input form="save" type="password" name="plex token" id="plex token" class="form-control"
                autocomplete="off"
                placeholder="{{ 'Saved, leave blank to keep' if settings['plex token'] else 'Not set' }}">
        </div>
        <div class="form-check mt-1">
            <input form="save" type="checkbox" class="form-check-input" name="clear plex token" id="clear plex token" value="true">
            <label class="form-check-label" for="clear plex token">Clear token</label>
        </div>

    </div>
```

- [ ] **Step 6: Run all the tests and confirm they pass**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 37 tests, OK.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/settings.html tests/test_app_plex.py
git commit -m "Add Plex settings and syncPlex()"
```

---

### Task 5: Block column in the editor

**Files:**
- Modify: `app.py`, in `editor_data()` and `editorSave()`
- Modify: `templates/editor.html`
- Test: `tests/test_app_editor.py`

**Interfaces:**
- Consumes: `availability.availableChannels`, `availability.pruneBlocks` (Task 1); `getBlocks`, `saveBlocks` (Task 2); `syncPlex` (Task 4)
- Produces:
  - `/editor_data` rows gain `"block": str` and `"dead": bool`.
  - `/editor/save` accepts the form field `blockEdits`, a JSON list of `{"portal", "channel id", "block"}`.
  - The editor's JS has a global `table` (the DataTables API instance) and play buttons carrying `data-portal` and `data-channelId`. Task 7 builds on these.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_editor.py`:

```python
import json
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig

EMPTY_EDITS = {
    "enabledEdits": "[]",
    "numberEdits": "[]",
    "nameEdits": "[]",
    "genreEdits": "[]",
    "epgEdits": "[]",
    "fallbackEdits": "[]",
}


class EditorTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {PORTAL: portalConfig(**{"channel blocks": {"2": "NHL"}, "dead channels": ["3"]})},
            "blocks": {"NHL": "true", "Old": "false"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def save(self, blockEdits=None, enabledEdits=None):
        form = dict(EMPTY_EDITS)
        if blockEdits is not None:
            form["blockEdits"] = json.dumps(blockEdits)
        if enabledEdits is not None:
            form["enabledEdits"] = json.dumps(enabledEdits)
        return self.client.post("/editor/save", data=form)

    def blockEdit(self, channelId, block):
        return {"portal": PORTAL, "channel id": channelId, "block": block}

    def test_editor_page_renders_block_field(self):
        body = self.client.get("/editor").get_data(as_text=True)
        self.assertIn('id="blockEdits"', body)
        self.assertIn("function editBlock", body)

    def test_editor_data_has_block_and_dead(self):
        rows = {r["channelId"]: r for r in self.client.get("/editor_data").get_json()["data"]}
        self.assertEqual(rows["2"]["block"], "NHL")
        self.assertEqual(rows["1"]["block"], "")
        self.assertTrue(rows["3"]["dead"])
        self.assertFalse(rows["1"]["dead"])

    def test_block_names_are_trimmed(self):
        self.save([self.blockEdit("1", "  NHL ")])
        self.assertEqual(self.app.getPortals()[PORTAL]["channel blocks"]["1"], "NHL")

    def test_clearing_block_removes_membership(self):
        self.save([self.blockEdit("2", "")])
        self.assertNotIn("2", self.app.getPortals()[PORTAL]["channel blocks"])

    def test_clearing_block_never_set_is_harmless(self):
        response = self.save([self.blockEdit("1", "")])
        self.assertEqual(response.status_code, 302)

    def test_save_without_block_edits_field_still_works(self):
        response = self.save()
        self.assertEqual(response.status_code, 302)

    def test_unused_block_states_pruned(self):
        self.save([self.blockEdit("2", "")])
        self.assertEqual(self.app.getBlocks(), {})

    def test_adding_channel_to_block_that_is_on_syncs_plex(self):
        self.save([self.blockEdit("1", "NHL"), self.blockEdit("3", "NHL")])
        self.syncPlex.assert_not_called()  # 1 already enabled, 3 is dead: nothing changed
        self.save([self.blockEdit("1", "")])
        self.syncPlex.assert_not_called()  # 1 is still enabled on its own
        self.app.getPortals()[PORTAL]["enabled channels"] = []
        self.save([self.blockEdit("1", "NHL")])
        self.syncPlex.assert_called_once()

    def test_enabling_channel_syncs_plex(self):
        self.save(enabledEdits=[{"portal": PORTAL, "channel id": "3", "enabled": False}])
        self.syncPlex.assert_not_called()
        self.save(enabledEdits=[{"portal": PORTAL, "channel id": "1", "enabled": False}])
        self.syncPlex.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m unittest tests.test_app_editor -v`
Expected: failures, including `KeyError: 'block'` in `test_editor_data_has_block_and_dead` and `id="blockEdits"` not found in `test_editor_page_renders_block_field`.

- [ ] **Step 3: Add `block` and `dead` to `/editor_data`**

In `editor_data()`, after `fallbackChannels = portals[portal].get("fallback channels", {})`:

```python
            channelBlocks = portals[portal].get("channel blocks", {})
            deadChannels = portals[portal].get("dead channels", [])
```

In the `channels.append({...})` dict, after `"fallbackChannel": fallbackChannel,`:

```python
                            "block": channelBlocks.get(channelId, ""),
                            "dead": channelId in deadChannels,
```

- [ ] **Step 4: Save block edits and sync Plex when availability changes**

In `editorSave()`:

1. After `fallbackEdits = json.loads(request.form["fallbackEdits"])`:

```python
    blockEdits = json.loads(request.form.get("blockEdits", "[]"))
```

2. Right after `portals = getPortals()`:

```python
    blocks = getBlocks()
    availableBefore = {p: availability.availableChannels(portals[p], blocks) for p in portals}
```

3. Before `savePortals(portals)`:

```python
    for edit in blockEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        block = edit["block"].strip()
        portals[portal].setdefault("channel blocks", {})
        if block:
            portals[portal]["channel blocks"][channelId] = block
        else:
            portals[portal]["channel blocks"].pop(channelId, None)
```

4. Replace:

```python
    savePortals(portals)
    logger.info("Playlist config saved!")
    flash("Playlist config saved!", "success")
```

with:

```python
    savePortals(portals)
    saveBlocks(availability.pruneBlocks(portals, blocks))
    logger.info("Playlist config saved!")
    flash("Playlist config saved!", "success")

    availableAfter = {p: availability.availableChannels(portals[p], getBlocks()) for p in portals}
    if availableAfter != availableBefore:
        category, message = syncPlex()
        flash(message, category)
```

- [ ] **Step 5: Run the backend tests**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 46 tests, with only `test_editor_page_renders_block_field` failing. The template changes come next.

- [ ] **Step 6: Add the Block column to the editor UI**

In `templates/editor.html`:

1. Header: after `<th>Genre</th>`, add `<th>Block</th>`.
2. Hidden form: after `<input type="text" id="fallbackEdits" name="fallbackEdits" value="">`, add:

```html
        <input type="text" id="blockEdits" name="blockEdits" value="">
```

3. Script: after `var fallbackEdits = [];`, add:

```javascript
    var blockEdits = [];
    var table;

    function escapeAttr(s) {
        return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
```

4. After `function editFallback(ele) {...}`, add:

```javascript
    function editBlock(ele) {
        var p = ele.getAttribute('data-portal');
        var i = ele.getAttribute('data-channelId');
        var j = { "portal": p, "channel id": i, "block": ele.value };
        blockEdits.push(j);
    }
```

5. In `save()`, after the `fallbackEdits` line:

```javascript
        document.getElementById("blockEdits").value = JSON.stringify(blockEdits);
```

6. Change `$('#table').DataTable({` to `table = $('#table').DataTable({`.
7. Replace the `columnDefs` array with the following. It adds the Block column at index 4 and shifts Number, EPG ID, Fallback and Portal one place right:

```javascript
            columnDefs: [
                { targets: [0, 1], width: "0%" },
                { targets: 0, className: "align-middle", orderable: false, searchable: false, orderDataType: "dom-checkbox" },
                { targets: 1, className: "align-middle", orderable: false, searchable: false },
                { targets: 2, className: "align-middle", orderDataType: "dom-text", type: 'string' },
                { targets: 3, className: "align-middle", orderDataType: "dom-text", type: 'string' },
                { targets: 4, className: "align-middle", orderDataType: "dom-text", type: 'string' },
                { targets: 5, className: "align-middle", orderDataType: "dom-text-numeric" },
                { targets: 6, className: "align-middle", orderDataType: "dom-text", type: 'string' },
                { targets: 7, className: "align-middle", orderDataType: "dom-text", type: 'string' },
                { targets: 8, className: "align-middle" }
            ],
```

8. In `columns`, insert after the `genre` column object and before the `channelNumber` one:

```javascript
                {
                    data: "block",
                    render: function (data, type, row, meta) {
                        if (type === 'filter' || type === 'sort') {
                            return data;
                        }
                        return '<input \
                                type="text" \
                                class="form-control" \
                                style="min-width: 150px;" \
                                onchange="editBlock(this)" \
                                data-portal="' + row.portal + '" \
                                data-channelId="' + row.channelId + '" \
                                placeholder="No block" \
                                value="' + escapeAttr(data) +
                            '">'
                    },
                },
```

- [ ] **Step 7: Run all the tests and confirm they pass**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 46 tests, OK.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/editor.html tests/test_app_editor.py
git commit -m "Add Block column to the playlist editor; sync Plex when availability changes"
```

---

### Task 6: Blocks page

**Files:**
- Modify: `app.py`. Add routes `/blocks`, `/blocks/toggle` and `/blocks/sync` after `editorReset()`.
- Create: `templates/blocks.html`
- Modify: `templates/base.html`. Add a nav item.
- Test: `tests/test_app_blocks.py`

**Interfaces:**
- Consumes: `availability.blockSummaries`, `availability.blockNames` (Task 1); `getBlocks`, `saveBlocks` (Task 2); `syncPlex`, `plexConfigured`, `lastPlexSync` (Task 4)
- Produces: `GET /blocks`; `POST /blocks/toggle` with form fields `name` and `enabled` (`"true"`/`"false"`); `POST /blocks/sync`.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_blocks.py`:

```python
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class BlocksPageTest(unittest.TestCase):
    def setUp(self):
        cfg = {
            "portals": {
                PORTAL: portalConfig(
                    **{"channel blocks": {"2": "NHL", "3": "NHL", "1": "<b>Bold</b>"}, "dead channels": ["3"]}
                )
            },
            "blocks": {"NHL": "false"},
            "settings": {"plex url": "http://plex.test:32400", "plex token": "tok"},
        }
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated: 2 channels enabled"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def test_page_lists_blocks_with_counts(self):
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("NHL", body)
        self.assertIn("2 channels", body)
        self.assertIn("1 dead", body)
        self.assertIn("Sync Plex now", body)

    def test_block_names_are_escaped(self):
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("&lt;b&gt;Bold&lt;/b&gt;", body)
        self.assertNotIn("<b>Bold</b>", body)

    def test_empty_state(self):
        self.app.getPortals()[PORTAL]["channel blocks"] = {}
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("No blocks yet", body)

    def test_toggle_on_saves_and_syncs(self):
        response = self.client.post("/blocks/toggle", data={"name": "NHL", "enabled": "true"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.app.getBlocks()["NHL"], "true")
        self.syncPlex.assert_called_once()
        lineup = [e["GuideNumber"] for e in self.client.get("/lineup.json").get_json()]
        self.assertEqual(sorted(lineup), ["101", "102"])

    def test_toggle_off(self):
        self.app.getBlocks()["NHL"] = "true"
        self.client.post("/blocks/toggle", data={"name": "NHL", "enabled": "false"})
        self.assertEqual(self.app.getBlocks()["NHL"], "false")

    def test_toggle_saves_even_when_plex_fails(self):
        self.syncPlex.return_value = ("danger", "Plex not updated: couldn't reach Plex at http://plex.test:32400 (ConnectionError)")
        self.client.post("/blocks/toggle", data={"name": "NHL", "enabled": "true"})
        self.assertEqual(self.app.getBlocks()["NHL"], "true")
        body = self.client.get("/blocks").get_data(as_text=True)
        self.assertIn("couldn&#39;t reach Plex", body)

    def test_toggle_unknown_block(self):
        self.client.post("/blocks/toggle", data={"name": "Nope", "enabled": "true"})
        self.assertNotIn("Nope", self.app.getBlocks())
        self.syncPlex.assert_not_called()

    def test_sync_now(self):
        response = self.client.post("/blocks/sync")
        self.assertEqual(response.status_code, 302)
        self.syncPlex.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

`test_toggle_saves_even_when_plex_fails` reads the message back through the next page's flash. Jinja escapes `'` as `&#39;`.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m unittest tests.test_app_blocks -v`
Expected: failures with status 404 for `/blocks`.

- [ ] **Step 3: Add the routes**

In `app.py`, after `editorReset()`:

```python
@app.route("/blocks", methods=["GET"])
@authorise
def blocksPage():
    return render_template(
        "blocks.html",
        blocks=availability.blockSummaries(getPortals(), getBlocks()),
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
```

- [ ] **Step 4: Create `templates/blocks.html`**

```html
{% extends "base.html" %}
{% block content %}

<div class="container text-light p-lg-5">

    <div class="d-flex align-items-center mb-2">
        <h4 class="mb-0">Blocks</h4>
        <form action="/blocks/sync" method="post" class="ms-auto">
            <button class="btn btn-primary" {{ "disabled" if not plexConfigured }}><i class="fa fa-refresh"></i> Sync Plex now</button>
        </form>
    </div>

    <p class="text-muted">
        {% if not plexConfigured %}
        Plex sync is off. Add the Plex address and token in Settings.
        {% elif lastPlexSync.time %}
        Last Plex sync {{ lastPlexSync.time }}:
        <span class="{{ 'text-success' if lastPlexSync.ok else 'text-danger' }}">{{ lastPlexSync.message }}</span>
        {% else %}
        {{ lastPlexSync.message }}
        {% endif %}
    </p>
    <hr>

    {% if blocks %}
    <table class="table table-dark table-striped align-middle">
        <thead>
            <tr>
                <th style="width: 0%;">On</th>
                <th>Block</th>
                <th>Channels</th>
            </tr>
        </thead>
        <tbody>
            {% for block in blocks %}
            <tr>
                <td>
                    <form action="/blocks/toggle" method="post">
                        <input type="hidden" name="name" value="{{ block.name }}">
                        <input type="hidden" name="enabled" value="{{ 'false' if block.enabled else 'true' }}">
                        <div class="form-check form-switch">
                            <input class="form-check-input block-switch" type="checkbox"
                                onchange="switchBlock(this)" {{ "checked" if block.enabled }}>
                        </div>
                    </form>
                </td>
                <td>{{ block.name }}</td>
                <td>
                    {{ block.channels }} channels
                    {% if block.dead %}<span class="badge bg-danger ms-1">{{ block.dead }} dead</span>{% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    <p id="updating" class="text-muted d-none"><i class="fa fa-spinner fa-spin"></i> Updating Plex...</p>
    {% else %}
    <p>No blocks yet. In the Playlist Editor, type the same block name in the Block column for each channel you
        want in a block, then save.</p>
    {% endif %}

</div>

<script>
    function switchBlock(ele) {
        document.querySelectorAll('.block-switch').forEach(function (e) { e.disabled = true; });
        document.getElementById('updating').classList.remove('d-none');
        ele.form.submit();
    }
</script>

{% endblock %}
```

The switches have no `name`, so disabling them doesn't change what's submitted. The hidden fields carry the values.

- [ ] **Step 5: Add the nav item**

In `templates/base.html`, after the `<li>` that contains `href="/editor"`:

```html
                    <li class="nav-item">
                        <a class="nav-link" href="/blocks"><i class="fa fa-th-large"></i> Blocks</a>
                    </li>
```

- [ ] **Step 6: Run all the tests and confirm they pass**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 54 tests, OK.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/blocks.html templates/base.html tests/test_app_blocks.py
git commit -m "Add Blocks page to switch blocks on and off"
```

---

### Task 7: Dead channels

**Files:**
- Modify: `app.py`. Add route `/channel/dead` after `blocksSync()`.
- Modify: `templates/editor.html`
- Test: `tests/test_app_dead.py`

**Interfaces:**
- Consumes: `availability.availableChannels` (Task 1); `syncPlex` (Task 4); from Task 5's editor JS, the globals `table` and `escapeAttr`, and row fields `dead`, `portal` and `channelId`.
- Produces: `POST /channel/dead` with form fields `portal`, `channelId` and `dead` (`"true"`/`"false"`). It returns JSON `{"dead": bool, "plex": str}`, or 404 `{"error": "Unknown portal"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_dead.py`:

```python
import unittest
from unittest import mock

from tests.support import PORTAL, loadApp, portalConfig


class DeadChannelTest(unittest.TestCase):
    def setUp(self):
        cfg = {"portals": {PORTAL: portalConfig(**{"enabled channels": ["1", "2"]})}}
        self.app = loadApp(self, cfg)
        self.client = self.app.app.test_client()
        patcher = mock.patch.object(self.app, "syncPlex", return_value=("success", "Plex updated: 1 channels enabled"))
        self.syncPlex = patcher.start()
        self.addCleanup(patcher.stop)

    def mark(self, channelId, dead, portal=PORTAL):
        return self.client.post(
            "/channel/dead", data={"portal": portal, "channelId": channelId, "dead": "true" if dead else "false"}
        )

    def lineupNumbers(self):
        return sorted(e["GuideNumber"] for e in self.client.get("/lineup.json").get_json())

    def test_mark_available_channel_dead(self):
        response = self.mark("2", True)
        self.assertEqual(response.get_json(), {"dead": True, "plex": "Plex updated: 1 channels enabled"})
        self.assertEqual(self.app.getPortals()[PORTAL]["dead channels"], ["2"])
        self.assertEqual(self.lineupNumbers(), ["101"])
        self.syncPlex.assert_called_once()

    def test_unmark_restores(self):
        self.mark("2", True)
        self.mark("2", False)
        self.assertEqual(self.app.getPortals()[PORTAL]["dead channels"], [])
        self.assertEqual(self.lineupNumbers(), ["101", "102"])
        self.assertEqual(self.syncPlex.call_count, 2)
        self.assertEqual(self.app.getPortals()[PORTAL]["enabled channels"], ["1", "2"])

    def test_marking_unavailable_channel_does_not_sync(self):
        response = self.mark("3", True)
        self.assertEqual(response.get_json(), {"dead": True, "plex": ""})
        self.syncPlex.assert_not_called()

    def test_marking_twice_does_not_duplicate(self):
        self.mark("2", True)
        self.mark("2", True)
        self.assertEqual(self.app.getPortals()[PORTAL]["dead channels"], ["2"])
        self.syncPlex.assert_called_once()

    def test_unknown_portal(self):
        response = self.mark("1", True, portal="nope")
        self.assertEqual(response.status_code, 404)

    def test_editor_page_has_dead_controls(self):
        body = self.client.get("/editor").get_data(as_text=True)
        self.assertIn('id="deadButton"', body)
        self.assertIn("function toggleDead", body)
        self.assertIn("dead-filter", body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m unittest tests.test_app_dead -v`
Expected: failures with status 404 for `/channel/dead`.

- [ ] **Step 3: Add the route**

In `app.py`, after `blocksSync()`:

```python
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
```

- [ ] **Step 4: Run the backend tests**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 60 tests, with only `test_editor_page_has_dead_controls` failing. The template changes come next.

- [ ] **Step 5: Add the dead badge, "Hide dead" filter and preview controls to the editor**

In `templates/editor.html`:

1. Modal: after the closing `</div>` of `<div class="modal-body">`, add:

```html
                <div class="modal-footer">
                    <span id="previewProblem" class="me-auto text-warning d-none">This channel didn't play. Mark it dead?</span>
                    <span id="deadStatus" class="me-auto small"></span>
                    <button type="button" class="btn btn-danger" id="deadButton" onclick="toggleDead()">Mark dead</button>
                </div>
```

2. Play button: in the `link` column's render, add these attributes after `onclick="selectChannel(this)" \`:

```javascript
                            data-portal="' + row.portal + '" \
                            data-channelId="' + row.channelId + '" \
```

3. Name column: replace the `channelName` column's render function with this one, which wraps the input and the dead badge:

```javascript
                    render: function (data, type, row, meta) {
                        return '<div class="d-flex align-items-center"><input \
                                type="text" \
                                class="form-control" \
                                style="min-width: 200px;" \
                                onchange="editCustomName(this)" \
                                data-portal="' + row.portal + '" \
                                data-channelId="' + row.channelId + '" \
                                placeholder="' + row.channelName + '" \
                                title="' + row.channelName + '" \
                                value="' + row.customChannelName +
                            '"><span class="badge bg-danger ms-2 dead-badge' + (row.dead ? '' : ' d-none') + '" \
                                data-key="' + row.portal + '/' + row.channelId + '">dead</span></div>'
                    },
```

4. Replace the existing `selectChannel` function and the `$('#videoModal').on('hidden.bs.modal', ...)` handler with:

```javascript
    var currentChannel = null;
    var previewTimer = null;

    function selectChannel(ele) {
        link = ele.getAttribute('data-link');
        player.src = link;
        channel = ele.getAttribute('data-customChannelName');
        if (channel == "") {
            channel = ele.getAttribute('data-channelName');
        }
        title.innerHTML = channel
        currentChannel = { portal: ele.getAttribute('data-portal'), channelId: ele.getAttribute('data-channelId') };
        showDeadState(rowFor(currentChannel).dead);
        document.getElementById("previewProblem").classList.add("d-none");
        document.getElementById("deadStatus").textContent = "";
        clearTimeout(previewTimer);
        previewTimer = setTimeout(previewFailed, 15000);
    }

    player.addEventListener("playing", function () {
        clearTimeout(previewTimer);
    });

    player.addEventListener("error", function () {
        previewFailed();
    });

    $('#videoModal').on('hidden.bs.modal', function () {
        currentChannel = null;
        clearTimeout(previewTimer);
        player.src = "";
    })

    function rowFor(ch) {
        var found = null;
        table.rows().every(function () {
            var d = this.data();
            if (d.portal == ch.portal && d.channelId == ch.channelId) {
                found = d;
            }
        });
        return found;
    }

    function previewFailed() {
        clearTimeout(previewTimer);
        if (!currentChannel || rowFor(currentChannel).dead) {
            return;
        }
        document.getElementById("previewProblem").classList.remove("d-none");
    }

    function showDeadState(dead) {
        var button = document.getElementById("deadButton");
        button.textContent = dead ? "Mark working" : "Mark dead";
        button.className = dead ? "btn btn-success" : "btn btn-danger";
    }

    function toggleDead() {
        var ch = currentChannel;
        var row = rowFor(ch);
        var button = document.getElementById("deadButton");
        var status = document.getElementById("deadStatus");
        button.disabled = true;
        $.post("/channel/dead", { portal: ch.portal, channelId: ch.channelId, dead: row.dead ? "false" : "true" })
            .done(function (res) {
                row.dead = res.dead;
                var badge = document.querySelector('.dead-badge[data-key="' + ch.portal + '/' + ch.channelId + '"]');
                if (badge) {
                    badge.classList.toggle("d-none", !res.dead);
                }
                showDeadState(res.dead);
                document.getElementById("previewProblem").classList.add("d-none");
                status.textContent = (res.dead ? "Marked dead." : "Marked working.") + (res.plex ? " " + res.plex : "");
                table.draw(false);
            })
            .fail(function () {
                status.textContent = "Couldn't save. Try again.";
            })
            .always(function () {
                button.disabled = false;
            });
    }

    var hideDead = true;
    $.fn.dataTable.ext.search.push(function (settings, data, dataIndex, rowData) {
        return !hideDead || !rowData.dead;
    });
```

`previewFailed()` ignores the `error` that clearing `player.src` fires on close, because the close handler sets `currentChannel = null` first.

5. "Hide dead" toggle: change the table's `dom` option to:

```javascript
            dom: "<'row m-1'<'col-auto'B><'col-auto d-flex align-items-center dead-filter'><'col-auto ms-auto'f><'col-auto'l>>" +
                "<'row'<'col-12'tr>>" +
                "<'row mb-1 mb-lg-0'<'col-auto text-light'i><'col-auto ms-auto'p>>",
```

and add this option after `pageLength: 25,`:

```javascript
            initComplete: function () {
                $('div.dead-filter').html(
                    '<div class="form-check form-switch text-light mb-0">' +
                    '<input type="checkbox" class="form-check-input" id="hideDead" checked ' +
                    'onchange="hideDead = this.checked; table.draw(false);">' +
                    '<label class="form-check-label" for="hideDead">Hide dead</label></div>'
                );
            },
```

The "Hide dead" input deliberately doesn't have the `checkbox` class: `editAll()` toggles every `.checkbox` element except the first.

- [ ] **Step 6: Run all the tests and confirm they pass**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 60 tests, OK.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/editor.html tests/test_app_dead.py
git commit -m "Mark channels dead from the preview; hide dead channels everywhere"
```

---

### Task 8: Deploy and verify end to end

**Files:**
- No code changes, unless a check fails. A fix goes in a new commit, together with a test that reproduces the problem.

**Interfaces:**
- Consumes: everything above, plus the live LXC 115 (`ssh proxmox`, `pct exec 115`) and Plex on `ssh ubuntu3` (container `plex`).

- [ ] **Step 1: Run the full test suite one last time**

Run: `.venv/bin/python -m unittest discover -s tests -t . -v`
Expected: 60 tests, OK.

- [ ] **Step 2: Deploy as a git fast-forward**

```bash
cd /code/stb-proxy
B=/tmp/claude-1000/-code/d43e5192-875a-4aef-949c-a6347f8c0fac/scratchpad/stb.bundle
git bundle create "$B" master
scp -q "$B" proxmox:/tmp/stb.bundle
ssh proxmox 'pct push 115 /tmp/stb.bundle /tmp/stb.bundle && rm /tmp/stb.bundle && pct exec 115 -- bash -c "
cd /opt/stb-proxy/app &&
git -c safe.directory=/opt/stb-proxy/app pull --ff-only /tmp/stb.bundle master &&
chown -R stbproxy:stbproxy /opt/stb-proxy/app && rm /tmp/stb.bundle &&
systemctl restart stb-proxy && sleep 3 && systemctl is-active stb-proxy &&
git -c safe.directory=/opt/stb-proxy/app log --oneline -1"'
rm "$B"
```

Expected: `active`, followed by the latest commit.

- [ ] **Step 3: Install the verification helpers on ubuntu3**

Write this to the scratchpad as `e2e.sh`, then copy it to ubuntu3 with `scp e2e.sh ubuntu3:stb-e2e.sh`. Every later step runs `ssh ubuntu3 'source ~/stb-e2e.sh; <commands>'`.

```bash
S=http://192.168.5.71:8001
P=48b21626fe5e4aaca795ebb4a4d5ad6b
T=$(docker exec plex sh -c 'grep -o "PlexOnlineToken=\"[^\"]*" "/config/Library/Application Support/Plex Media Server/Preferences.xml" | cut -d\" -f2')

lineupNumbers() {
    curl -s "$S/lineup.json" | python3 -c 'import json,sys; L=json.load(sys.stdin); print(len(L), "in lineup:", " ".join(sorted(c["GuideNumber"] for c in L)))'
}

plexMap() {
    curl -s -H Accept:application/json "http://127.0.0.1:32400/livetv/dvrs/2?X-Plex-Token=$T" | python3 -c '
import json, sys
cm = json.load(sys.stdin)["MediaContainer"]["Dvr"][0]["Device"][0].get("ChannelMapping", [])
print(len(cm), "mapped,", sum(c.get("enabled") == "1" for c in cm), "enabled")
for c in sorted(cm, key=lambda c: c["deviceIdentifier"]):
    print(" ", c["deviceIdentifier"], c["lineupIdentifier"], "on" if c.get("enabled") == "1" else "off")'
}

editorSave() {  # $1 = blockEdits JSON
    curl -s -o /dev/null -w "editor save: %{http_code}\n" -X POST "$S/editor/save" --data-urlencode "blockEdits=$1" \
        -d enabledEdits=[] -d numberEdits=[] -d nameEdits=[] -d genreEdits=[] -d epgEdits=[] -d fallbackEdits=[]
}

toggleBlock() {  # $1 = block name, $2 = true|false
    curl -s -o /dev/null -w "toggle: %{http_code}\n" -X POST "$S/blocks/toggle" --data-urlencode "name=$1" -d "enabled=$2"
}

markDead() {  # $1 = channelId, $2 = true|false
    curl -s -X POST "$S/channel/dead" -d "portal=$P" -d "channelId=$1" -d "dead=$2"; echo
}

lastSync() {
    curl -s "$S/blocks" | sed -n '/Last Plex sync/,/<\/p>/p' | sed 's/<[^>]*>//g' | tr -s ' \n' ' '; echo
}

guideImport() {
    docker exec plex sh -c 'grep -h "EPG\[xmltv\]: Step" "/config/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log" | tail -1 | cut -c1-170'
}
```

- [ ] **Step 4: Configure Plex sync**

Run this from this machine. It reads the token on ubuntu3 and pipes it into a form post made inside the LXC. Every other setting is posted with its current value from `config.json`, so nothing else changes. The token is never printed.

```bash
ssh ubuntu3 'docker exec plex sh -c "grep -o \"PlexOnlineToken=\\\"[^\\\"]*\" \"/config/Library/Application Support/Plex Media Server/Preferences.xml\" | cut -d\\\" -f2"' \
| ssh proxmox 'pct exec 115 -- python3 -c "
import json, sys, urllib.parse, urllib.request
token = sys.stdin.read().strip()
settings = json.load(open(\"/opt/stb-proxy/config/config.json\"))[\"settings\"]
form = dict(settings, **{\"plex url\": \"http://192.168.5.3:32400\", \"plex token\": token})
urllib.request.urlopen(\"http://127.0.0.1:8001/settings/save\", urllib.parse.urlencode(form).encode())
print(\"settings saved\")"'
ssh proxmox 'pct exec 115 -- python3 -c "import json; s=json.load(open(\"/opt/stb-proxy/config/config.json\"))[\"settings\"]; print(s[\"plex url\"], len(s[\"plex token\"]))"'
```

Expected: `settings saved`, then `http://192.168.5.3:32400 20`. If the length is 0, stdin didn't reach the LXC. In that case, write the token to a root-only file in the LXC, read it from there, and delete the file afterwards.

Then check that the Settings page doesn't contain the token:

```bash
ssh ubuntu3 'source ~/stb-e2e.sh; curl -s $S/settings | grep -c "$T"'
```

Expected: `0`.

- [ ] **Step 5: Check that a block switched on reaches Plex**

```bash
ssh ubuntu3 'source ~/stb-e2e.sh
editorSave "[{\"portal\":\"$P\",\"channel id\":\"6637\",\"block\":\"ZZ Test\"},{\"portal\":\"$P\",\"channel id\":\"9750\",\"block\":\"ZZ Test\"}]"
lineupNumbers
toggleBlock "ZZ Test" true
lineupNumbers; lastSync; plexMap
curl -s $S/xmltv | grep -c "id=\"${P}6637\""
sleep 60; guideImport'
```

Expected:
- The first `lineupNumbers` shows 15, since the block is still off.
- After the toggle: `17 in lineup` including `3728` and `3730`.
- `lastSync` shows `Plex updated: 17 channels enabled`.
- `plexMap` shows `17 mapped, 17 enabled`, with `3730 48b21626fe5e4aaca795ebb4a4d5ad6b6637 on`.
- The XMLTV count is `1`.
- `guideImport` shows `database:` greater than `0.0`.

- [ ] **Step 6: Check that switching it off removes the channels**

```bash
ssh ubuntu3 'source ~/stb-e2e.sh; toggleBlock "ZZ Test" false; lineupNumbers; lastSync; plexMap'
```

Expected:
- `15 in lineup: 3597 … 3611`
- `Plex updated: 15 channels enabled`
- `15 mapped, 15 enabled`, with 3597–3611 mapped to `48b21626fe5e4aaca795ebb4a4d5ad6b` + `2032, 1401, 4858, 1490, 2039, 2082, 59790, 2020, 6642, 2128, 2116, 59796, 2006, 2134, 2148` respectively, the same as before this work

- [ ] **Step 7: Check dead marking**

```bash
ssh ubuntu3 'source ~/stb-e2e.sh; markDead 2032 true; plexMap | head -3; markDead 2032 false; plexMap | head -2'
```

Expected:
1. `{"dead":true,"plex":"Plex updated: 14 channels enabled"}`, then `14 mapped, 14 enabled`, with the first mapping `3598`.
2. `{"dead":false,"plex":"Plex updated: 15 channels enabled"}`, then `15 mapped, 15 enabled` and `3597 48b21626fe5e4aaca795ebb4a4d5ad6b2032 on`.

- [ ] **Step 8: Check what happens when Plex is down**

Point STB-Proxy at a port where nothing listens. An empty stdin keeps the saved token.

```bash
true | ssh proxmox 'pct exec 115 -- python3 -c "
import json, sys, urllib.parse, urllib.request
token = sys.stdin.read().strip()
settings = json.load(open(\"/opt/stb-proxy/config/config.json\"))[\"settings\"]
form = dict(settings, **{\"plex url\": \"http://192.168.5.3:1\", \"plex token\": token})
urllib.request.urlopen(\"http://127.0.0.1:8001/settings/save\", urllib.parse.urlencode(form).encode())
print(\"settings saved\")"'
ssh ubuntu3 'source ~/stb-e2e.sh; toggleBlock "ZZ Test" true; lastSync'
ssh proxmox 'pct exec 115 -- python3 -c "import json; c=json.load(open(\"/opt/stb-proxy/config/config.json\")); print(c[\"blocks\"], len(c[\"settings\"][\"plex token\"]))"'
ssh ubuntu3 'source ~/stb-e2e.sh; toggleBlock "ZZ Test" false'
```

Expected:
- `lastSync` shows `Plex not updated: couldn't reach Plex at http://192.168.5.3:1 (ConnectionError)`.
- The config shows `{'ZZ Test': 'true'} 20`: the block was saved and the token kept.

Restore the address, then retry with "Sync Plex now":

```bash
true | ssh proxmox 'pct exec 115 -- python3 -c "
import json, sys, urllib.parse, urllib.request
token = sys.stdin.read().strip()
settings = json.load(open(\"/opt/stb-proxy/config/config.json\"))[\"settings\"]
form = dict(settings, **{\"plex url\": \"http://192.168.5.3:32400\", \"plex token\": token})
urllib.request.urlopen(\"http://127.0.0.1:8001/settings/save\", urllib.parse.urlencode(form).encode())
print(\"settings saved\")"'
ssh ubuntu3 'source ~/stb-e2e.sh; curl -s -o /dev/null -X POST $S/blocks/sync; lastSync; plexMap | head -1'
```

Expected: `Plex updated: 15 channels enabled` and `15 mapped, 15 enabled`.

- [ ] **Step 9: Check the UI in a browser**

Use the Playwright MCP browser tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_take_screenshot`) against `http://192.168.5.71:8001`:

1. **Blocks page:** `/blocks` shows the "Blocks" nav item, the `ZZ Test` row reading "2 channels", and an off switch.
2. **Editor:** `/editor` shows the Block column with `ZZ Test` for SNY and the Dodgers channel (type `ZZ Test` in the filter box). The "Hide dead" switch is present and on.
3. **Preview and dead marking:** open the preview for the SNY row. The footer shows "Mark dead". Click it, and check that the status shows "Marked dead." and the row disappears (hidden as dead). Turn "Hide dead" off, and check the row reappears with a red "dead" badge. Open its preview, check the button reads "Mark working", and click it. Check the badge is gone.
4. **Block value escaping:** in the editor, type `Quote "test"` as a block name and save. Check the field shows `Quote "test"` after reload. Then clear it and save.

- [ ] **Step 10: Clean up**

```bash
ssh ubuntu3 'source ~/stb-e2e.sh
editorSave "[{\"portal\":\"$P\",\"channel id\":\"6637\",\"block\":\"\"},{\"portal\":\"$P\",\"channel id\":\"9750\",\"block\":\"\"}]"
curl -s $S/blocks | grep -c "No blocks yet"; lineupNumbers; plexMap | head -1
rm ~/stb-e2e.sh'
ssh proxmox 'pct exec 115 -- python3 -c "import json; c=json.load(open(\"/opt/stb-proxy/config/config.json\")); p=next(iter(c[\"portals\"].values())); print(c[\"blocks\"], p[\"channel blocks\"], p[\"dead channels\"], len(p[\"enabled channels\"]))"'
```

Expected:
- `1`, then `15 in lineup`, then `15 mapped, 15 enabled`
- `{} {} [] 15`

- [ ] **Step 11: Update the homelab memory note**

Append to `/home/greg/.claude/projects/-code/memory/homelab-layout.md`:

> STB-Proxy source of truth is `/code/stb-proxy` (deploy: git bundle fast-forward into `/opt/stb-proxy/app`, then restart). It has channel blocks (Blocks page), dead-channel marking in the editor preview, and Plex sync configured in Settings.
