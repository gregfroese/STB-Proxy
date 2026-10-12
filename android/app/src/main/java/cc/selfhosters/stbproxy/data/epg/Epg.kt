package cc.selfhosters.stbproxy.data.epg

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * One XMLTV programme (spec 2.8). [stop] is nullable: the `getShortEpg`
 * fallback may omit it.
 */
data class Programme(
    val title: String,
    val start: Instant,
    val stop: Instant? = null,
    val description: String? = null,
) {
    /** `HH:mm–HH:mm` (or just the start when [stop] is missing) in [zone]. */
    fun timeRange(zone: ZoneId): String {
        val startText = TIME_FORMAT.format(start.atZone(zone))
        val stopText = stop?.let { TIME_FORMAT.format(it.atZone(zone)) }
        return if (stopText != null) "$startText–$stopText" else startText
    }

    companion object {
        private val TIME_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")
    }
}

/**
 * The only two programmes the picker/player needs per channel (spec 2.6/2.8):
 * the one airing now and the earliest one still to come.
 */
data class NowNext(
    val now: Programme? = null,
    val next: Programme? = null,
)
