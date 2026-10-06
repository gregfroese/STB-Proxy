// Channel name filters for the Playlist Editor (also loaded by tests under node).
//
// Modes:
//   words    - each word must appear as a whole word: "TSN" matches "TSN 1 FHD", not "SPORTSNET"
//   prefix   - each word must start a word: "sport" matches "SPORTSNET" and "Sports Max"
//   contains - each word may appear anywhere
//   exact    - the whole name, ignoring case and spacing; commas separate alternatives
//   regex    - a regular expression, case-insensitive
// For words/prefix/contains: words separated by spaces must all match, commas separate
// alternatives ("TSN, sportsnet"), a leading "-" excludes ("sportsnet -4k"), and quotes keep
// a phrase together ("sportsnet one").
(function (root) {
    function escapeRegex(s) {
        return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function normalise(s) {
        return String(s).toLowerCase().replace(/\s+/g, " ").trim();
    }

    function termMatcher(term, mode) {
        var t = escapeRegex(term.toLowerCase()).replace(/ +/g, "\\s+");
        if (mode === "contains") {
            return new RegExp(t, "i");
        }
        var start = "(^|[^a-z0-9])";
        return new RegExp(mode === "prefix" ? start + t : start + t + "($|[^a-z0-9])", "i");
    }

    // A function name -> bool for the query, null when there's nothing to filter by,
    // or {error: message} when it can't be understood.
    function parseChannelQuery(text, mode) {
        text = String(text || "").trim();
        if (!text) {
            return null;
        }
        if (mode === "regex") {
            var re;
            try {
                re = new RegExp(text, "i");
            } catch (e) {
                return { error: "Not a valid regex: " + e.message };
            }
            return function (name) { return re.test(name); };
        }
        if (mode === "exact") {
            var wanted = text.split(",").map(normalise).filter(Boolean);
            return function (name) { return wanted.indexOf(normalise(name)) !== -1; };
        }
        var groups = text.split(",").map(function (group) {
            var include = [], exclude = [];
            var token = /(-?)"([^"]*)"|(-?)(\S+)/g, m;
            while ((m = token.exec(group)) !== null) {
                var negate = (m[1] || m[3]) === "-";
                var word = m[2] !== undefined ? m[2] : m[4];
                if (!word) {
                    continue;
                }
                (negate ? exclude : include).push(termMatcher(word, mode));
            }
            return { include: include, exclude: exclude };
        }).filter(function (g) { return g.include.length || g.exclude.length; });
        if (!groups.length) {
            return null;
        }
        return function (name) {
            return groups.some(function (g) {
                return g.include.every(function (re) { return re.test(name); }) &&
                    !g.exclude.some(function (re) { return re.test(name); });
            });
        };
    }

    root.parseChannelQuery = parseChannelQuery;
    if (typeof module !== "undefined") {
        module.exports = { parseChannelQuery: parseChannelQuery };
    }
})(typeof window !== "undefined" ? window : this);
