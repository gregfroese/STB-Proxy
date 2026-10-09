// Multiview's tiles and layout, kept in this browser, and helpers for picking channels.
// Shared by the Multiview page and the preview player's "Send to Multiview" (also loaded by
// tests under node).
//
// State: {layout, order, tiles, audio, big}
//   layout - "1", "2", "4", "9" or "big" (one big tile and three small)
//   order  - the nine tile indexes in the order they're shown; the first is the big one
//   tiles  - by tile index: {portal, channelId}, or null for an empty tile; picked from a
//            block, also {block, favouritesOnly}, so channel up/down stays in that list
//   audio  - the tile index whose sound plays
//   big    - the big tile's share of the width, in percent
//   beforeBig - {layout, order} to go back to after making a tile big, or null
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
        return { layout: "4", order: order, tiles: tiles, audio: 0, big: 66, beforeBig: null };
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

    function isOrder(order) {
        return Array.isArray(order) && order.length == TILES &&
            order.map(Number).sort(function (a, b) { return a - b; }).join() == defaultState().order.join();
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
            if (!t || !t.portal || !t.channelId) {
                return null;
            }
            var tile = { portal: String(t.portal), channelId: String(t.channelId) };
            if (typeof t.block == "string" && t.block) {
                tile.block = t.block;
                tile.favouritesOnly = t.favouritesOnly === true;
            }
            return tile;
        });
        state.audio = isTileIndex(saved.audio) ? saved.audio : 0;
        state.big = typeof saved.big == "number" && saved.big >= 30 && saved.big <= 85 ? saved.big : 66;
        var back = saved.beforeBig;
        if (back && typeof back == "object" && LAYOUTS.hasOwnProperty(back.layout) && back.layout != "big" && isOrder(back.order)) {
            state.beforeBig = { layout: back.layout, order: back.order.map(Number) };
        }
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

    // A layout picked from the toolbar: forget the view to go back to.
    function chooseLayout(state, layout) {
        state.layout = layout;
        state.beforeBig = null;
    }

    // Whether tile i's make-big button goes back to the view from before.
    function canGoBack(state, i) {
        return !!state.beforeBig && state.layout == "big" && state.order[0] == i;
    }

    // Make tile i the big one, remembering the view before; on the big tile, go back to it.
    function toggleBig(state, i) {
        if (canGoBack(state, i)) {
            state.layout = state.beforeBig.layout;
            state.order = state.beforeBig.order.slice();
            state.beforeBig = null;
            return;
        }
        if (state.layout != "big") {
            state.beforeBig = { layout: state.layout, order: state.order.slice() };
        }
        state.order = [i].concat(state.order.filter(function (x) { return x != i; }));
        state.layout = "big";
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

    // The picker's Favourites tab: favourites by number. matches(row), or null for all.
    function favouriteChoices(channels, matches) {
        return channels
            .filter(function (row) { return row.favourite && (!matches || matches(row)); })
            .sort(byNumber);
    }

    // The picker's Blocks tab: blocks that are on (enabledBlocks) and have channels here,
    // by name, with how many. matches(name), or null for all.
    function blockChoices(channels, enabledBlocks, matches) {
        var counts = {};
        channels.forEach(function (row) {
            (row.blocks || []).forEach(function (name) {
                counts[name] = (counts[name] || 0) + 1;
            });
        });
        return enabledBlocks
            .filter(function (name) { return counts[name] && (!matches || matches(name)); })
            .sort(function (a, b) { return a.localeCompare(b); })
            .map(function (name) { return { name: name, channels: counts[name] }; });
    }

    // matches(row) for a block's own favourites.
    function isBlockFavouriteIn(name) {
        return function (row) { return (row.blockFavourites || []).indexOf(name) != -1; };
    }

    // One block's channels: its favourites first, then by number. matches(row), or null for all.
    function blockChannels(channels, name, matches) {
        var favourite = isBlockFavouriteIn(name);
        return channels
            .filter(function (row) { return (row.blocks || []).indexOf(name) != -1 && (!matches || matches(row)); })
            .sort(function (a, b) { return (favourite(b) - favourite(a)) || byNumber(a, b); });
    }

    // Channel up/down through a list, wrapping round; from outside the list, its first (or last).
    function nextInList(list, current, step) {
        if (!list.length) {
            return null;
        }
        var index = -1;
        for (var i = 0; i < list.length; i++) {
            if (list[i].portal == current.portal && list[i].channelId == current.channelId) {
                index = i;
            }
        }
        if (index == -1) {
            return list[step > 0 ? 0 : list.length - 1];
        }
        return list[(index + step + list.length) % list.length];
    }

    // Channel up/down: the lineup's working channels, by number.
    function nextChannel(channels, current, step) {
        return nextInList(channels.filter(function (row) { return row.available && !row.dead; }).sort(byNumber), current, step);
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
        favouriteChoices: favouriteChoices,
        blockChoices: blockChoices,
        blockChannels: blockChannels,
        isBlockFavouriteIn: isBlockFavouriteIn,
        nextInList: nextInList,
        chooseLayout: chooseLayout,
        canGoBack: canGoBack,
        toggleBig: toggleBig,
        nextChannel: nextChannel,
        failureAction: failureAction,
    };
    root.multiview = api;
    if (typeof module !== "undefined") {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : this);
