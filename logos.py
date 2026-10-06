"""Channel logos matched by name from the iptv-org database (https://github.com/iptv-org/database).

Portals often send no logos. iptv-org lists ~30k channels with logo URLs; a channel
whose cleaned-up name matches exactly one of them (or one in the country its name
starts with, as in "UK | ...") gets that logo. Ambiguous names get none: no logo is
better than the wrong one.
"""
import re

CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"
LOGOS_URL = "https://iptv-org.github.io/api/logos.json"
FEEDS_URL = "https://iptv-org.github.io/api/feeds.json"

# "UK | Sky Sports", "CA: TSN", "ES - MOVISTAR": a 2-3 letter country code before a separator.
COUNTRY_PREFIX = re.compile(r"^\s*([A-Za-z]{2,3})\s*[|:]\s*")
OTHER_PREFIX = re.compile(r"^\s*(LIVE|VIP|24/7)\s*[|:]\s*", re.I)
# Quality and status words that aren't part of the channel's name.
TAGS = re.compile(
    r"\b(FHD|UHD|HD|SD|4K|8K|HEVC|H\.?265|H\.?264|1080[PI]?|720P|50FPS|60FPS|RAW|BACKUP|"
    r"MULTI\s*AUDIO|LIVE|UPCOMING|REPLAY|ALT|VIP)\b",
    re.I,
)
TRAILING = re.compile(r"[\s\-|:()\[\]]+$")
# iptv-org uses ISO codes; portals often say UK for GB.
COUNTRY_ALIASES = {"UK": "UK", "GB": "UK", "EN": "UK", "USA": "US"}


# Countries a portal's category (genre) names often spell out, e.g. "ENGLISH | CANADA".
GROUP_COUNTRIES = {
    "CANADA": "CA", "CANADIAN": "CA", "USA": "US", "UNITED STATES": "US", "AMERICA": "US", "UK": "UK",
    "UNITED KINGDOM": "UK", "BRITISH": "UK", "IRELAND": "IE", "AUSTRALIA": "AU", "NEW ZEALAND": "NZ",
    "MEXICO": "MX", "SPAIN": "ES", "ARGENTINA": "AR", "CHILE": "CL", "COLOMBIA": "CO", "PERU": "PE",
    "ECUADOR": "EC", "PARAGUAY": "PY", "URUGUAY": "UY", "VENEZUELA": "VE", "BRAZIL": "BR", "PORTUGAL": "PT",
    "FRANCE": "FR", "BELGIUM": "BE", "SWITZERLAND": "CH", "GERMANY": "DE", "AUSTRIA": "AT", "ITALY": "IT",
    "NETHERLANDS": "NL", "POLAND": "PL", "GREECE": "GR", "TURKEY": "TR", "SWEDEN": "SE", "NORWAY": "NO",
    "DENMARK": "DK", "FINLAND": "FI", "ROMANIA": "RO", "INDIA": "IN", "PAKISTAN": "PK", "PHILIPPINES": "PH",
}


def groupCountry(group):
    words = " " + re.sub(r"[^A-Z ]", " ", (group or "").upper()) + " "
    for name, code in GROUP_COUNTRIES.items():
        if " " + name + " " in words:
            return code
    return None


def key(name):
    """A name reduced to lower-case letters and digits, for exact comparison."""
    return re.sub(r"[^0-9a-z+]", "", name.casefold().replace("&", "and"))


def clean(name):
    """(country hint or None, the channel's name without prefixes, tags or suffixes)."""
    country = None
    m = COUNTRY_PREFIX.match(name)
    if m:
        country = COUNTRY_ALIASES.get(m.group(1).upper(), m.group(1).upper())
        name = name[m.end():]
    name = OTHER_PREFIX.sub("", name)
    name = re.sub(r"\(.*?\)|\[.*?\]", " ", name)
    name = re.sub(r"\s+-\s+.*$", "", name)  # "MX | DAZN 13 - UPCOMING" -> "DAZN 13"
    name = TAGS.sub(" ", name)
    name = TRAILING.sub("", name).strip()
    return country, name


def buildIndex(channels, logos, feeds=()):
    """{name key: [(country, logo url), ...]} from iptv-org's channels, logos and feeds.

    Feeds (regional versions such as "Sportsnet East") are indexed as the channel's name
    followed by the feed's, with the feed's own logo if it has one.
    """
    best = {}
    for logo in logos:
        # Prefer a logo still in use; for a channel, prefer its main logo (no feed).
        target = (logo["channel"], logo.get("feed"))
        rank = not logo.get("in_use", True)
        current = best.get(target)
        if current is None or rank < current[0]:
            best[target] = (rank, logo["url"])

    def channelLogo(channelId, feedId=None):
        found = best.get((channelId, feedId)) or best.get((channelId, None))
        return found[1] if found else None

    index = {}

    def add(name, country, url):
        k = key(name)
        if k and (country, url) not in index.setdefault(k, []):
            index[k].append((country, url))

    named = {}
    for channel in channels:
        if channel.get("closed"):
            continue
        country = (channel.get("country") or "").upper()
        names = [channel["name"]] + list(channel.get("alt_names") or [])
        named[channel["id"]] = (country, names)
        url = channelLogo(channel["id"])
        if url:
            for name in names:
                add(name, country, url)
    for feed in feeds:
        if feed["channel"] not in named:
            continue
        country, names = named[feed["channel"]]
        url = channelLogo(feed["channel"], feed["id"])
        if url:
            for name in names:
                for feedName in [feed["name"]] + list(feed.get("alt_names") or []):
                    add(name + " " + feedName, country, url)
    return index


def candidates(index, name):
    """(country hint, [(country, url), ...]) for a channel name."""
    country, cleaned = clean(name)
    return country, index.get(key(cleaned), [])


def pick(found, country):
    """The logo from the given country, or the only logo among the candidates, or None."""
    if country:
        # Any of the country's own entries has the right brand; take the first listed.
        local = [url for c, url in found if c == country]
        if local:
            return local[0]
    urls = {url for _, url in found}
    return urls.pop() if len(urls) == 1 else None


def matchAll(index, entries):
    """{channel id: logo url} for [(channel id, name, group)].

    A name that several countries use is settled by the country in its name ("UK | ...")
    or its group (the portal's genre, e.g. "ENGLISH | CANADA"), then by the country most
    common among the clear matches in the same group, then in the whole list.
    """
    logos = {}
    countries = {}
    pending = []
    byCountry = {}
    for channelId, name, group in entries:
        hint, found = candidates(index, name)
        if not found:
            continue
        url = pick(found, hint or groupCountry(group))
        if url:
            logos[channelId] = url
            country = next(c for c, u in found if u == url)
            countries.setdefault(group, {}).setdefault(country, 0)
            countries[group][country] += 1
            byCountry[country] = byCountry.get(country, 0) + 1
        else:
            pending.append((channelId, group, found))

    def favourite(counts, found):
        options = {c for c, _ in found}
        ranked = sorted(((counts.get(c, 0), c) for c in options), reverse=True)
        if ranked and ranked[0][0] > 0 and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
            return ranked[0][1]
        return None

    for channelId, group, found in pending:
        country = favourite(countries.get(group, {}), found) or favourite(byCountry, found)
        url = pick(found, country) if country else None
        if url:
            logos[channelId] = url
    return logos


def match(index, name):
    """The logo URL for one channel name, or None if there's no single clear match."""
    hint, found = candidates(index, name)
    return pick(found, hint) if found else None
