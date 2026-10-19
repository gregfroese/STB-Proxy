package cc.selfhosters.stbproxy.ui.guide

import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.epg.Programme
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.model.GuideHit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class GuideLogicTest {

    private fun channel(id: String, name: String = "Channel $id", epgId: String? = "epg$id") = Channel(
        portal = "p1",
        channelId = id,
        name = name,
        url = "/play/p1/$id",
        number = id,
        epgId = epgId,
        genre = "News",
    )

    private fun hit(id: String, title: String = "Show") = GuideHit(
        portal = "p1",
        channelId = id,
        channelName = "Channel $id",
        channelNumber = id,
        epgId = "epg$id",
        start = 1000,
        stop = 2000,
        title = title,
    )

    @Test
    fun `result count label shows first N of Y when more exist`() {
        assertEquals("Showing first 200 of 340", resultCountLabel(200, 340))
        assertEquals("3 results", resultCountLabel(3, 3))
        assertEquals("1 result", resultCountLabel(1, 1))
    }

    @Test
    fun `load more steps toward the maximum and clamps`() {
        assertEquals(400, nextGuideLimit(200))
        assertEquals(500, nextGuideLimit(400))
        assertEquals(500, nextGuideLimit(500))
    }

    @Test
    fun `hit channels are distinct and in first-seen order`() {
        val channels = listOf(channel("1"), channel("2"), channel("3"))
        val channelsInOrder = hitChannels(listOf(hit("2"), hit("1"), hit("2")), channels)
        assertEquals(listOf("2", "1"), channelsInOrder.map { it.channelId })
    }

    @Test
    fun `a hit whose channel is absent is dropped`() {
        assertEquals(emptyList<Channel>(), hitChannels(listOf(hit("9")), listOf(channel("1"))))
    }

    @Test
    fun `airing channels keeps only the currently-airing ones`() {
        val now = Instant.ofEpochSecond(1500)
        val epg = mapOf(
            "epg1" to NowNext(
                now = Programme("Now", Instant.ofEpochSecond(1000), Instant.ofEpochSecond(2000)),
            ),
            "epg2" to NowNext(
                now = Programme("Later", Instant.ofEpochSecond(3000), Instant.ofEpochSecond(4000)),
            ),
        )
        val airing = airingChannels(listOf(channel("1"), channel("2")), epg, now)
        assertEquals(listOf("1"), airing.map { it.channelId })
    }

    @Test
    fun `sub-filter matches name or number case-insensitively`() {
        val channels = listOf(channel("1", name = "BBC News"), channel("2", name = "ITV"))
        assertEquals(listOf("1"), filterGuideChannels(channels, "bbc").map { it.channelId })
        assertEquals(listOf("2"), filterGuideChannels(channels, "2").map { it.channelId })
        assertEquals(2, filterGuideChannels(channels, "").size)
    }

    @Test
    fun `notice names failed and partial portals`() {
        assertNull(guideNotice(emptyList(), emptyList()))
        assertEquals("Guide unavailable for A · Partial guide for B", guideNotice(listOf("A"), listOf("B")))
    }

    @Test
    fun `programme airing is a half-open window`() {
        assertEquals(true, programmeAiring(100, 200, 150))
        assertEquals(false, programmeAiring(100, 200, 200))
        assertEquals(false, programmeAiring(100, 200, 99))
    }
}
