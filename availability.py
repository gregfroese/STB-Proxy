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
