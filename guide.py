"""A searchable programme guide covering every channel on the portals.

The portal's bulk EPG for all channels is large (tens of MB of JSON), so
only what search needs is kept: one (start, stop, title, desc, portal,
channelId) tuple per programme that hasn't finished yet.
"""

import re

DESC_LENGTH = 300


def programmes(portalId, epg, now):
    out = []
    for channelId, entries in epg.items():
        for p in entries or []:
            try:
                start = int(p.get("start_timestamp"))
                stop = int(p.get("stop_timestamp"))
            except (TypeError, ValueError):
                continue
            if stop <= now:
                continue
            title = str(p.get("name") or "").strip()
            if not title:
                continue
            desc = str(p.get("descr") or "").strip()[:DESC_LENGTH]
            out.append((start, stop, title, desc, portalId, str(channelId)))
    return out


def termPattern(term, mode):
    t = re.escape(term.lower()).replace(r"\ ", " ")
    t = re.sub(" +", r"\\s+", t)
    if mode == "contains":
        return re.compile(t, re.I)
    start = "(^|[^a-z0-9])"
    return re.compile(start + t if mode == "prefix" else start + t + "($|[^a-z0-9])", re.I)


def normalise(text):
    return " ".join(str(text).lower().split())


def parseQuery(text, mode="words"):
    """A test text -> bool, or None if there's nothing to search for. Raises ValueError for a bad regex.

    The same language as static/channel-filter.js: words (whole words), prefix (words
    start with), contains, exact (the whole text; commas separate alternatives) or regex.
    Otherwise words must all match, commas separate alternatives, "-word" leaves out and
    quotes keep a phrase together.
    """
    text = (text or "").strip()
    if not text:
        return None
    if mode == "regex":
        try:
            pattern = re.compile(text, re.I)
        except re.error as e:
            raise ValueError("Not a valid regex: {}".format(e))
        return lambda s: bool(pattern.search(s))
    if mode == "exact":
        wanted = {normalise(t) for t in text.split(",") if normalise(t)}
        return lambda s: normalise(s) in wanted
    groups = []
    for group in text.split(","):
        include, exclude = [], []
        for m in re.finditer(r'(-?)"([^"]*)"|(-?)(\S+)', group):
            negate = (m.group(1) or m.group(3)) == "-"
            word = m.group(2) if m.group(2) is not None else m.group(4)
            if word:
                (exclude if negate else include).append(termPattern(word, mode))
        if include or exclude:
            groups.append((include, exclude))
    if not groups:
        return None
    return lambda s: any(
        all(p.search(s) for p in include) and not any(p.search(s) for p in exclude) for include, exclude in groups
    )


def search(programmes, query, now, keep=None, onNow=False, limit=300, mode="words"):
    """Programmes still to finish whose title or description matches query (see parseQuery).

    keep(portalId, channelId) narrows to some channels. Returns (first `limit`
    matches by start time, total number of matches).
    """
    test = parseQuery(query, mode)
    matches = []
    for p in programmes:
        start, stop, title, desc, portalId, channelId = p
        if stop <= now or (onNow and start > now):
            continue
        if test and not test(title + "\n" + desc):
            continue
        if keep and not keep(portalId, channelId):
            continue
        matches.append(p)
    matches.sort(key=lambda p: (p[0], p[2]))
    return matches[:limit], len(matches)
