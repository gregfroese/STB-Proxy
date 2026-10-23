package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandEpisode
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandProgress
import cc.selfhosters.stbproxy.data.model.OnDemandSeason
import cc.selfhosters.stbproxy.data.model.OnDemandUpNext
import cc.selfhosters.stbproxy.data.network.ApiException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TitleDetailLogicTest {

    private fun movie(progress: OnDemandProgress? = null) = OnDemandItem(
        portal = "p1",
        id = "m1",
        kind = OnDemandItem.MOVIE,
        name = "Heat",
        portalName = "Main",
        progress = progress,
    )

    private val heat = OnDemandKey.Movie("p1", "m1")

    // ---- a Movie's buttons ----

    @Test
    fun `a Movie with a Resume point offers Resume from mm-ss and Start over`() {
        val buttons = playButtons(movie(OnDemandProgress(positionSec = 754, durationSec = 6000)), null, null)
        assertEquals("▶ Resume from 12:34", buttons.primary.label)
        assertEquals(PlayChoice(heat, 754, "Heat"), buttons.primary.choice)
        assertEquals("Start over", buttons.startOver?.label)
        assertEquals(PlayChoice(heat, 0, "Heat"), buttons.startOver?.choice)
        assertEquals("Mark watched", buttons.watchedToggle)
    }

    @Test
    fun `a Watched Movie offers Play again from the start, even with a later Resume point`() {
        val buttons = playButtons(movie(OnDemandProgress(positionSec = 300, durationSec = 6000, watched = true)), null, null)
        assertEquals("▶ Play again", buttons.primary.label)
        assertEquals(PlayChoice(heat, 0, "Heat"), buttons.primary.choice)
        assertNull(buttons.startOver)
        assertEquals("✓ Watched", buttons.watchedToggle)
    }

    @Test
    fun `an unstarted Movie offers Play`() {
        val buttons = playButtons(movie(), null, null)
        assertEquals("▶ Play", buttons.primary.label)
        assertEquals(PlayChoice(heat, 0, "Heat"), buttons.primary.choice)
        assertNull(buttons.startOver)
        assertEquals("Mark watched", buttons.watchedToggle)
    }

    @Test
    fun `the detail's viewer state wins over the row's once it has loaded`() {
        val row = movie(OnDemandProgress(positionSec = 754, durationSec = 6000))
        val detail = OnDemandDetail(portal = "p1", id = "m1", name = "Heat", progress = null)
        assertEquals("▶ Play", playButtons(row, detail, null).primary.label)
    }

    // ---- a Series' button ----

    private fun series(upNext: OnDemandUpNext? = null) = OnDemandItem(
        portal = "p1",
        id = "s1",
        kind = OnDemandItem.SERIES,
        name = "Dark",
        portalName = "Main",
        upNext = upNext,
    )

    private fun seriesDetail(upNext: OnDemandUpNext? = null) = OnDemandDetail(
        portal = "p1",
        id = "s1",
        kind = OnDemandItem.SERIES,
        name = "Dark",
        upNext = upNext,
        seasons = listOf(OnDemandSeason("se1", number = 1), OnDemandSeason("se2", number = 2)),
    )

    private fun upNext(positionSec: Int? = null, name: String? = "Lost and Found") = OnDemandUpNext(
        seasonId = "se2",
        seasonNumber = 2,
        episodeId = "e24",
        episodeNumber = 4,
        name = name,
        positionSec = positionSec,
        durationSec = 3000,
    )

    private val s2e4 = OnDemandKey.Episode("p1", "s1", "se2", "e24")

    @Test
    fun `a Series with a started Up next resumes it, naming it and where`() {
        val buttons = playButtons(series(), seriesDetail(upNext(positionSec = 600)), null)
        assertEquals("▶ Resume S2 E4", buttons.primary.label)
        assertEquals(PlayChoice(s2e4, 600, "Dark", "S2 E4 · Lost and Found"), buttons.primary.choice)
        assertEquals("Lost and Found · from 10:00", buttons.note)
        assertNull(buttons.startOver)
        assertNull(buttons.watchedToggle)
    }

    @Test
    fun `a Series with an unstarted Up next plays it from the start`() {
        val buttons = playButtons(series(upNext()), null, null)
        assertEquals("▶ Play S2 E4", buttons.primary.label)
        assertEquals(PlayChoice(s2e4, 0, "Dark", "S2 E4 · Lost and Found"), buttons.primary.choice)
        assertEquals("Lost and Found", buttons.note)
    }

    @Test
    fun `an Up next with no name reads Episode n`() {
        val buttons = playButtons(series(upNext(positionSec = 90, name = null)), null, null)
        assertEquals("Episode 4 · from 1:30", buttons.note)
        assertEquals("S2 E4 · Episode 4", buttons.primary.choice?.subtitle)
    }

    @Test
    fun `a Series with no Up next plays S1 E1 once the first Season's Episodes are known`() {
        assertEquals(PlayButton("▶ Play S1 E1", null), playButtons(series(), seriesDetail(), null).primary)
        val episodes = listOf(
            OnDemandEpisode("e11", "se1", number = 1, name = "Secrets"),
            OnDemandEpisode("e12", "se1", number = 2),
        )
        val buttons = playButtons(series(), seriesDetail(), episodes)
        assertEquals("▶ Play S1 E1", buttons.primary.label)
        assertEquals(
            PlayChoice(OnDemandKey.Episode("p1", "s1", "se1", "e11"), 0, "Dark", "S1 E1 · Secrets"),
            buttons.primary.choice,
        )
        assertEquals("Secrets", buttons.note)
    }

    // ---- Seasons and Episodes ----

    @Test
    fun `Season chips open on the Up next Season, else the first`() {
        assertEquals("se2", openingSeason(seriesDetail(upNext())))
        assertEquals("se1", openingSeason(seriesDetail()))
        assertEquals("se1", openingSeason(seriesDetail(upNext().copy(seasonId = "gone"))))
        assertNull(openingSeason(seriesDetail().copy(seasons = emptyList())))
    }

    @Test
    fun `Episode rows show Watched, mm-ss in with a bar, and the Up next badge`() {
        val season = OnDemandSeason("se2", number = 2)
        val episodes = listOf(
            OnDemandEpisode("e21", "se2", number = 1, name = "Alpha", progress = OnDemandProgress(watched = true)),
            OnDemandEpisode("e22", "se2", number = 2, progress = OnDemandProgress(positionSec = 750, durationSec = 3000)),
            OnDemandEpisode("e24", "se2", number = 4, name = "Lost and Found"),
        )
        val rows = episodeRows(series(), season, episodes, upNext())

        assertEquals(listOf("1", "2", "4"), rows.map { it.number })
        assertEquals(listOf("Alpha", "Episode 2", "Lost and Found"), rows.map { it.name })
        assertEquals(listOf("✓ Watched", "12:30 in", null), rows.map { it.status })
        assertEquals(listOf(null, 0.25f, null), rows.map { it.progress })
        assertEquals(listOf(false, false, true), rows.map { it.upNext })
    }

    @Test
    fun `OK on an Episode plays it from its Resume point, or from the start once Watched`() {
        val season = OnDemandSeason("se2", number = 2)
        val episodes = listOf(
            OnDemandEpisode("e21", "se2", number = 1, name = "Alpha", progress = OnDemandProgress(positionSec = 900, watched = true)),
            OnDemandEpisode("e22", "se2", number = 2, progress = OnDemandProgress(positionSec = 750, durationSec = 3000)),
        )
        val rows = episodeRows(series(), season, episodes, null)
        assertEquals(
            PlayChoice(OnDemandKey.Episode("p1", "s1", "se2", "e21"), 0, "Dark", "S2 E1 · Alpha"),
            rows[0].choice,
        )
        assertEquals(750, rows[1].choice.startSec)
    }

    @Test
    fun `the Up next badge needs the same Season`() {
        val season = OnDemandSeason("se1", number = 1)
        val episodes = listOf(OnDemandEpisode("e24", "se1", number = 4))
        assertEquals(listOf(false), episodeRows(series(), season, episodes, upNext()).map { it.upNext })
    }

    // ---- inline errors under Play ----

    @Test
    fun `Play's busy, not found and portal errors use the web's wording`() {
        assertEquals(
            "Someone else on this login is already watching — On Demand uses the same stream as live TV. " +
                "Stop the other stream and try again.",
            playErrorText(ApiException(503, ApiException.BUSY, "All tuners are busy")),
        )
        assertEquals("This title isn't available any more.", playErrorText(ApiException(404, ApiException.NOT_FOUND)))
        assertEquals(
            "The portal didn't answer. Try again in a moment.",
            playErrorText(ApiException(502, ApiException.PORTAL_ERROR, "create_link failed")),
        )
    }

    @Test
    fun `other Play failures say what the server said, the status, or that it was unreachable`() {
        assertEquals(
            "This stream type isn't supported",
            playErrorText(ApiException(502, ApiException.UNSUPPORTED_STREAM, "This stream type isn't supported")),
        )
        assertEquals("Couldn't start playback (HTTP 500)", playErrorText(ApiException(500)))
        assertEquals("Couldn't reach the server", playErrorText(java.io.IOException("timeout")))
    }

    @Test
    fun `a failed Mark watched says it couldn't save`() {
        assertEquals("This title isn't available any more.", markErrorText(ApiException(404, ApiException.NOT_FOUND)))
        assertEquals("Couldn't save Watched (HTTP 500)", markErrorText(ApiException(500)))
    }
}
