package cc.selfhosters.stbproxy.ui.guide

import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.model.GuideHit
import java.time.Instant

/** The operator's five match modes (ticket 09), defaulting to prefix. */
enum class GuideMode(val wire: String) {
    PREFIX("prefix"),
    WORDS("words"),
    CONTAINS("contains"),
    EXACT("exact"),
    REGEX("regex"),
}

const val GUIDE_LIMIT_DEFAULT = 200
const val GUIDE_LIMIT_MAX = 500
const val GUIDE_LIMIT_STEP = 200
const val GUIDE_DEBOUNCE_MS = 300L

/** "Showing first N of Y" while more results exist, else a plain count. */
fun resultCountLabel(shown: Int, total: Int): String = when {
    total > shown -> "Showing first $shown of $total"
    total == 1 -> "1 result"
    else -> "$total results"
}

/** The next page size for "Load more", capped at the maximum. */
fun nextGuideLimit(current: Int): Int = (current + GUIDE_LIMIT_STEP).coerceAtMost(GUIDE_LIMIT_MAX)

/** A Channel's identity — the GLOSSARY's `(portal, channelId)` pair, as one key. */
fun channelKey(channel: Channel): String = "${channel.portal}:${channel.channelId}"

/** The distinct Channels a set of hits airs on, in first-seen order (search zap scope). */
fun hitChannels(hits: List<GuideHit>, channels: List<Channel>): List<Channel> {
    val wanted = channels.associateBy { channelKey(it) }
    val seen = mutableSetOf<String>()
    val out = mutableListOf<Channel>()
    for (hit in hits) {
        val key = "${hit.portal}:${hit.channelId}"
        val channel = wanted[key] ?: continue
        if (seen.add(key)) out.add(channel)
    }
    return out
}

/** The channels whose current Programme is airing at [now] (the "On now" filter). */
fun airingChannels(
    channels: List<Channel>,
    nowNext: Map<String, NowNext>,
    now: Instant,
): List<Channel> = channels.filter { channel ->
    val current = channel.epgId?.let { nowNext[it]?.now } ?: return@filter false
    val stop = current.stop
    !current.start.isAfter(now) && (stop == null || now.isBefore(stop))
}

/** The channel-name/number sub-filter. */
fun filterGuideChannels(channels: List<Channel>, text: String): List<Channel> {
    val needle = text.trim().lowercase()
    if (needle.isEmpty()) return channels
    return channels.filter {
        it.name.lowercase().contains(needle) || it.number?.contains(needle) == true
    }
}

/** True while a guide programme is on air at [now] (epoch seconds). */
fun programmeAiring(start: Long, stop: Long, now: Long): Boolean = start <= now && stop > now

/** The partial/unavailable-portals note shown above results, or null. */
fun guideNotice(failed: List<String>, partial: List<String>): String? {
    val parts = buildList {
        if (failed.isNotEmpty()) add("Guide unavailable for ${failed.joinToString(", ")}")
        if (partial.isNotEmpty()) add("Partial guide for ${partial.joinToString(", ")}")
    }
    return parts.takeIf { it.isNotEmpty() }?.joinToString(" · ")
}
