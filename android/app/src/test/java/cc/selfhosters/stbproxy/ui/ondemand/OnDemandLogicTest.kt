package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandCategory
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandPortalStatus
import cc.selfhosters.stbproxy.data.model.OnDemandProgress
import cc.selfhosters.stbproxy.data.model.OnDemandSeason
import cc.selfhosters.stbproxy.data.model.OnDemandUpNext
import cc.selfhosters.stbproxy.data.network.ApiException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OnDemandLogicTest {

    private fun movie(
        id: String,
        name: String = "Movie $id",
        year: Int? = null,
        rating: Double? = null,
        progress: OnDemandProgress? = null,
    ) = OnDemandItem(
        portal = "p1",
        id = id,
        kind = OnDemandItem.MOVIE,
        name = name,
        portalName = "Main",
        year = year,
        rating = rating,
        progress = progress,
    )

    // ---- the list query ----

    @Test
    fun `search applies from two characters, trimmed`() {
        assertNull(listQuery(category = "", search = " a ", sort = null).q)
        assertEquals("ab", listQuery(category = "", search = " ab ", sort = null).q)
    }

    @Test
    fun `All is no category`() {
        assertNull(listQuery(category = ALL_ID, search = "", sort = null).category)
        assertEquals("drama", listQuery(category = "drama", search = "", sort = null).category)
    }

    @Test
    fun `browsing highlights Recently added, searching highlights no sort until one is chosen`() {
        assertEquals(OnDemandSort.ADDED, listQuery("", "", null).shownSort)
        assertNull(listQuery("", "heat", null).shownSort)
        assertEquals(OnDemandSort.YEAR, listQuery("", "heat", OnDemandSort.YEAR).shownSort)
    }

    @Test
    fun `the search hint names the ranking and the category`() {
        assertNull(searchHint(listQuery("", "", null), "All"))
        assertEquals("Best match first · in Drama", searchHint(listQuery("drama", "heat", null), "Drama"))
        assertEquals("A–Z · in All", searchHint(listQuery("", "heat", OnDemandSort.NAME), "All"))
    }

    @Test
    fun `an empty list says why`() {
        assertEquals("No titles match “heat” in Drama", emptyListText(listQuery("drama", "heat", null), "Drama"))
        assertEquals("Nothing here yet", emptyListText(listQuery("drama", "", null), "Drama"))
    }

    // ---- paging ----

    @Test
    fun `more is fetched once focus is within 16 rows of the loaded end`() {
        assertFalse(shouldLoadMore(focusIndex = 43, loaded = 60, total = 200, loading = false))
        assertTrue(shouldLoadMore(focusIndex = 44, loaded = 60, total = 200, loading = false))
    }

    @Test
    fun `nothing more is fetched while loading, when complete or before the first page`() {
        assertFalse(shouldLoadMore(focusIndex = 59, loaded = 60, total = 200, loading = true))
        assertFalse(shouldLoadMore(focusIndex = 59, loaded = 60, total = 60, loading = false))
        assertFalse(shouldLoadMore(focusIndex = 0, loaded = 0, total = null, loading = false))
    }

    @Test
    fun `the list ends with a loading row, then the count`() {
        assertEquals("Loading more… (60 of 200)", footerText(loaded = 60, total = 200))
        assertEquals("200 titles", footerText(loaded = 200, total = 200))
        assertEquals("1 title", footerText(loaded = 1, total = 1))
    }

    @Test
    fun `rows are keyed by portal and id`() {
        assertEquals("p1/series:3", itemKey(movie("series:3")))
    }

    // ---- rows ----

    @Test
    fun `the facts line is year, rating and portal`() {
        assertEquals("1995 · ★ 8.3 · Main", factsLine(movie("1", year = 1995, rating = 8.3)))
        assertEquals("★ 7 · Main", factsLine(movie("1", rating = 7.0)))
        assertEquals("Main", factsLine(movie("1")))
    }

    @Test
    fun `a progress line shows only for an unwatched Resume point`() {
        assertEquals(0.25f, progressFraction(OnDemandProgress(positionSec = 1500, durationSec = 6000))!!, 0.001f)
        assertNull(progressFraction(OnDemandProgress(positionSec = 1500, durationSec = 6000, watched = true)))
        assertNull(progressFraction(OnDemandProgress(positionSec = 1500, durationSec = null)))
        assertNull(progressFraction(null))
    }

    @Test
    fun `Continue watching says the minutes left or the Episode up next`() {
        val heat = movie("1", progress = OnDemandProgress(positionSec = 1200, durationSec = 6000))
        assertEquals("80 min left", continueSubtitle(heat))

        val nearlyDone = movie("1", progress = OnDemandProgress(positionSec = 5990, durationSec = 6000))
        assertEquals("1 min left", continueSubtitle(nearlyDone))

        val noDuration = movie("1", progress = OnDemandProgress(positionSec = 754, durationSec = null))
        assertEquals("12:34 in", continueSubtitle(noDuration))

        val dark = OnDemandItem(
            portal = "p1",
            id = "s",
            kind = OnDemandItem.SERIES,
            name = "Dark",
            upNext = OnDemandUpNext(seasonId = "2", seasonNumber = 2, episodeId = "4", episodeNumber = 4, name = "Lost"),
        )
        assertEquals("S2 · E4 · Lost · Up next", continueSubtitle(dark))
        assertEquals("S2 · E4 · Up next", continueSubtitle(dark.copy(upNext = dark.upNext!!.copy(name = null))))
    }

    // ---- categories pane ----

    @Test
    fun `Continue watching comes first, then All, then the categories`() {
        val entries = categoryEntries(
            categories = listOf(OnDemandCategory("drama", "Drama", 12)),
            continueCount = 3,
            allCount = 54,
        )
        assertEquals(listOf(CONTINUE_ID, ALL_ID, "drama"), entries.map { it.id })
        assertEquals(listOf("Continue watching", "All", "Drama"), entries.map { it.name })
        assertEquals(listOf(3, 54, 12), entries.map { it.count })
    }

    @Test
    fun `a Series row's line follows its Up next Episode's Resume point`() {
        val dark = OnDemandItem(
            portal = "p1",
            id = "s",
            kind = OnDemandItem.SERIES,
            upNext = OnDemandUpNext(seasonId = "1", episodeId = "2", positionSec = 300, durationSec = 3000),
        )
        assertEquals(0.1f, rowProgress(dark)!!, 0.001f)
        assertNull(rowProgress(dark.copy(upNext = dark.upNext!!.copy(positionSec = null))))
    }

    // ---- preview ----

    @Test
    fun `the preview facts are year, length or Seasons, age rating and stars`() {
        val heat = movie("1", year = 1995, rating = 8.3)
        assertEquals("1995 · ★ 8.3", detailFacts(heat, null))
        assertEquals(
            "1995 · 170 min · R · ★ 8.3",
            detailFacts(heat, OnDemandDetail(portal = "p1", id = "1", durationMin = 170, ageRating = "R")),
        )
        val dark = OnDemandDetail(
            portal = "p1",
            id = "s",
            kind = OnDemandItem.SERIES,
            seasons = listOf(OnDemandSeason("1"), OnDemandSeason("2")),
        )
        assertEquals("2 Seasons", detailFacts(movie("s").copy(kind = OnDemandItem.SERIES), dark))
        assertEquals("1 Season", detailFacts(movie("s"), dark.copy(seasons = dark.seasons.take(1))))
    }

    @Test
    fun `credits name the director, the first five of the cast and the country`() {
        val detail = OnDemandDetail(
            portal = "p1",
            id = "1",
            director = "Michael Mann",
            actors = "Al Pacino, Robert De Niro, Val Kilmer, Jon Voight, Tom Sizemore, Diane Venora, Amy Brenneman",
            country = "USA",
        )
        assertEquals(
            listOf(
                "Director" to "Michael Mann",
                "Cast" to "Al Pacino, Robert De Niro, Val Kilmer, Jon Voight, Tom Sizemore +2 more",
                "Country" to "USA",
            ),
            credits(detail),
        )
        assertEquals(emptyList<Pair<String, String>>(), credits(OnDemandDetail(portal = "p1", id = "1")))
    }

    // ---- load errors ----

    @Test
    fun `a load error reads the server's words, else the status, else unreachable`() {
        assertEquals(
            "The portal didn't answer. Try again in a moment.",
            loadErrorText(ApiException(502, ApiException.PORTAL_ERROR, "The portal didn't send this")),
        )
        assertEquals("Couldn't load On Demand (HTTP 500)", loadErrorText(ApiException(500)))
        assertEquals("Couldn't reach the server", loadErrorText(java.io.IOException("timeout")))
    }

    // ---- portal status pills ----

    @Test
    fun `a ready portal has no pill`() {
        assertNull(statusPill(OnDemandPortalStatus("p1", "Main", "ready"), nowEpochSec = 0))
    }

    @Test
    fun `pills say how each portal's index stands`() {
        val now = 1_000_000L
        assertEquals(
            "Main: Still indexing (42%) — newest first",
            statusPill(OnDemandPortalStatus("p1", "Main", "indexing", progress = 42), now),
        )
        assertEquals(
            "Main: Still indexing — newest first",
            statusPill(OnDemandPortalStatus("p1", "Main", "indexing"), now),
        )
        assertEquals(
            "Main: Not refreshed for 3 days",
            statusPill(OnDemandPortalStatus("p1", "Main", "stale", lastRefresh = now - 3 * 86_400 - 5), now),
        )
        assertEquals(
            "Main: Not refreshed for 5 hours",
            statusPill(OnDemandPortalStatus("p1", "Main", "stale", lastRefresh = now - 5 * 3_600), now),
        )
        assertEquals("Main: Partly indexed", statusPill(OnDemandPortalStatus("p1", "Main", "partial"), now))
        assertEquals(
            "Main: Couldn't load — showing nothing from it",
            statusPill(OnDemandPortalStatus("p1", "Main", "failed"), now),
        )
    }
}
