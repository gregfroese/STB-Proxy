"""A searchable programme guide covering every channel on the portals.

The portal's bulk EPG for all channels is large (tens of MB of JSON), so
only what search needs is kept: one (start, stop, title, desc, portal,
channelId) tuple per programme that hasn't finished yet.
"""

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


def search(programmes, query, now, keep=None, onNow=False, limit=300):
    """Programmes still to finish whose title or description has every word of query.

    keep(portalId, channelId) narrows to some channels. Returns (first `limit`
    matches by start time, total number of matches).
    """
    words = query.lower().split()
    matches = []
    for p in programmes:
        start, stop, title, desc, portalId, channelId = p
        if stop <= now or (onNow and start > now):
            continue
        if words:
            text = (title + "\n" + desc).lower()
            if not all(w in text for w in words):
                continue
        if keep and not keep(portalId, channelId):
            continue
        matches.append(p)
    matches.sort(key=lambda p: (p[0], p[2]))
    return matches[:limit], len(matches)
