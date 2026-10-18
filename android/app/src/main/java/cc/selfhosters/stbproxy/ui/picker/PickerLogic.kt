package cc.selfhosters.stbproxy.ui.picker

import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.data.model.Channel

/** Rail entry for public channels that sit in no visible Block (`blocks: []`) or genre. */
const val OTHER_BLOCK = "Other"

/** The picker's favourites filter (spec follow-up). */
enum class ChannelFilter(val label: String) {
    ALL("All"),
    FAVOURITES("★ Favourites"),
    BLOCK_FAVOURITES("★ Block faves"),
}

/** Keep only the channels the [filter] selects. */
fun applyChannelFilter(channels: List<Channel>, filter: ChannelFilter): List<Channel> = when (filter) {
    ChannelFilter.ALL -> channels
    ChannelFilter.FAVOURITES -> channels.filter { it.favourite }
    ChannelFilter.BLOCK_FAVOURITES -> channels.filter { it.blockFavourites.isNotEmpty() }
}

/** Favourites first (overall, then block favourites), then by number and name. */
fun sortChannels(channels: List<Channel>): List<Channel> = channels.sortedWith(
    compareBy({ !it.favourite }, { it.blockFavourites.isEmpty() }, { it.number ?: "" }, { it.name }),
)

/** One entry of the Block rail: a name plus its current channel count. */
data class BlockEntry(val name: String, val count: Int)

/**
 * The Block rail in `/api/lineup` `blocks` order (alphabetical), with an
 * "Other" entry appended **last** when any channel has no visible Block
 * (spec 2.5).
 */
fun blockRail(blocks: List<String>, channels: List<Channel>): List<BlockEntry> {
    val entries = blocks.map { name -> BlockEntry(name, channels.count { name in it.blocks }) }
    val ungrouped = channels.count { it.blocks.isEmpty() }
    return if (ungrouped > 0) entries + BlockEntry(OTHER_BLOCK, ungrouped) else entries
}

/** Channels belonging to [block]; "Other" means the ungrouped public channels. */
fun channelsInBlock(channels: List<Channel>, block: String): List<Channel> =
    if (block == OTHER_BLOCK) channels.filter { it.blocks.isEmpty() }
    else channels.filter { block in it.blocks }

/**
 * Case-insensitive search across every Block, matching a channel's name or
 * number. A blank query returns all channels.
 */
fun searchChannels(channels: List<Channel>, query: String): List<Channel> {
    val needle = query.trim().lowercase()
    if (needle.isEmpty()) return channels
    return channels.filter { channel ->
        channel.name.lowercase().contains(needle) ||
            channel.number?.contains(needle) == true
    }
}

/** Per-Block match counts for the search rail, keyed by rail entry name. */
fun blockMatchCounts(
    channels: List<Channel>,
    blockNames: List<String>,
    query: String,
): Map<String, Int> {
    val matched = searchChannels(channels, query)
    return blockNames.associateWith { block -> channelsInBlock(matched, block).size }
}

/**
 * The `+N` badge count: how many *other* Blocks this channel is in, beyond the
 * active rail entry. Zero while searching (all tags are shown) and on "Other".
 */
fun extraBlockCount(channel: Channel, activeBlock: String?, searching: Boolean): Int {
    if (searching || activeBlock == null || activeBlock == OTHER_BLOCK) return 0
    return channel.blocks.count { it != activeBlock }
}

/**
 * The Block a channel is launched into the player from (its zap list): the
 * active rail entry when the channel belongs to it, else the channel's first
 * Block, else "Other".
 */
fun launchBlockFor(channel: Channel, activeBlock: String?): String {
    if (activeBlock == OTHER_BLOCK && channel.blocks.isEmpty()) return OTHER_BLOCK
    if (activeBlock != null && activeBlock != OTHER_BLOCK && activeBlock in channel.blocks) {
        return activeBlock
    }
    return channel.blocks.firstOrNull() ?: OTHER_BLOCK
}

/**
 * The mode actually used: a preference of [GroupMode.BLOCKS] still falls back to
 * [GroupMode.GENRES] when the account has no visible Blocks, so nothing is
 * dumped into a lone "Other" bucket.
 */
fun effectiveGroupMode(pref: GroupMode, blocks: List<String>): GroupMode =
    if (blocks.isEmpty()) GroupMode.GENRES else pref

/** A channel's Genre as a rail name, or [OTHER_BLOCK] when the portal gave none. */
fun genreName(channel: Channel): String {
    val genre = channel.genre?.trim().orEmpty()
    return genre.ifEmpty { OTHER_BLOCK }
}

/** The Genre rail: distinct genres (case-insensitively sorted), "Other" last. */
fun genreRail(channels: List<Channel>): List<BlockEntry> {
    val canonical = linkedMapOf<String, String>()
    channels.forEach { channel ->
        val genre = channel.genre?.trim().orEmpty()
        if (genre.isNotEmpty()) canonical.putIfAbsent(genre.lowercase(), genre)
    }
    val entries = canonical.values
        .sortedBy { it.lowercase() }
        .map { name ->
            val count = channels.count { it.genre?.trim().orEmpty().lowercase() == name.lowercase() }
            BlockEntry(name, count)
        }
    val other = channels.count { it.genre?.trim().orEmpty().isEmpty() }
    return if (other > 0) entries + BlockEntry(OTHER_BLOCK, other) else entries
}

/** The rail for [mode]: Blocks in operator order, or Genres alphabetically. */
fun groupRail(mode: GroupMode, blocks: List<String>, channels: List<Channel>): List<BlockEntry> =
    if (mode == GroupMode.GENRES) genreRail(channels) else blockRail(blocks, channels)

/** Channels belonging to [group], interpreted by [mode]. */
fun channelsInGroup(mode: GroupMode, channels: List<Channel>, group: String): List<Channel> {
    if (mode == GroupMode.BLOCKS) return channelsInBlock(channels, group)
    val target = group.lowercase()
    return channels.filter { channel ->
        val genre = channel.genre?.trim().orEmpty()
        if (group == OTHER_BLOCK) genre.isEmpty() else genre.lowercase() == target
    }
}

/** Per-group match counts for the search rail, keyed by rail entry name. */
fun groupMatchCounts(
    mode: GroupMode,
    channels: List<Channel>,
    groupNames: List<String>,
    query: String,
): Map<String, Int> {
    val matched = searchChannels(channels, query)
    return groupNames.associateWith { group -> channelsInGroup(mode, matched, group).size }
}

/**
 * The `+N` badge: how many other groups the channel belongs to. Always 0 in
 * genre mode — a channel has exactly one genre.
 */
fun extraGroupCount(mode: GroupMode, channel: Channel, activeGroup: String?, searching: Boolean): Int =
    if (mode == GroupMode.GENRES) 0 else extraBlockCount(channel, activeGroup, searching)

/** The group a channel is launched into the player from (its zap list). */
fun launchGroupFor(mode: GroupMode, channel: Channel, activeGroup: String?): String =
    if (mode == GroupMode.GENRES) genreName(channel) else launchBlockFor(channel, activeGroup)
