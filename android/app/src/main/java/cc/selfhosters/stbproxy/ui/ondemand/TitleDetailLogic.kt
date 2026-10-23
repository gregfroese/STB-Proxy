package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandEpisode
import cc.selfhosters.stbproxy.data.model.OnDemandSeason
import cc.selfhosters.stbproxy.data.model.OnDemandUpNext
import cc.selfhosters.stbproxy.data.network.ApiException

/*
 * Pure logic behind a title's Play buttons, Seasons and Episodes (ticket 14): the TV
 * preview pane and the phone detail page share it, with the web's button rules.
 */

/**
 * What a Play button hands the player: the item, where to start (seconds) and what
 * to call it ([title], plus "S2 E3 · Name" for an Episode).
 */
data class PlayChoice(
    val key: OnDemandKey,
    val startSec: Int,
    val title: String,
    val subtitle: String? = null,
)

/** One button; [choice] is null while it can't start yet (a Series' first Episode unknown). */
data class PlayButton(val label: String, val choice: PlayChoice?)

/**
 * A title's buttons: the main Play/Resume, Start over (a Movie with a Resume point),
 * the Series' note beside the button ("Name · from 12:34") and a Movie's Mark watched
 * toggle text (null for a Series).
 */
data class PlayButtons(
    val primary: PlayButton,
    val startOver: PlayButton? = null,
    val note: String? = null,
    val watchedToggle: String? = null,
)

/**
 * The buttons for [item] (the row, shown at once), using [detail]'s fresher viewer
 * state once it has loaded. [firstSeasonEpisodes] are a Series' first Season's
 * Episodes, needed only to start "S1 E1" when there is no Up next.
 */
fun playButtons(
    item: OnDemandItem,
    detail: OnDemandDetail?,
    firstSeasonEpisodes: List<OnDemandEpisode>?,
): PlayButtons {
    if (item.isSeries) return seriesButton(item, detail, firstSeasonEpisodes)
    val progress = if (detail != null) detail.progress else item.progress
    val key = OnDemandKey.Movie(item.portal, item.id)
    val fromStart = PlayChoice(key, 0, item.name)
    val toggle = watchedToggleText(progress?.watched == true)
    val resumeAt = progress?.positionSec?.takeIf { !progress.watched && it > 0 }
    return when {
        progress?.watched == true -> PlayButtons(PlayButton("▶ Play again", fromStart), watchedToggle = toggle)
        resumeAt != null -> PlayButtons(
            primary = PlayButton("▶ Resume from ${clock(resumeAt)}", fromStart.copy(startSec = resumeAt)),
            startOver = PlayButton("Start over", fromStart),
            watchedToggle = toggle,
        )
        else -> PlayButtons(PlayButton("▶ Play", fromStart), watchedToggle = toggle)
    }
}

/** ▶ Resume/Play S<n> E<n> from Up next, else ▶ Play S1 E1 (the first Season's first Episode). */
private fun seriesButton(
    item: OnDemandItem,
    detail: OnDemandDetail?,
    firstSeasonEpisodes: List<OnDemandEpisode>?,
): PlayButtons {
    val next = if (detail != null) detail.upNext else item.upNext
    if (next != null) {
        val code = episodeCode(next.seasonNumber, next.episodeNumber)
        val name = episodeName(next.name, next.episodeNumber)
        val resumeAt = next.positionSec?.takeIf { it > 0 }
        val choice = PlayChoice(
            key = OnDemandKey.Episode(item.portal, item.id, next.seasonId, next.episodeId),
            startSec = resumeAt ?: 0,
            title = item.name,
            subtitle = listOf(code, name).filter { it.isNotEmpty() }.joinToString(" · "),
        )
        return PlayButtons(
            primary = PlayButton(spaced(if (resumeAt != null) "▶ Resume" else "▶ Play", code), choice),
            note = if (resumeAt != null) "$name · from ${clock(resumeAt)}" else name,
        )
    }
    val first = firstSeasonEpisodes?.firstOrNull()
    val season = detail?.seasons?.firstOrNull()
    if (first == null || season == null) return PlayButtons(PlayButton("▶ Play S1 E1", null))
    val code = episodeCode(season.number ?: 1, first.number ?: 1)
    val name = episodeName(first.name, first.number)
    return PlayButtons(
        primary = PlayButton(
            "▶ Play $code",
            PlayChoice(
                key = OnDemandKey.Episode(item.portal, item.id, season.id, first.id),
                startSec = 0,
                title = item.name,
                subtitle = "$code · $name",
            ),
        ),
        note = name,
    )
}

/** The Season the chips open on: Up next's, else the first; null for no Seasons. */
fun openingSeason(detail: OnDemandDetail): String? =
    detail.upNext?.seasonId?.takeIf { id -> detail.seasons.any { it.id == id } }
        ?: detail.seasons.firstOrNull()?.id

/**
 * One Episode row: its number, name (or "Episode n"), "✓ Watched" or "mm:ss in", the
 * thin bar, whether it is Up next, and what OK plays (from its Resume point unless
 * Watched).
 */
data class EpisodeRow(
    val id: String,
    val number: String,
    val name: String,
    val status: String?,
    val progress: Float?,
    val upNext: Boolean,
    val choice: PlayChoice,
    val watched: Boolean = false,
)

fun episodeRows(
    series: OnDemandItem,
    season: OnDemandSeason,
    episodes: List<OnDemandEpisode>,
    upNext: OnDemandUpNext?,
): List<EpisodeRow> = episodes.mapIndexed { index, episode ->
    val progress = episode.progress
    val watched = progress?.watched == true
    val resumeAt = progress?.positionSec?.takeIf { !watched && it > 0 }
    val name = episodeName(episode.name, episode.number)
    val code = episodeCode(season.number, episode.number)
    EpisodeRow(
        id = episode.id,
        number = (episode.number ?: (index + 1)).toString(),
        name = name,
        status = when {
            watched -> "✓ Watched"
            resumeAt != null -> "${clock(resumeAt)} in"
            else -> null
        },
        progress = progressFraction(progress),
        upNext = upNext != null && upNext.seasonId == season.id && upNext.episodeId == episode.id,
        choice = PlayChoice(
            key = OnDemandKey.Episode(series.portal, series.id, season.id, episode.id),
            startSec = resumeAt ?: 0,
            title = series.name,
            subtitle = listOf(code, name).filter { it.isNotEmpty() }.joinToString(" · "),
        ),
        watched = watched,
    )
}

/** "S2 E4"; a part the server didn't number is left out. */
fun episodeCode(seasonNumber: Int?, episodeNumber: Int?): String = listOfNotNull(
    seasonNumber?.let { "S$it" },
    episodeNumber?.let { "E$it" },
).joinToString(" ")

/** An Episode's name, or "Episode n" (Xtream/legacy Episodes have none). */
fun episodeName(name: String?, number: Int?): String =
    name?.takeIf { it.isNotBlank() } ?: number?.let { "Episode $it" } ?: "Episode"

private fun spaced(vararg parts: String): String = parts.filter { it.isNotEmpty() }.joinToString(" ")

/** The inline error under Play: the web's wording for busy/not_found/portal_error. */
fun playErrorText(error: Exception): String = actionErrorText(error, "start playback")

/** The inline error after a failed Mark watched. */
fun markErrorText(error: Exception): String = actionErrorText(error, "save Watched")

private fun actionErrorText(error: Exception, what: String): String = when (error) {
    is ApiException -> error.errorCode?.let(ON_DEMAND_ERROR_TEXT::get)
        ?: error.serverMessage
        ?: "Couldn't $what (HTTP ${error.code})"
    else -> "Couldn't reach the server"
}

/** The Mark watched toggle: "✓ Watched" once Watched, else "Mark watched". */
fun watchedToggleText(watched: Boolean): String = if (watched) "✓ Watched" else "Mark watched"
