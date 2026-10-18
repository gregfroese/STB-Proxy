package cc.selfhosters.stbproxy.ui.picker

import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.data.model.Channel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PickerLogicTest {

    private fun channel(
        id: String,
        name: String,
        number: String? = null,
        blocks: List<String> = emptyList(),
    ) = Channel(
        portal = "1",
        channelId = id,
        name = name,
        url = "/play/1/$id",
        number = number,
        blocks = blocks,
    )

    private val kids = channel("1", "Cartoon Network", "301", listOf("Kids"))
    private val news = channel("2", "BBC News", "501", listOf("News"))
    private val multi = channel("3", "TNT Sports", "203", listOf("Sports", "Entertainment"))
    private val ungrouped = channel("4", "Community TV", "701", emptyList())

    private val channels = listOf(kids, news, multi, ungrouped)

    @Test
    fun `rail follows blocks order and appends Other last`() {
        val blocks = listOf("Entertainment", "Kids", "News", "Sports")
        val rail = blockRail(blocks, channels)

        assertEquals(
            listOf("Entertainment", "Kids", "News", "Sports", OTHER_BLOCK),
            rail.map { it.name },
        )
        assertEquals(1, rail.first { it.name == "Entertainment" }.count)
        assertEquals(1, rail.first { it.name == "Kids" }.count)
        assertEquals(1, rail.first { it.name == "News" }.count)
        assertEquals(1, rail.first { it.name == "Sports" }.count)
        assertEquals(1, rail.first { it.name == OTHER_BLOCK }.count)
    }

    @Test
    fun `Other is omitted when every channel is grouped`() {
        val rail = blockRail(listOf("Kids", "News", "Sports"), listOf(kids, news, multi))
        assertTrue(rail.none { it.name == OTHER_BLOCK })
        assertEquals(listOf("Kids", "News", "Sports"), rail.map { it.name })
    }

    @Test
    fun `channelsInBlock resolves named blocks and Other`() {
        assertEquals(listOf(multi), channelsInBlock(channels, "Sports"))
        assertEquals(listOf(ungrouped), channelsInBlock(channels, OTHER_BLOCK))
    }

    @Test
    fun `search matches name and number across all blocks, case-insensitively`() {
        assertEquals(listOf(news), searchChannels(channels, "bbc"))
        assertEquals(listOf(ungrouped), searchChannels(channels, "701"))
        assertEquals(channels, searchChannels(channels, "  "))
        assertTrue(searchChannels(channels, "zzz").isEmpty())
    }

    @Test
    fun `block match counts are per-block and span every block`() {
        val blocks = listOf("Entertainment", "Kids", "News", "Sports", OTHER_BLOCK)
        val counts = blockMatchCounts(channels, blocks, "t")

        // "t": Cartoon Network (Kids), TNT Sports (Sports + Entertainment), Community TV (Other)
        assertEquals(1, counts["Entertainment"])
        assertEquals(1, counts["Kids"])
        assertEquals(0, counts["News"])
        assertEquals(1, counts["Sports"])
        assertEquals(1, counts[OTHER_BLOCK])
    }

    @Test
    fun `plus-N badge counts the channel's other blocks only`() {
        assertEquals(1, extraBlockCount(multi, "Sports", searching = false))
        assertEquals(0, extraBlockCount(kids, "Kids", searching = false))
        assertEquals(0, extraBlockCount(multi, "Sports", searching = true))
        assertEquals(0, extraBlockCount(ungrouped, OTHER_BLOCK, searching = false))
    }

    @Test
    fun `launch block prefers the active block else the channel's first`() {
        assertEquals("Sports", launchBlockFor(multi, "Sports"))
        assertEquals("Sports", launchBlockFor(multi, "Kids"))
        assertEquals("Sports", launchBlockFor(multi, null))
        assertEquals(OTHER_BLOCK, launchBlockFor(ungrouped, "Kids"))
        assertEquals(OTHER_BLOCK, launchBlockFor(ungrouped, OTHER_BLOCK))
    }

    // ---- genre grouping (spec follow-up) ----

    private fun genreChannel(id: String, name: String, genre: String?) =
        Channel(
            portal = "1",
            channelId = id,
            name = name,
            url = "/play/1/$id",
            genre = genre,
        )

    private val gNews = genreChannel("1", "BBC News", "News")
    private val gNews2 = genreChannel("2", "Sky News", "news")
    private val gSports = genreChannel("3", "TNT Sports", "Sports")
    private val gNone = genreChannel("4", "Community TV", null)
    private val genreChannels = listOf(gNews, gNews2, gSports, gNone)

    @Test
    fun `genre mode only replaces blocks when there are none`() {
        assertEquals(GroupMode.BLOCKS, effectiveGroupMode(GroupMode.BLOCKS, listOf("Kids")))
        assertEquals(GroupMode.GENRES, effectiveGroupMode(GroupMode.GENRES, listOf("Kids")))
        assertEquals(GroupMode.GENRES, effectiveGroupMode(GroupMode.BLOCKS, emptyList()))
    }

    @Test
    fun `genre rail merges same-named genres, sorts, and appends Other last`() {
        val rail = genreRail(genreChannels)
        assertEquals(listOf("News", "Sports", OTHER_BLOCK), rail.map { it.name })
        assertEquals(listOf(2, 1, 1), rail.map { it.count })
    }

    @Test
    fun `channelsInGroup resolves genres case-insensitively and Other`() {
        assertEquals(listOf("BBC News", "Sky News"), channelsInGroup(GroupMode.GENRES, genreChannels, "News").map { it.name })
        assertEquals(listOf("TNT Sports"), channelsInGroup(GroupMode.GENRES, genreChannels, "sports").map { it.name })
        assertEquals(listOf("Community TV"), channelsInGroup(GroupMode.GENRES, genreChannels, OTHER_BLOCK).map { it.name })
    }

    @Test
    fun `genre match counts are per-genre and the plus-N badge is zero`() {
        val counts = groupMatchCounts(GroupMode.GENRES, genreChannels, listOf("News", "Sports", OTHER_BLOCK), "sky")
        assertEquals(1, counts["News"])
        assertEquals(0, counts["Sports"])
        assertEquals(0, extraGroupCount(GroupMode.GENRES, gSports, "Sports", searching = false))
        assertEquals(1, extraGroupCount(GroupMode.BLOCKS, multi, "Sports", searching = false))
    }

    @Test
    fun `launch group is the channel's genre in genre mode`() {
        assertEquals("Sports", launchGroupFor(GroupMode.GENRES, gSports, "News"))
        assertEquals(OTHER_BLOCK, launchGroupFor(GroupMode.GENRES, gNone, null))
        assertEquals("Sports", launchGroupFor(GroupMode.BLOCKS, multi, "Kids"))
    }
}
