package cc.selfhosters.stbproxy.ui.ondemand

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.math.sign

/*
 * Pure logic behind the On Demand player (ticket 15; decision: ticket 11's answer):
 * the TV seek speed-up, the phone's double-tap, the end card, report scheduling and
 * reading a 410's reason. Clocks are injected milliseconds, so tests drive time.
 */

/** The step a held ← → reaches: 10 s, 30 s after 1 s, 60 s after 3 s. */
fun seekStepSec(heldMs: Long): Int = when {
    heldMs < 1_000 -> 10
    heldMs < 3_000 -> 30
    else -> 60
}

/** A held key steps at most this often (about 5 steps a second). */
const val SEEK_REPEAT_MS = 180L

/**
 * TV ← → seeking: each press seeks straight away; holding the key speeds it up
 * ([seekStepSec]) and steps about 5 times a second.
 */
class SeekKeys(private val clock: () -> Long) {
    private var holdStart = 0L
    private var lastStep = 0L

    /**
     * A press of ← (`direction` -1) or → (+1); [repeat] for the key's auto-repeat.
     * Returns the signed seconds to seek, or null for a repeat that comes too soon.
     */
    fun press(direction: Int, repeat: Boolean): Int? {
        val now = clock()
        if (!repeat) {
            holdStart = now
        } else if (now - lastStep < SEEK_REPEAT_MS) {
            return null
        }
        lastStep = now
        return direction.sign * seekStepSec(now - holdStart)
    }
}

/** A phone double-tap at [xFraction] of the picture's width: ∓10 s on a side, else null. */
fun doubleTapSeek(xFraction: Float): Int? = when {
    xFraction < 0.4f -> -10
    xFraction > 0.6f -> 10
    else -> null
}

/** The end card's countdown (to the next Episode, or back to details). */
const val END_CARD_MS = 15_000L

/** Autoplays in a row with no input before the player asks "Still watching?". */
const val AUTOPLAY_LIMIT = 3

/** What the player shows once an item has played to its end (B's end card). */
enum class EndCard {
    /** "Next Episode · in 15 s" with ▶ Play now and Back to Episodes. */
    Next,

    /** "Still watching <Series>?" with ▶ Continue and Back; no countdown. */
    StillWatching,

    /** ✓ Watched (a Movie or the last Episode) with ↺ Play again and Back to details. */
    Watched,
}

/** What an end card's countdown asks for when it runs out. */
sealed interface EndAction {
    data class PlayNext(val auto: Boolean) : EndAction
    data object BackToDetails : EndAction
}

/**
 * The end of playback, the same as the web player (ticket 12): the end card, its
 * 15 s countdown and the autoplay count behind "Still watching?". Any input resets
 * the count, as does a manual hand-over.
 */
class EndOfPlayback(private val clock: () -> Long) {
    var card: EndCard? = null
        private set

    private var shownAt = 0L
    private var autoplays = 0

    /** The item played to its end; [hasNext] when a next Episode follows. */
    fun ended(hasNext: Boolean) {
        shownAt = clock()
        card = when {
            !hasNext -> EndCard.Watched
            autoplays >= AUTOPLAY_LIMIT -> EndCard.StillWatching
            else -> EndCard.Next
        }
    }

    /** A key press or tap. */
    fun input() {
        autoplays = 0
    }

    /** Called regularly: the countdown's action once it has run out (once), else null. */
    fun tick(): EndAction? {
        val card = card ?: return null
        if (card == EndCard.StillWatching || clock() - shownAt < END_CARD_MS) return null
        this.card = null
        return if (card == EndCard.Next) EndAction.PlayNext(auto = true) else EndAction.BackToDetails
    }

    /** Whole seconds left on the countdown, or null when no countdown runs. */
    fun secondsLeft(): Int? {
        val card = card ?: return null
        if (card == EndCard.StillWatching) return null
        val left = END_CARD_MS - (clock() - shownAt)
        return ((left.coerceAtLeast(0) + 999) / 1000).toInt()
    }

    /** The next Episode took over: by the countdown ([auto]) or by the viewer. */
    fun handedOver(auto: Boolean) {
        card = null
        autoplays = if (auto) autoplays + 1 else 0
    }

    /** The card went away without a hand-over (Play again, a seek back). */
    fun dismiss() {
        card = null
    }
}

/** Progress is reported after this much playback (ADR 0006), besides the event reports. */
const val REPORT_EVERY_MS = 30_000L

/**
 * When the next timed progress report is due: after [REPORT_EVERY_MS] of playback
 * (time spent paused or buffering doesn't count). Any report restarts it.
 */
class ReportSchedule(private val clock: () -> Long, private val everyMs: Long = REPORT_EVERY_MS) {
    private var lastTick: Long? = null
    private var playedMs = 0L

    /** Called regularly with whether the picture is playing; true once a report is due. */
    fun tick(playing: Boolean): Boolean {
        val now = clock()
        val last = lastTick
        if (playing && last != null) playedMs += now - last
        lastTick = now
        return playedMs >= everyMs
    }

    /** A report went out (timed or not). */
    fun reported() {
        playedMs = 0
    }
}

/** Why the server ended an On Demand session (06's 410 `session_ended` reasons). */
enum class SessionEnd {
    /** 120 s without a request: restart silently with `replaces`. */
    IDLE,

    /** A newer session on the same login took the stream. */
    EVICTED,

    /** The stream stopped coming from the portal (a timeout, a dropped connection, a 5xx). */
    FAILED,

    /** Stopped from the operator's Streams page. */
    STOPPED,

    /** A 410 whose body didn't say. */
    UNKNOWN,
}

private val reasonJson = Json { ignoreUnknownKeys = true }

/**
 * A failed media request's [status] and [body] (Media3 keeps the error body) as the
 * session's end, or null when it wasn't a 410.
 */
fun sessionEndOf(status: Int?, body: ByteArray?): SessionEnd? {
    if (status != 410) return null
    val reason = runCatching {
        val obj = reasonJson.parseToJsonElement(body?.decodeToString().orEmpty()) as? JsonObject
        (obj?.get("reason") as? JsonPrimitive)?.content
    }.getOrNull()
    return when (reason) {
        "idle" -> SessionEnd.IDLE
        "evicted" -> SessionEnd.EVICTED
        "failed" -> SessionEnd.FAILED
        "stopped" -> SessionEnd.STOPPED
        else -> SessionEnd.UNKNOWN
    }
}
