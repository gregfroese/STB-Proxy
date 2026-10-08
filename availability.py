"""Which channels STB-Proxy offers, given enabled channels, blocks and dead marks.

A channel is available when it is (individually enabled OR in a block that is
on) AND not marked dead. A channel can be in several blocks: each portal's
"channel blocks" is {channelId: [blockName, ...]}; whether a block is on lives
in config["blocks"] ({blockName: "true"|"false"}). Blocks named in
config["hidden blocks"] still work but are left out of the API.
"""


def channelBlockNames(value):
    # Configs from before channels could be in several blocks hold a single name.
    if isinstance(value, str):
        return [value] if value else []
    return list(value)


def normaliseChannelBlocks(channelBlocks):
    normalised = {}
    for channelId, value in channelBlocks.items():
        names = parseBlockNames(",".join(channelBlockNames(value)))
        if names:
            normalised[channelId] = names
    return normalised


def parseBlockNames(text):
    """Comma-separated block names, trimmed, without blanks or repeats, in order."""
    names = []
    for name in text.split(","):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


def availableChannels(portal, blocks):
    channels = set(portal.get("enabled channels", []))
    for channelId, names in portal.get("channel blocks", {}).items():
        if any(blocks.get(name) == "true" for name in channelBlockNames(names)):
            channels.add(channelId)
    return channels - set(portal.get("dead channels", []))


def blockNames(portals):
    names = set()
    for portal in portals.values():
        for value in portal.get("channel blocks", {}).values():
            names.update(channelBlockNames(value))
    return names


def pruneBlocks(portals, blocks):
    names = blockNames(portals)
    return {name: state for name, state in blocks.items() if name in names}


def renameBlock(portals, old, new):
    """Put every channel in block old into block new instead, in place."""
    for portal in portals.values():
        channelBlocks = portal.get("channel blocks", {})
        for channelId, value in channelBlocks.items():
            names = channelBlockNames(value)
            if old in names:
                channelBlocks[channelId] = parseBlockNames(",".join(new if n == old else n for n in names))


def blockSummaries(portals, blocks, hidden=()):
    summaries = {}
    for portal in portals.values():
        dead = set(portal.get("dead channels", []))
        for channelId, value in portal.get("channel blocks", {}).items():
            for name in channelBlockNames(value):
                summary = summaries.setdefault(
                    name,
                    {"name": name, "enabled": blocks.get(name) == "true", "hidden": name in hidden,
                     "channels": 0, "dead": 0},
                )
                summary["channels"] += 1
                if channelId in dead:
                    summary["dead"] += 1
    return [summaries[name] for name in sorted(summaries)]
