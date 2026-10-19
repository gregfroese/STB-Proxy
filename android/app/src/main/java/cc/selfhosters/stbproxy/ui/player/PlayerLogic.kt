package cc.selfhosters.stbproxy.ui.player

import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.data.ZapScope
import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.epg.Programme
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.ui.picker.channelsInGroup
import java.time.Duration
import java.time.Instant

/**
 * The three stream failures the player surfaces over the video (spec 2.6). The
 * normal, playing case is represented by `null`; this sealed type is only the
 * error taxonomy.
 */
sealed interface PlaybackError {
    /** HTTP 503: every tuner is busy. */
    data object AllTunersBusy : PlaybackError

    /** Network/DNS/timeout or any other non-2xx that isn't the two cases below. */
    data object Unreachable : PlaybackError

    /** A 3xx that reached the data source (cross-protocol / not auto-followed). */
    data class RedirectingToPortal(val target: String?) : PlaybackError
}

/**
 * Response info distilled from a Media3 source exception. Keeping this plain
 * (no Media3/Android types) lets the classification be JVM unit-tested.
 */
data class SourceErrorInfo(
    val isHttpResponse: Boolean = false,
    val responseCode: Int? = null,
    val location: String? = null,
)

/**
 * Maps a surfaced source exception to one of the three error states (spec 2.6).
 * A 503 is "all tuners busy", a 3xx is a redirect diagnostic, and everything
 * else (including a plain network failure) is "unreachable".
 */
fun classifySourceError(info: SourceErrorInfo): PlaybackError {
    if (info.isHttpResponse) {
        when (info.responseCode) {
            503 -> return PlaybackError.AllTunersBusy
            301, 302, 303, 307, 308 -> return PlaybackError.RedirectingToPortal(info.location)
        }
    }
    return PlaybackError.Unreachable
}

/** What the EPG ticker should do on a wake-up (spec 2.6). */
enum class EpgRefreshAction { NONE, RECOMPUTE, REFETCH }

/** True once [now] has entered a different wall-clock minute than [lastComputedAt]. */
fun minuteBoundaryPassed(now: Instant, lastComputedAt: Instant): Boolean =
    now.epochSecond / 60 != lastComputedAt.epochSecond / 60

/** True once the currently-airing programme's `stop` has been reached. */
fun programmeBoundaryPassed(now: Instant, currentStop: Instant?): Boolean =
    currentStop != null && !now.isBefore(currentStop)

/**
 * The refresh decision (spec 2.6): re-fetch `/xmltv` on app foreground and when
 * the current programme ends; otherwise just recompute against the fresh clock
 * every minute.
 */
fun epgRefreshAction(
    now: Instant,
    lastComputedAt: Instant,
    currentStop: Instant?,
    foregrounded: Boolean = false,
): EpgRefreshAction = when {
    foregrounded || programmeBoundaryPassed(now, currentStop) -> EpgRefreshAction.REFETCH
    minuteBoundaryPassed(now, lastComputedAt) -> EpgRefreshAction.RECOMPUTE
    else -> EpgRefreshAction.NONE
}

/**
 * Re-derives the now/next to display at [now] from a stored snapshot. While the
 * stored `now` is still airing it is kept; once it has ended, the stored `next`
 * is promoted if it has started. A programme with a null `stop` never expires.
 */
fun resolveNowNext(stored: NowNext?, now: Instant): NowNext? {
    val snapshot = stored ?: return null
    val current = snapshot.now
    val stillAiring = current != null &&
        !current.start.isAfter(now) &&
        (current.stop == null || now.isBefore(current.stop))
    if (stillAiring) return snapshot

    val promoted = snapshot.next?.takeIf { !it.start.isAfter(now) }
    return if (promoted != null) {
        NowNext(now = promoted, next = null)
    } else {
        NowNext(now = null, next = snapshot.next)
    }
}

/** Fraction of [programme] elapsed at [now], clamped to 0..1; 0 when unbounded. */
fun programmeProgress(programme: Programme?, now: Instant): Float {
    val stop = programme?.stop ?: return 0f
    val total = Duration.between(programme.start, stop).toMillis()
    if (total <= 0) return 0f
    val elapsed = Duration.between(programme.start, now).toMillis()
    return (elapsed.toFloat() / total.toFloat()).coerceIn(0f, 1f)
}

/**
 * The channel up/down list for a player launched from [launchGroup] (spec 2.6):
 * the channels of that group — a Block (so a channel in several Blocks walks the
 * one it was launched from) or a Genre, per [mode].
 */
fun zapList(
    channels: List<Channel>,
    launchGroup: String,
    mode: GroupMode = GroupMode.BLOCKS,
): List<Channel> = channelsInGroup(mode, channels, launchGroup)

/**
 * The ordered up/down list for a player launched under [scope] (ticket 07): a
 * [ZapScope.Group] re-derives from the lineup as today; a [ZapScope.Channels]
 * list maps its keys to the lineup, preserving order, and keeps [launched] even
 * when the set no longer holds it.
 */
fun scopeZapList(
    channels: List<Channel>,
    scope: ZapScope,
    mode: GroupMode,
    launched: Channel?,
): List<Channel> = when (scope) {
    is ZapScope.Group -> channelsInGroup(mode, channels, scope.block)
    is ZapScope.Channels -> {
        val byKey = channels.associateBy { "${it.portal}:${it.channelId}" }
        val seen = mutableSetOf<String>()
        val out = mutableListOf<Channel>()
        for (key in scope.keys) {
            val channel = byKey[key] ?: continue
            if (seen.add(key)) out.add(channel)
        }
        if (launched != null) {
            val key = "${launched.portal}:${launched.channelId}"
            if (key !in seen) out.add(0, launched)
        }
        out
    }
}

/** The label a scope shows in the sidebar heading and the live badge (ticket 07). */
fun scopeLabel(scope: ZapScope): String = when (scope) {
    is ZapScope.Group -> scope.label.ifEmpty { scope.block }
    is ZapScope.Channels -> scope.label
}

/** Steps [current] by [delta] through every [channels] entry, wrapping (Multiview, ticket 10). */
fun zapWithin(channels: List<Channel>, current: Channel, delta: Int): Channel? {
    if (channels.isEmpty()) return null
    val index = channels.indexOfFirst { it.portal == current.portal && it.channelId == current.channelId }
    return channels.getOrNull(zapIndex(channels.size, if (index < 0) 0 else index, delta))
}

/** Steps [current] by [delta] within a list of [size], wrapping; -1 when empty. */
fun zapIndex(size: Int, current: Int, delta: Int): Int {
    if (size <= 0) return -1
    return ((current + delta) % size + size) % size
}

/**
 * The channel [delta] steps away from [current] in [launchBlock]'s list,
 * wrapping at both ends; null when the list is empty. If [current] isn't in the
 * list the step starts from the first entry.
 */
fun zapTarget(
    channels: List<Channel>,
    launchGroup: String,
    current: Channel,
    delta: Int,
    mode: GroupMode = GroupMode.BLOCKS,
): Channel? {
    val list = zapList(channels, launchGroup, mode)
    if (list.isEmpty()) return null
    val index = list.indexOfFirst {
        it.portal == current.portal && it.channelId == current.channelId
    }
    return list.getOrNull(zapIndex(list.size, if (index < 0) 0 else index, delta))
}

/**
 * Whether the player should start in full-screen (immersive) mode. TV is always
 * full-screen already, so only phones matter, and there a phone in landscape
 * fills the screen while portrait keeps the video above the now/next sheet.
 */
fun shouldAutoFullscreen(isTv: Boolean, isLandscape: Boolean): Boolean = !isTv && isLandscape
