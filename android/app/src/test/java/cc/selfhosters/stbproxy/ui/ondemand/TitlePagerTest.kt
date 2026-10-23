package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandPage
import cc.selfhosters.stbproxy.data.model.OnDemandProgress
import cc.selfhosters.stbproxy.data.network.ApiException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TitlePagerTest {

    private fun item(n: Int) = OnDemandItem(portal = "p1", id = n.toString(), name = "Title $n")

    /** A catalogue of [total] titles served [PAGE_SIZE] at a time, recording each offset asked for. */
    private class Catalogue(var total: Int) {
        val offsets = mutableListOf<Int>()
        var failNext: Exception? = null

        suspend fun fetch(offset: Int, limit: Int): OnDemandPage {
            offsets += offset
            failNext?.let { failNext = null; throw it }
            val end = minOf(total, offset + limit)
            return OnDemandPage(
                items = (offset until end).map { OnDemandItem(portal = "p1", id = it.toString(), name = "Title $it") },
                total = total,
            )
        }
    }

    @Test
    fun `the first page is fetched from offset 0`() = runBlocking {
        val catalogue = Catalogue(200)
        val pager = TitlePager(catalogue::fetch)
        pager.loadMore()

        assertEquals(listOf(0), catalogue.offsets)
        assertEquals(60, pager.state.value.items.size)
        assertEquals(200, pager.state.value.total)
    }

    @Test
    fun `focus near the end fetches the next page from the loaded count`() = runBlocking {
        val catalogue = Catalogue(200)
        val pager = TitlePager(catalogue::fetch)
        pager.loadMore()

        pager.onFocus(30)
        assertEquals(listOf(0), catalogue.offsets)

        pager.onFocus(44)
        assertEquals(listOf(0, 60), catalogue.offsets)
        assertEquals(120, pager.state.value.items.size)
    }

    @Test
    fun `the focused row keeps its index as pages arrive`() = runBlocking {
        val catalogue = Catalogue(200)
        val pager = TitlePager(catalogue::fetch)
        pager.loadMore()
        val focused = itemKey(pager.state.value.items[50])

        pager.onFocus(50)

        assertEquals(50, pager.indexOf(focused))
    }

    @Test
    fun `an unknown focus key falls back to the first row`() = runBlocking {
        val pager = TitlePager(Catalogue(10)::fetch)
        pager.loadMore()

        assertEquals(0, pager.indexOf("p1/nope"))
        assertEquals(0, pager.indexOf(null))
    }

    @Test
    fun `once everything is loaded nothing more is fetched`() = runBlocking {
        val catalogue = Catalogue(70)
        val pager = TitlePager(catalogue::fetch)
        pager.loadMore()
        pager.onFocus(69)
        pager.onFocus(69)
        pager.loadMore()

        assertEquals(listOf(0, 60), catalogue.offsets)
        assertTrue(pager.state.value.complete)
    }

    @Test
    fun `a title that shifted into the next page is not listed twice`() = runBlocking {
        val pages = ArrayDeque(
            listOf(
                OnDemandPage((0 until 60).map(::item), total = 120),
                // A new title arrived at the top, so the old 59th comes again.
                OnDemandPage((59 until 119).map(::item), total = 121),
            ),
        )
        val offsets = mutableListOf<Int>()
        val pager = TitlePager({ offset, _ ->
            offsets += offset
            pages.removeFirstOrNull() ?: OnDemandPage(total = 121)
        })
        pager.loadMore()
        pager.loadMore()

        val keys = pager.state.value.items.map(::itemKey)
        assertEquals(keys.distinct(), keys)
        assertEquals(119, keys.size)

        pager.loadMore()
        assertEquals("the next page carries on from the server's offset", listOf(0, 60, 120), offsets)
        assertEquals("119 titles", pager.state.value.footer)
    }

    @Test
    fun `an empty page ends the list even if the total said more`() = runBlocking {
        val catalogue = Catalogue(120)
        val pager = TitlePager(catalogue::fetch)
        pager.loadMore()
        catalogue.total = 60
        pager.loadMore()

        assertTrue(pager.state.value.complete)
        assertEquals(60, pager.state.value.total)
        assertEquals("60 titles", pager.state.value.footer)
        pager.loadMore()
        assertEquals(listOf(0, 60), catalogue.offsets)
    }

    @Test
    fun `a failure is kept, focus doesn't retry it, and retry does`() = runBlocking {
        val catalogue = Catalogue(200)
        val pager = TitlePager(catalogue::fetch)
        pager.loadMore()
        catalogue.failNext = ApiException(502, "portal_error")

        pager.onFocus(50)
        assertNotNull(pager.state.value.error)
        assertFalse(pager.state.value.loading)

        pager.onFocus(51)
        assertEquals(listOf(0, 60), catalogue.offsets)

        pager.retry()
        assertNull(pager.state.value.error)
        assertEquals(listOf(0, 60, 60), catalogue.offsets)
        assertEquals(120, pager.state.value.items.size)
    }

    @Test
    fun `a refreshed title replaces its row in place, and an unlisted one is ignored`() = runBlocking {
        val catalogue = Catalogue(200)
        val pager = TitlePager(catalogue::fetch)
        pager.loadMore()
        val watched = item(5).copy(progress = OnDemandProgress(watched = true))

        pager.replace(watched)
        assertEquals(watched, pager.state.value.items[5])
        assertEquals(60, pager.state.value.items.size)

        pager.replace(item(999))
        assertEquals(60, pager.state.value.items.size)
        assertEquals(listOf(0), catalogue.offsets)
    }
}
