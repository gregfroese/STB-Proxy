// Recording helpers for the Recordings page, the preview player and Multiview (also loaded
// by tests under node).
(function (root) {
    function formatSize(bytes) {
        if (bytes >= Math.pow(1024, 3)) {
            return (bytes / Math.pow(1024, 3)).toFixed(1).replace(/\.0$/, "") + " GB";
        }
        if (bytes >= 1024 * 1024) {
            return (bytes / 1024 / 1024).toFixed(1).replace(/\.0$/, "") + " MB";
        }
        return Math.round(bytes / 1024) + " KB";
    }

    function formatDuration(seconds) {
        seconds = Math.max(0, Math.round(seconds));
        var h = Math.floor(seconds / 3600);
        var m = Math.floor(seconds % 3600 / 60);
        var s = seconds % 60;
        var mm = h ? (m < 10 ? "0" : "") + m : String(m);
        return (h ? h + ":" : "") + mm + ":" + (s < 10 ? "0" : "") + s;
    }

    // How long to record: until stopped, until the programme on now ends (if known), or a while.
    function recordOptions(now, programme) {
        var options = [{ label: "Until I stop it" }];
        if (programme && programme.stop > now) {
            options.push({ label: "Until " + programme.title + " ends", until: programme.stop });
        }
        options.push({ label: "30 minutes", minutes: 30 });
        options.push({ label: "1 hour", minutes: 60 });
        options.push({ label: "2 hours", minutes: 120 });
        return options;
    }

    // "portal/channelId" -> recording id, for every channel being recorded now.
    function recordingChannels(recordings) {
        var keys = {};
        recordings.forEach(function (rec) {
            if (rec.status == "recording") {
                keys[rec.portal + "/" + rec.channelId] = rec.id;
            }
        });
        return keys;
    }

    var api = {
        formatSize: formatSize,
        formatDuration: formatDuration,
        recordOptions: recordOptions,
        recordingChannels: recordingChannels,
    };
    root.stbRecordings = api;
    if (typeof module !== "undefined") {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : this);
