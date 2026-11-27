package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandDownloadBrief
import cc.selfhosters.stbproxy.data.model.OnDemandEpisode
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandSeason
import cc.selfhosters.stbproxy.data.network.ApiException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class DownloadLogicTest {

    private fun brief(status: String, progress: Int = 0, mine: Boolean = false) =
        OnDemandDownloadBrief("d1", status, progress, mine = mine)

    // ---- the Download button (the web's wording) ----

    @Test
    fun `the button reads Download, Queued, Paused, Downloading, Downloaded or failed`() {
        assertEquals(DownloadButton("Download", canStart = true), downloadButton(null))
        assertEquals(DownloadButton("Queued", canStart = false), downloadButton(brief("queued")))
        assertEquals(DownloadButton("Paused at 37%", canStart = false), downloadButton(brief("queued", 37)))
        assertEquals(DownloadButton("Downloading 42%", canStart = false), downloadButton(brief("downloading", 42)))
        assertEquals(DownloadButton("Downloaded", canStart = false), downloadButton(brief("done", 100)))
        assertEquals(DownloadButton("Download failed – try again", canStart = true), downloadButton(brief("failed", 12)))
    }

    @Test
    fun `an Episode row says its download status, and a failure without try again`() {
        assertNull(episodeDownloadText(null))
        assertEquals("Downloading 42%", episodeDownloadText(brief("downloading", 42)))
        assertEquals("Paused at 5%", episodeDownloadText(brief("queued", 5)))
        assertEquals("Downloaded", episodeDownloadText(brief("done", 100)))
        assertEquals("Download failed", episodeDownloadText(brief("failed")))
    }

    @Test
    fun `only the viewer's own unfinished download can be cancelled`() {
        assertFalse(canCancelDownload(null))
        assertTrue(canCancelDownload(brief("queued", mine = true)))
        assertTrue(canCancelDownload(brief("downloading", 10, mine = true)))
        assertTrue(canCancelDownload(brief("failed", mine = true)))
        assertFalse(canCancelDownload(brief("done", 100, mine = true)))
        assertFalse(canCancelDownload(brief("queued", mine = false)))
    }

    @Test
    fun `queued and downloading are active, the rest are not`() {
        assertFalse(isDownloadActive(null))
        assertTrue(isDownloadActive(brief("queued")))
        assertTrue(isDownloadActive(brief("downloading", 3)))
        assertFalse(isDownloadActive(brief("done", 100)))
        assertFalse(isDownloadActive(brief("failed")))
    }

    @Test
    fun `the Season button names the Season's number, else its place`() {
        assertEquals("Download Season 3", seasonDownloadLabel(OnDemandSeason("s3", number = 3), 0))
        assertEquals("Download Season 2", seasonDownloadLabel(OnDemandSeason("x"), 1))
    }

    @Test
    fun `a download error shows the server's text`() {
        assertEquals(
            "Downloads are off for this Account",
            downloadErrorText(ApiException(403, "downloads_off", "Downloads are off for this Account")),
        )
        assertEquals("Couldn't ask for the download (HTTP 500)", downloadErrorText(ApiException(500)))
        assertEquals("Couldn't reach the server", downloadErrorText(IOException("down")))
    }

    // ---- the detail state ----

    private val movie = OnDemandDetail(portal = "p1", id = "m1", kind = "movie", name = "Heat", canDownload = true)
    private val series = OnDemandDetail(
        portal = "p1",
        id = "s1",
        kind = "series",
        name = "Dark",
        canDownload = true,
        seasons = listOf(OnDemandSeason("se1", number = 1), OnDemandSeason("se2", number = 2)),
    )

    private fun state(detail: OnDemandDetail, episodes: Map<String, List<OnDemandEpisode>> = emptyMap()) =
        TitleDetailState(item = detail.asItem(), detail = detail, seasonId = detail.seasons.lastOrNull()?.id, episodes = episodes)

    @Test
    fun `a Movie offers Download only when the server allows it`() {
        assertEquals(DownloadButton("Download", true), state(movie).movieDownload)
        assertNull(state(movie.copy(canDownload = false)).movieDownload)
        assertNull(state(series).movieDownload)
        assertNull(TitleDetailState(item = movie.asItem()).movieDownload)
    }

    @Test
    fun `a Series offers its shown Season's download`() {
        assertEquals(DownloadButton("Download Season 2", true), state(series).seasonDownload)
        assertNull(state(series.copy(canDownload = false)).seasonDownload)
        assertNull(state(movie).seasonDownload)
    }

    @Test
    fun `a Season's button says when every Episode is asked for`() {
        val season = series.seasons.last().id
        fun with(vararg statuses: String?) = state(series, mapOf(season to statuses.mapIndexed { i, s ->
            OnDemandEpisode("e$i", season, number = i + 1, download = s?.let { brief(it) })
        })).seasonDownload
        assertEquals(DownloadButton("Download Season 2", true), with("queued", null))
        assertEquals(DownloadButton("Download Season 2", true), with("done", "failed"))
        assertEquals(DownloadButton("Season queued (1 of 3 downloaded)", false), with("done", "downloading", "queued"))
        assertEquals(DownloadButton(SEASON_DOWNLOADED, false), with("done", "done"))
    }

    @Test
    fun `Cancel download is offered for the viewer's own unfinished Movie download`() {
        assertTrue(state(movie.copy(download = brief("queued", mine = true))).canCancelMovieDownload)
        assertFalse(state(movie.copy(download = brief("queued"))).canCancelMovieDownload)
        assertFalse(state(movie.copy(download = brief("done", 100, mine = true))).canCancelMovieDownload)
    }

    @Test
    fun `Episode rows carry their download text`() {
        val season = OnDemandSeason("se1", number = 1)
        val rows = episodeRows(
            series.asItem(),
            season,
            listOf(
                OnDemandEpisode("e1", "se1", number = 1, download = brief("downloading", 42)),
                OnDemandEpisode("e2", "se1", number = 2),
            ),
            null,
        )
        assertEquals(listOf("Downloading 42%", null), rows.map { it.download })
    }

    @Test
    fun `an active download anywhere on the title keeps the page looking`() {
        assertFalse(state(movie).hasActiveDownload)
        assertTrue(state(movie.copy(download = brief("queued"))).hasActiveDownload)
        assertFalse(state(movie.copy(download = brief("done", 100))).hasActiveDownload)
        val episodes = mapOf(
            "se1" to listOf(OnDemandEpisode("e1", "se1", download = brief("done", 100))),
            "se2" to listOf(OnDemandEpisode("e2", "se2", download = brief("downloading", 3))),
        )
        assertTrue(state(series, episodes).hasActiveDownload)
    }

    @Test
    fun `briefs land on the Movie and on matching Episodes`() {
        val done = OnDemandDownloadBrief("d9", "done", 100)
        val movieState = state(movie).withDownloads(
            mapOf(downloadKey(OnDemandKey.Movie("p1", "m1")) to done),
            complete = false,
        )
        assertEquals(done, movieState.detail?.download)

        val old = brief("queued")
        val episodes = mapOf(
            "se1" to listOf(OnDemandEpisode("e1", "se1"), OnDemandEpisode("e2", "se1", download = old)),
        )
        val update = mapOf(downloadKey(OnDemandKey.Episode("p1", "s1", "se1", "e1")) to done)

        // A POST's answer names only what it touched: the rest keep their briefs.
        val posted = state(series, episodes).withDownloads(update, complete = false)
        assertEquals(listOf(done, old), posted.episodes.getValue("se1").map { it.download })

        // The full list is the truth: what isn't in it has no download any more.
        val polled = state(series, episodes).withDownloads(update, complete = true)
        assertEquals(listOf(done, null), polled.episodes.getValue("se1").map { it.download })
    }

    @Test
    fun `download keys tell a Movie from an Episode`() {
        assertEquals(downloadKey(OnDemandKey.Movie("p1", "m1")), downloadKey(OnDemandKey.Movie("p1", "m1")))
        assertFalse(
            downloadKey(OnDemandKey.Movie("p1", "e1")) == downloadKey(OnDemandKey.Episode("p1", "s1", "se1", "e1")),
        )
    }
}
