package cc.selfhosters.stbproxy.ui.player

import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.epg.Programme
import cc.selfhosters.stbproxy.data.model.Channel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class PlayerLogicTest {

    // ---- error classification (spec 2.6) ----

    @Test
    fun `503 is all-tuners-busy`() {
        val error = classifySourceError(SourceErrorInfo(isHttpResponse = true, responseCode = 503))
        assertEquals(PlaybackError.AllTunersBusy, error)
    }

    @Test
    fun `302 is a redirect carrying its target`() {
        val error = classifySourceError(
            SourceErrorInfo(isHttpResponse = true, responseCode = 302, location = "http://portal/stream.m3u8"),
        )
        assertEquals(PlaybackError.RedirectingToPortal("http://portal/stream.m3u8"), error)
    }

    @Test
    fun `every 3xx redirect status maps to a redirect`() {
        listOf(301, 302, 303, 307, 308).forEach { code ->
            assertEquals(
                PlaybackError.RedirectingToPortal(null),
                classifySourceError(SourceErrorInfo(isHttpResponse = true, responseCode = code)),
            )
        }
    }

    @Test
    fun `other http errors and plain network failures are unreachable`() {
        assertEquals(
            PlaybackError.Unreachable,
            classifySourceError(SourceErrorInfo(isHttpResponse = true, responseCode = 404)),
        )
        assertEquals(
            PlaybackError.Unreachable,
            classifySourceError(SourceErrorInfo(isHttpResponse = true, responseCode = 500)),
        )
        assertEquals(
            PlaybackError.Unreachable,
            classifySourceError(SourceErrorInfo(isHttpResponse = true, responseCode = 200)),
        )
        assertEquals(PlaybackError.Unreachable, classifySourceError(SourceErrorInfo()))
    }

    // ---- EPG refresh decision (spec 2.6) ----

    private val t0: Instant = Instant.parse("2024-01-01T12:00:00Z")

    @Test
    fun `minute boundary is crossed only when the wall-clock minute changes`() {
        assertTrue(minuteBoundaryPassed(t0.plusSeconds(60), t0))
        assertTrue(!minuteBoundaryPassed(t0.plusSeconds(1), t0))
        assertTrue(!minuteBoundaryPassed(t0.plusSeconds(30), t0))
        assertTrue(!minuteBoundaryPassed(t0, t0))
    }

    @Test
    fun `programme boundary passes at or after stop, not before, tolerating null`() {
        val stop = t0.plusSeconds(1800)
        assertTrue(programmeBoundaryPassed(stop, stop))
        assertTrue(programmeBoundaryPassed(stop.plusSeconds(1), stop))
        assertTrue(!programmeBoundaryPassed(stop.minusSeconds(1), stop))
        assertTrue(!programmeBoundaryPassed(t0, null))
    }

    @Test
    fun `foreground forces a refetch`() {
        assertEquals(
            EpgRefreshAction.REFETCH,
            epgRefreshAction(t0, t0, currentStop = t0.plusSeconds(600), foregrounded = true),
        )
    }

    @Test
    fun `a programme boundary forces a refetch even mid-minute`() {
        val stop = t0.plusSeconds(30)
        assertEquals(
            EpgRefreshAction.REFETCH,
            epgRefreshAction(stop, t0, currentStop = stop),
        )
    }

    @Test
    fun `a new minute recomputes, otherwise nothing`() {
        assertEquals(
            EpgRefreshAction.RECOMPUTE,
            epgRefreshAction(t0.plusSeconds(61), t0, currentStop = t0.plusSeconds(600)),
        )
        assertEquals(
            EpgRefreshAction.NONE,
            epgRefreshAction(t0.plusSeconds(30), t0, currentStop = t0.plusSeconds(600)),
        )
    }

    // ---- now/next resolution (spec 2.6) ----

    private fun programme(title: String, start: Instant, stop: Instant?) =
        Programme(title = title, start = start, stop = stop)

    @Test
    fun `a still-airing now is kept`() {
        val now = t0.plusSeconds(300)
        val stored = NowNext(
            now = programme("A", t0, t0.plusSeconds(600)),
            next = programme("B", t0.plusSeconds(600), t0.plusSeconds(1200)),
        )
        val resolved = resolveNowNext(stored, now)!!
        assertEquals("A", resolved.now?.title)
        assertEquals("B", resolved.next?.title)
    }

    @Test
    fun `a null-stop now never expires`() {
        val stored = NowNext(now = programme("Open", t0, null))
        val resolved = resolveNowNext(stored, t0.plusSeconds(99999))!!
        assertEquals("Open", resolved.now?.title)
    }

    @Test
    fun `an ended now promotes a started next`() {
        val stored = NowNext(
            now = programme("A", t0, t0.plusSeconds(600)),
            next = programme("B", t0.plusSeconds(600), t0.plusSeconds(1200)),
        )
        val resolved = resolveNowNext(stored, t0.plusSeconds(700))!!
        assertEquals("B", resolved.now?.title)
        assertNull(resolved.next)
    }

    @Test
    fun `an ended now with an unstarted next leaves a gap`() {
        val stored = NowNext(
            now = programme("A", t0, t0.plusSeconds(600)),
            next = programme("B", t0.plusSeconds(900), t0.plusSeconds(1200)),
        )
        val resolved = resolveNowNext(stored, t0.plusSeconds(700))!!
        assertNull(resolved.now)
        assertEquals("B", resolved.next?.title)
    }

    @Test
    fun `no stored entry resolves to null`() {
        assertNull(resolveNowNext(null, t0))
    }

    // ---- progress ----

    @Test
    fun `progress is the elapsed fraction, clamped`() {
        val p = programme("A", t0, t0.plusSeconds(600))
        assertEquals(0.5f, programmeProgress(p, t0.plusSeconds(300)), 0.0001f)
        assertEquals(0f, programmeProgress(p, t0.minusSeconds(60)), 0.0001f)
        assertEquals(1f, programmeProgress(p, t0.plusSeconds(900)), 0.0001f)
        assertEquals(0f, programmeProgress(programme("A", t0, null), t0.plusSeconds(300)), 0.0001f)
        assertEquals(0f, programmeProgress(null, t0), 0.0001f)
    }

    // ---- channel up/down within the launch Block (spec 2.6) ----

    private fun channel(id: String, name: String, blocks: List<String>) = Channel(
        portal = "1",
        channelId = id,
        name = name,
        url = "/play/1/$id",
        blocks = blocks,
    )

    private val news1 = channel("1", "BBC News", listOf("News"))
    private val news2 = channel("2", "Sky News", listOf("News"))
    private val news3 = channel("3", "CNN", listOf("News", "US"))
    private val kids = channel("4", "Cartoon Network", listOf("Kids"))
    private val channels = listOf(news1, news2, news3, kids)

    @Test
    fun `zap list is the launch block's channels`() {
        assertEquals(listOf(news1, news2, news3), zapList(channels, "News"))
        assertEquals(listOf(kids), zapList(channels, "Kids"))
    }

    @Test
    fun `a multi-block channel walks the launch block`() {
        // CNN is in News and US; launched from News it steps within News.
        assertEquals(news1, zapTarget(channels, "News", news3, delta = 1))
        assertEquals(news2, zapTarget(channels, "News", news3, delta = -1))
    }

    @Test
    fun `channel up and down wrap at both ends`() {
        assertEquals(news2, zapTarget(channels, "News", news1, delta = 1))
        assertEquals(news3, zapTarget(channels, "News", news1, delta = -1))
    }

    @Test
    fun `an empty block has no zap target`() {
        assertNull(zapTarget(channels, "Sports", news1, delta = 1))
        assertEquals(-1, zapIndex(0, 0, 1))
    }

    @Test
    fun `a channel outside the list steps from the first entry`() {
        assertEquals(news2, zapTarget(channels, "News", kids, delta = 1))
    }

    @Test
    fun `zap index wraps in both directions`() {
        assertEquals(0, zapIndex(3, 2, 1))
        assertEquals(2, zapIndex(3, 0, -1))
        assertEquals(1, zapIndex(3, 0, 1))
    }

    // ---- full-screen decision ----

    @Test
    fun `phone landscape starts full-screen`() {
        assertTrue(shouldAutoFullscreen(isTv = false, isLandscape = true))
    }

    @Test
    fun `phone portrait keeps the now-next sheet`() {
        assertTrue(!shouldAutoFullscreen(isTv = false, isLandscape = false))
    }

    @Test
    fun `TV is never auto-toggled`() {
        assertTrue(!shouldAutoFullscreen(isTv = true, isLandscape = true))
        assertTrue(!shouldAutoFullscreen(isTv = true, isLandscape = false))
    }
}
