package cc.selfhosters.stbproxy.ui.multiview

import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.ui.player.PlaybackError

/** Number of cells a Multiview grid always has (spec 2.7: TV 2x2). */
const val MULTIVIEW_SLOTS = 4

/**
 * Tuner budget used when `GET /discover.json` can't be read (spec 2.7). The
 * proxy's own `tunerCount()` floors at 1, but a budget of 1 would render a 2x2
 * grid almost entirely busy on first launch, so the app assumes the common
 * consumer tuner count of 2; discovery overwrites it when reachable.
 */
const val DEFAULT_TUNER_COUNT = 2

/**
 * One cell of the Multiview grid (GLOSSARY **Tile**). [slot] is the stable
 * identity of the cell so a Tile survives a swap/remove/reorder; [channel] is
 * the stream it currently shows, or null when empty.
 */
data class MultiviewTile(
    val slot: Int,
    val channel: Channel? = null,
)

/** A fresh grid of [count] empty tiles, slots `0 until count`. */
fun emptyTiles(count: Int = MULTIVIEW_SLOTS): List<MultiviewTile> =
    (0 until count).map { MultiviewTile(slot = it) }

/**
 * The slots that may open a stream given [tunerCount] (spec 2.7). Distinct
 * channels cost one tuner each; a later Tile on an already-open channel shares
 * it and costs nothing extra; empty Tiles never consume a tuner. Tiles whose
 * channel cannot get a tuner are left out and render "All tuners busy".
 *
 * Tiles are consumed in slot order, so which Tile loses the race is
 * deterministic.
 */
fun playableSlots(tiles: List<MultiviewTile>, tunerCount: Int): Set<Int> {
    val budget = tunerCount.coerceAtLeast(1)
    val opened = LinkedHashSet<Pair<String, String>>()
    val playable = LinkedHashSet<Int>()
    for (tile in tiles.sortedBy { it.slot }) {
        val channel = tile.channel ?: continue
        val key = channel.portal to channel.channelId
        if (key in opened || opened.size < budget) {
            opened.add(key)
            playable.add(tile.slot)
        }
    }
    return playable
}

/** Slots with a channel but no tuner to open it (spec 2.7). */
fun overBudgetSlots(tiles: List<MultiviewTile>, tunerCount: Int): Set<Int> {
    val playable = playableSlots(tiles, tunerCount)
    return tiles.filter { it.channel != null && it.slot !in playable }.map { it.slot }.toSet()
}

/** How many distinct channels the grid is asking for (the tuner-demand figure). */
fun distinctChannelCount(tiles: List<MultiviewTile>): Int =
    tiles.mapNotNull { it.channel }.distinctBy { it.portal to it.channelId }.size

/** Exchange the channels held by slots [a] and [b] (spec 2.7 Swap). */
fun swapTiles(tiles: List<MultiviewTile>, a: Int, b: Int): List<MultiviewTile> {
    if (a == b) return tiles
    val tileA = tiles.firstOrNull { it.slot == a } ?: return tiles
    val tileB = tiles.firstOrNull { it.slot == b } ?: return tiles
    return tiles.map {
        when (it.slot) {
            a -> it.copy(channel = tileB.channel)
            b -> it.copy(channel = tileA.channel)
            else -> it
        }
    }
}

/** Clear the channel held by [slot] (spec 2.7 Remove); the cell stays in place. */
fun removeTile(tiles: List<MultiviewTile>, slot: Int): List<MultiviewTile> =
    tiles.map { if (it.slot == slot) it.copy(channel = null) else it }

/** Put [channel] into [slot] (spec 2.7 Pick). */
fun assignChannel(tiles: List<MultiviewTile>, slot: Int, channel: Channel): List<MultiviewTile> =
    tiles.map { if (it.slot == slot) it.copy(channel = channel) else it }

/**
 * The single audio-source slot (spec 2.7). Exactly one Tile is unmuted:
 * [requested] when it still holds a channel, otherwise the lowest playable
 * non-empty slot; null when the grid is empty. When [playable] is supplied the
 * audio is kept on a Tile that can actually play, so a busy Tile never becomes
 * the (silent) audio source.
 */
fun effectiveAudioSlot(
    tiles: List<MultiviewTile>,
    requested: Int?,
    playable: Set<Int>? = null,
): Int? {
    val nonEmpty = tiles.filter { it.channel != null }.map { it.slot }.sorted()
    if (nonEmpty.isEmpty()) return null
    val pool = playable?.let { nonEmpty.filter(it::contains) }.orEmpty().ifEmpty { nonEmpty }
    return if (requested != null && requested in pool) requested else pool.first()
}

/** What a Tile renders (spec 2.7): the normal case is [Live]. */
sealed interface TileStatus {
    /** No channel assigned. */
    data object Empty : TileStatus

    /** A channel is assigned and the player is running (or connecting). */
    data object Live : TileStatus

    /** No free tuner: either proactively over budget or a live 503. */
    data object TunerBusy : TileStatus

    /** A per-Tile stream failure (unreachable / redirect). */
    data class Failed(val error: PlaybackError) : TileStatus
}

/**
 * Derives a Tile's status from the budget and its own last [error]. A live 503
 * is folded into [TileStatus.TunerBusy] so both the proactive and reactive cases
 * render the same inline state (spec 2.7).
 */
fun tileStatus(
    tile: MultiviewTile,
    overBudget: Set<Int>,
    error: PlaybackError?,
): TileStatus = when {
    tile.channel == null -> TileStatus.Empty
    error == PlaybackError.AllTunersBusy -> TileStatus.TunerBusy
    error != null -> TileStatus.Failed(error)
    tile.slot in overBudget -> TileStatus.TunerBusy
    else -> TileStatus.Live
}
