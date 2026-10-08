// Multiview's tiles and layout, kept in this browser, and helpers for picking channels.
// Shared by the Multiview page and the preview player's "Send to Multiview" (also loaded by
// tests under node).
//
// State: {layout, order, tiles, audio, big}
//   layout - "1", "2", "4", "9" or "big" (one big tile and three small)
//   order  - the nine tile indexes in the order they're shown; the first is the big one
//   tiles  - by tile index: {portal, channelId}, or null for an empty tile
//   audio  - the tile index whose sound plays
//   big    - the big tile's share of the width, in percent
(function (root) {
    var KEY = "stbMultiview";
    var TAB_KEY = "stbTab";
    var TILES = 9;
    var LAYOUTS = { "1": 1, "2": 2, "4": 4, "9": 9, "big": 4 };
    var BIGGER = { "1": "2", "2": "4", "4": "9", "big": "9" };

    function defaultState() {
        var order = [];
        var tiles = [];
        for (var i = 0; i < TILES; i++) {
            order.push(i);
            tiles.push(null);
        }
        return { layout: "4", order: order, tiles: tiles, audio: 0, big: 66 };
    }

    function isTileIndex(n) {
        return typeof n == "number" && n % 1 == 0 && n >= 0 && n < TILES;
    }

    // name: "localStorage" (the default) or "sessionStorage".
    function browserStorage(name) {
        try {
            if (root[name || "localStorage"]) {
                return root[name || "localStorage"];
            }
        } catch (e) { }
        return { getItem: function () { return null; }, setItem: function () { } };
    }

    function loadState(storage) {
        var state = defaultState();
        var saved;
        try {
            saved = JSON.parse(storage.getItem(KEY) || "null");
        } catch (e) {
            return state;
        }
        if (!saved || typeof saved != "object" || !LAYOUTS.hasOwnProperty(saved.layout) ||
            !Array.isArray(saved.tiles) || saved.tiles.length != TILES || !Array.isArray(saved.order)) {
            return state;
        }
        var order = saved.order.map(Number);
        if (order.slice().sort(function (a, b) { return a - b; }).join() != state.order.join()) {
            return state;
        }
        state.layout = saved.layout;
        state.order = order;
        state.tiles = saved.tiles.map(function (t) {
            return t && t.portal && t.channelId ? { portal: String(t.portal), channelId: String(t.channelId) } : null;
        });
        state.audio = isTileIndex(saved.audio) ? saved.audio : 0;
        state.big = typeof saved.big == "number" && saved.big >= 30 && saved.big <= 85 ? saved.big : 66;
        return state;
    }

    // This tab's id, kept in sessionStorage: the same across a reload, different in another
    // tab, so two tabs in one browser don't take each other's tiles.
    function tabId(storage) {
        var id = null;
        try {
            id = storage.getItem(TAB_KEY);
        } catch (e) { }
        if (!id) {
            id = Math.random().toString(36).slice(2, 10);
            try {
                storage.setItem(TAB_KEY, id);
            } catch (e) { }
        }
        return id;
    }

    function saveState(storage, state) {
        try {
            storage.setItem(KEY, JSON.stringify(state));
        } catch (e) { }
    }

    function shownCount(state) {
        return LAYOUTS[state.layout];
    }

    function firstEmptyTile(state) {
        for (var pos = 0; pos < shownCount(state); pos++) {
            if (!state.tiles[state.order[pos]]) {
                return state.order[pos];
            }
        }
        return null;
    }

    // Put a channel in the first empty tile on show, growing the layout if they're all full,
    // and give it the sound.
    function addChannel(storage, ch) {
        var state = loadState(storage);
        var tile = firstEmptyTile(state);
        while (tile === null && BIGGER[state.layout]) {
            state.layout = BIGGER[state.layout];
            tile = firstEmptyTile(state);
        }
        if (tile === null) {
            tile = state.audio;  // all nine are full: replace the one being listened to
        }
        state.tiles[tile] = { portal: String(ch.portal), channelId: String(ch.channelId) };
        state.audio = tile;
        saveState(storage, state);
        return state;
    }

    function channelName(row) {
        return row.customChannelName || row.channelName;
    }

    function channelNumber(row) {
        return (row.customChannelNumber || row.channelNumber) * 1 || 0;
    }

    function byNumber(a, b) {
        return channelNumber(a) - channelNumber(b) || channelName(a).localeCompare(channelName(b));
    }

    // Channels for the picker: favourites, then the lineup, each by number.
    function channelChoices(channels, matches, limit) {
        return channels
            .filter(function (row) { return !matches || matches(row); })
            .sort(function (a, b) {
                return (b.favourite - a.favourite) || (b.available - a.available) || byNumber(a, b);
            })
            .slice(0, limit);
    }

    // Channel up/down: the lineup's working channels, by number, wrapping round.
    function nextChannel(channels, current, step) {
        var lineup = channels.filter(function (row) { return row.available && !row.dead; }).sort(byNumber);
        if (!lineup.length) {
            return null;
        }
        var index = -1;
        for (var i = 0; i < lineup.length; i++) {
            if (lineup[i].portal == current.portal && lineup[i].channelId == current.channelId) {
                index = i;
            }
        }
        if (index == -1) {
            return lineup[step > 0 ? 0 : lineup.length - 1];
        }
        return lineup[(index + step + lineup.length) % lineup.length];
    }

    // What a tile does when its preview fails. reason is from /preview/status. A busy portal
    // gets one automatic retry; no free tuner, or a tuner taken back, waits for Try again,
    // so a page with more tiles than tuners doesn't keep asking.
    function failureAction(reason, retried) {
        if (reason == "busy" || reason == "client" || reason == "recording") {
            return reason;
        }
        return retried ? "failed" : "retry";
    }

    var api = {
        KEY: KEY,
        TILES: TILES,
        LAYOUTS: LAYOUTS,
        browserStorage: browserStorage,
        tabId: tabId,
        loadState: loadState,
        saveState: saveState,
        shownCount: shownCount,
        addChannel: addChannel,
        channelName: channelName,
        channelChoices: channelChoices,
        nextChannel: nextChannel,
        failureAction: failureAction,
    };
    root.multiview = api;
    if (typeof module !== "undefined") {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : this);
