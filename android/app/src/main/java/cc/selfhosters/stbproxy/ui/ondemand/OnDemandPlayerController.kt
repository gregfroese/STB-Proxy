package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.OnDemandChanges
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandEpisode
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandSeason
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What the controller needs of the Media3 player (a fake in tests). */
interface PlaybackPort {
    val positionMs: Long

    /** The loaded media's length, or null while unknown. */
    val durationMs: Long?

    /** The picture is moving (not paused, buffering or ended). */
    val isPlaying: Boolean

    /** Playing is wanted (false once paused). */
    val playWhenReady: Boolean

    /** Opens [url] and plays it from [startMs]. */
    fun load(url: String, startMs: Long)
    fun seekTo(ms: Long)
    fun play()
    fun pause()

    /** Stops loading (before a session is handed over, so the old one's 410 isn't seen). */
    fun stop()
}

/**
 * The session overlay: [message], one action ([action]: "▶ Resume from mm:ss" or
 * "Try again") that mints [resume] (with [replaces], if any), and Back.
 */
data class SessionOverlay(
    val message: String,
    val action: String,
    val resume: PlayChoice,
    val replaces: String?,
)

data class OnDemandPlayerState(
    /** What is playing: the key, the title and "S2 E3 · Name". */
    val choice: PlayChoice,
    /** The live session, or null once the server ended it. */
    val session: String?,
    val durationSec: Int?,
    /** A `POST /play` is in flight (the spinner). */
    val starting: Boolean = false,
    val overlay: SessionOverlay? = null,
    val endCard: EndCard? = null,
    val endSecondsLeft: Int? = null,
    /** The next Episode, or null for a Movie, the Series' last Episode, or while unknown. */
    val next: PlayChoice? = null,
    /** [next]'s Season number. */
    val nextSeasonNumber: Int? = null,
    /** The playing Episode's Season number. */
    val seasonNumber: Int? = null,
    /** A Movie's "year · n min". */
    val facts: String? = null,
    val description: String? = null,
    /** A one-off message (the idle restart's 503); [OnDemandPlayerController.toastShown] clears it. */
    val toast: String? = null,
    /** The player should close (the Watched card ran out). */
    val finished: Boolean = false,
)

/** The overlay wording for each 410 reason (the web's, ticket 09). */
fun sessionEndText(end: SessionEnd): String = when (end) {
    SessionEnd.EVICTED -> "Playback stopped — someone started watching on another device with this login, " +
        "and the provider only allows one stream at a time"
    SessionEnd.STOPPED -> "The stream was stopped from the server's Streams page."
    SessionEnd.IDLE, SessionEnd.UNKNOWN -> "Playback stopped — the stream ended on the server."
}

const val IDLE_RESTART_FAILED = "Couldn't restart — someone else on this login is watching."

/**
 * Runs one On Demand player (ticket 15): the session Play minted ([start]), progress
 * reports (every 30 s of playback, on pause, background, the end, a hand-over and
 * leaving), the end card and its hand-over with `replaces`, and the session states
 * (06): a silent restart after a 410 `idle`, and the overlay after `evicted`/`stopped`
 * or a failed mint.
 *
 * Calls are expected on the main thread. [background] outlives the screen (the last
 * report, the session `DELETE` and the change announcement on leave).
 */
class OnDemandPlayerController(
    start: OnDemandPlayStart,
    private val api: ApiClient,
    private val port: PlaybackPort,
    private val scope: CoroutineScope,
    private val background: CoroutineScope,
    private val changes: OnDemandChanges,
    private val clock: () -> Long,
    private val onUnauthorized: () -> Unit,
) {
    private val _state = MutableStateFlow(
        OnDemandPlayerState(
            choice = start.choice,
            session = start.playback.session,
            durationSec = start.playback.durationSec,
        ),
    )
    val state: StateFlow<OnDemandPlayerState> = _state.asStateFlow()

    private val firstUrl = start.playback.absoluteUrl
    private val end = EndOfPlayback(clock)
    private val schedule = ReportSchedule(clock)
    private var lastReport: Pair<OnDemandKey, Int>? = null
    private var closed = false
    private var mintJob: Job? = null

    private var lookedUp: OnDemandKey? = null
    private var series: OnDemandDetail? = null
    private val episodes = mutableMapOf<String, List<OnDemandEpisode>>()

    /** Plays the minted session from the chosen start, and looks up the title's facts. */
    fun begin() {
        port.load(firstUrl, _state.value.choice.startSec * 1000L)
        scope.launch { lookUp(_state.value.choice.key) }
    }

    /** Called about 4 times a second: the timed report and the end card's countdown. */
    fun tick() {
        if (schedule.tick(port.isPlaying)) report()
        when (val action = end.tick()) {
            is EndAction.PlayNext -> handOver(action.auto)
            EndAction.BackToDetails -> _state.update { it.copy(endCard = null, finished = true) }
            null -> Unit
        }
        val left = end.secondsLeft()
        if (left != _state.value.endSecondsLeft || end.card != _state.value.endCard) {
            _state.update { it.copy(endCard = end.card, endSecondsLeft = left) }
        }
    }

    /** Any key press or tap (resets the autoplay count). */
    fun input() = end.input()

    fun togglePause() {
        if (_state.value.endCard != null || _state.value.overlay != null) return
        if (port.playWhenReady) {
            port.pause()
            report()
        } else {
            port.play()
        }
    }

    /** A relative seek (± seconds); from the end card it dismisses the card and plays. */
    fun seekBy(seconds: Int) = seekTo(port.positionMs + seconds * 1000L)

    fun seekTo(ms: Long) {
        val duration = durationMs()
        val target = ms.coerceAtLeast(0).let { if (duration != null) it.coerceAtMost(duration - 1000).coerceAtLeast(0) else it }
        port.seekTo(target)
        if (end.card != null) {
            end.dismiss()
            port.play()
            _state.update { it.copy(endCard = null, endSecondsLeft = null) }
        }
    }

    /** Media3 reached the end. */
    fun onEnded() {
        if (_state.value.endCard != null) return
        report()
        end.ended(hasNext = _state.value.next != null)
        _state.update { it.copy(endCard = end.card, endSecondsLeft = end.secondsLeft()) }
    }

    /** ⏭ Next Episode, ▶ Play now and ▶ Continue: a manual hand-over. */
    fun nextEpisode() = handOver(auto = false)

    /** ↺ Play again: from 0:00 in the same session. */
    fun playAgain() {
        end.dismiss()
        port.seekTo(0)
        port.play()
        _state.update { it.copy(endCard = null, endSecondsLeft = null) }
    }

    /**
     * Media3 failed loading the playlist or a segment: [status] and [body] are the
     * HTTP answer's, when there was one.
     */
    fun onPlaybackFailed(status: Int?, body: ByteArray?) {
        val position = port.positionMs
        val choice = _state.value.choice.copy(startSec = (position / 1000).toInt())
        val old = _state.value.session
        when (val ended = sessionEndOf(status, body)) {
            SessionEnd.IDLE -> {
                // The session idled out (a long pause): restart where it was, silently,
                // still paused if it was.
                val wasPlaying = port.playWhenReady
                port.stop()
                mint(choice, replaces = old, idleRestart = true, play = wasPlaying)
            }
            null -> {
                report()
                _state.update {
                    it.copy(overlay = SessionOverlay(failedText(status), resumeLabel(choice), choice, replaces = old))
                }
            }
            else -> {
                report()
                _state.update {
                    it.copy(session = null, overlay = SessionOverlay(sessionEndText(ended), resumeLabel(choice), choice, null))
                }
            }
        }
    }

    /** The overlay's action: Resume / Try again. */
    fun resume() {
        val overlay = _state.value.overlay ?: return
        mint(overlay.resume, overlay.replaces)
    }

    /** The app went to the background: pause and report. */
    fun onStop() {
        if (port.playWhenReady) port.pause()
        report()
    }

    fun toastShown() = _state.update { it.copy(toast = null) }

    /**
     * Leaving the player: the last report, then the session's `DELETE`, then word
     * that the title's viewer state changed (rows, pane and Continue watching refetch).
     */
    fun close() {
        if (closed) return
        closed = true
        mintJob?.cancel()
        val state = _state.value
        val key = state.choice.key
        val position = (port.positionMs / 1000).toInt()
        val duration = durationSec()
        val send = lastReport != key to position
        background.launch {
            if (send) runCatching { api.reportOnDemandProgress(key, position, duration) }
            state.session?.let { sid -> runCatching { api.endOnDemandSession(sid) } }
            changes.changed(key.portal, key.titleId)
        }
    }

    private fun handOver(auto: Boolean) {
        val next = _state.value.next ?: return
        report()
        end.handedOver(auto)
        port.stop()
        mint(next, replaces = _state.value.session)
    }

    /** Starts [choice] in a new session (handing over [replaces]) and plays it. */
    private fun mint(choice: PlayChoice, replaces: String?, idleRestart: Boolean = false, play: Boolean = true) {
        _state.update {
            val other = it.choice.key != choice.key
            it.copy(
                starting = true, overlay = null, endCard = null, endSecondsLeft = null, choice = choice,
                next = if (other) null else it.next,
                nextSeasonNumber = if (other) null else it.nextSeasonNumber,
            )
        }
        mintJob?.cancel()
        mintJob = scope.launch {
            try {
                val playback = api.playOnDemand(choice.key, replaces)
                _state.update {
                    it.copy(starting = false, session = playback.session, durationSec = playback.durationSec)
                }
                schedule.reported()
                port.load(playback.absoluteUrl, choice.startSec * 1000L)
                if (!play) port.pause()
                if (choice.key != lookedUp) lookUp(choice.key)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (e is ApiException && e.code == 401) onUnauthorized()
                val busy = e is ApiException && e.code == 503
                if (idleRestart) report()
                _state.update {
                    it.copy(
                        starting = false,
                        session = if (idleRestart || replaces == null) null else it.session,
                        overlay = SessionOverlay(
                            message = playErrorText(e),
                            action = if (busy) "Try again" else resumeLabel(choice),
                            resume = choice,
                            replaces = null,
                        ),
                        toast = if (idleRestart && busy) IDLE_RESTART_FAILED else it.toast,
                    )
                }
            }
        }
    }

    /** A progress report (07) of the current position, unless it was just sent. */
    private fun report() {
        schedule.reported()
        val key = _state.value.choice.key
        val position = (port.positionMs / 1000).toInt()
        if (lastReport == key to position) return
        lastReport = key to position
        val duration = durationSec()
        scope.launch {
            try {
                api.reportOnDemandProgress(key, position, duration)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (e is ApiException && e.code == 401) onUnauthorized()
            }
        }
    }

    private fun durationSec(): Int? = _state.value.durationSec ?: port.durationMs?.let { (it / 1000).toInt() }

    private fun durationMs(): Long? = _state.value.durationSec?.let { it * 1000L } ?: port.durationMs

    /** The title's facts, and for an Episode its Season number and the next Episode. */
    private suspend fun lookUp(key: OnDemandKey) {
        lookedUp = key
        try {
            when (key) {
                is OnDemandKey.Movie -> {
                    val detail = api.fetchOnDemandItem(key.portal, key.id)
                    _state.update {
                        it.copy(
                            facts = listOfNotNull(detail.year?.toString(), detail.durationMin?.let { m -> "$m min" })
                                .joinToString(" · ").ifEmpty { null },
                            description = detail.description,
                        )
                    }
                }
                is OnDemandKey.Episode -> lookUpEpisode(key)
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // Try again with the next session (a Resume or a hand-over).
            lookedUp = null
            if (e is ApiException && e.code == 401) onUnauthorized()
        }
    }

    private suspend fun lookUpEpisode(key: OnDemandKey.Episode) {
        val detail = series ?: api.fetchOnDemandItem(key.portal, key.seriesId).also { series = it }
        val seasons = detail.seasons
        val index = seasons.indexOfFirst { it.id == key.seasonId }
        val season = seasons.getOrNull(index)
        _state.update { it.copy(seasonNumber = season?.number, description = detail.description) }
        if (season == null) return
        val item = OnDemandItem(portal = detail.portal, id = detail.id, kind = OnDemandItem.SERIES, name = detail.name)
        val rows = episodeRows(item, season, episodesOf(key, season), upNext = null)
        val at = rows.indexOfFirst { it.id == key.episodeId }
        val following = rows.getOrNull(at + 1)?.let { it.choice to season.number }
            ?: seasons.getOrNull(index + 1)?.let { nextSeason ->
                episodeRows(item, nextSeason, episodesOf(key, nextSeason), upNext = null).firstOrNull()
                    ?.let { it.choice to nextSeason.number }
            }
        // Only if the viewer is still on this Episode.
        _state.update {
            if (it.choice.key == key) it.copy(next = following?.first, nextSeasonNumber = following?.second) else it
        }
    }

    private suspend fun episodesOf(key: OnDemandKey.Episode, season: OnDemandSeason): List<OnDemandEpisode> =
        episodes[season.id] ?: api.fetchOnDemandSeason(key.portal, key.seriesId, season.id).also { episodes[season.id] = it }

    private fun resumeLabel(choice: PlayChoice) = "▶ Resume from ${clock(choice.startSec)}"

    private fun failedText(status: Int?) =
        if (status != null) "Playback failed (HTTP $status)." else "Playback failed — the stream couldn't be reached."
}
