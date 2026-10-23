package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.ON_DEMAND_OFF_NOTICE
import cc.selfhosters.stbproxy.data.OnDemandAvailability
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

class OnDemandApiTest {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private lateinit var server: MockWebServer
    private val availability = OnDemandAvailability()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun api(): ApiClient = ApiClient(
        client = OkHttpClient(),
        json = json,
        baseUrlProvider = { server.url("/").toString().trimEnd('/') },
        retryDelaysMs = listOf(0L, 0L),
        onDemandAvailability = availability,
    )

    private fun respond(code: Int, body: String = "") {
        server.enqueue(MockResponse().setResponseCode(code).setBody(body))
    }

    private suspend fun failure(block: suspend () -> Unit): ApiException? = try {
        block()
        null
    } catch (e: ApiException) {
        e
    }

    // ---- reads ----

    @Test
    fun `categories decode with each portal's index status`() = runBlocking {
        respond(
            200,
            """{"categories": [{"id": "drama", "name": "Drama", "count": 12}],
               "portals": [{"portal": "p1", "name": "Main", "status": "indexing", "progress": 42,
                            "lastRefresh": null}]}""",
        )
        val result = api().fetchOnDemandCategories()

        assertEquals("/api/ondemand/categories", server.takeRequest().path)
        assertEquals("Drama", result.categories.single().name)
        assertEquals(12, result.categories.single().count)
        assertEquals("indexing", result.portals.single().status)
        assertEquals(42, result.portals.single().progress)
    }

    @Test
    fun `items sends only the query parts that are set`() = runBlocking {
        respond(200, """{"items": [], "total": 0, "offset": 60, "limit": 60}""")
        api().fetchOnDemandItems(category = "sci-fi & fantasy", q = "star wars", sort = null, offset = 60, limit = 60)

        val url = server.takeRequest().requestUrl!!
        assertEquals("/api/ondemand/items", url.encodedPath)
        assertEquals("sci-fi & fantasy", url.queryParameter("category"))
        assertEquals("star wars", url.queryParameter("q"))
        assertNull(url.queryParameter("sort"))
        assertEquals("60", url.queryParameter("offset"))
        assertEquals("60", url.queryParameter("limit"))
    }

    @Test
    fun `list items decode with progress, upNext and ids sent as numbers`() = runBlocking {
        respond(
            200,
            """{"total": 2, "items": [
                {"portal": "p1", "portalName": "Main", "id": 7, "kind": "movie", "name": "Heat",
                 "year": 1995, "rating": 8.3, "added": "2026-10-01 10:00:00",
                 "poster": "/api/ondemand/poster/p1/7",
                 "progress": {"positionSec": 1200, "durationSec": 6000, "watched": false, "updatedAt": 1}},
                {"portal": "p1", "portalName": "Main", "id": "series:3", "kind": "series", "name": "Dark",
                 "year": null, "rating": null, "poster": null,
                 "upNext": {"seasonId": 2, "seasonNumber": 2, "episodeId": "41", "episodeNumber": 4,
                            "name": null, "positionSec": null, "durationSec": null}}
            ]}""",
        )
        val page = api().fetchOnDemandItems(category = null, q = null, sort = "name", offset = 0, limit = 60)

        val (movie, series) = page.items
        assertEquals(2, page.total)
        assertEquals("7", movie.id)
        assertEquals(1200, movie.progress?.positionSec)
        assertEquals(false, movie.isSeries)
        assertEquals("series:3", series.id)
        assertEquals(true, series.isSeries)
        assertEquals("2", series.upNext?.seasonId)
        assertEquals(4, series.upNext?.episodeNumber)
    }

    @Test
    fun `item and season paths escape the ids`() = runBlocking {
        respond(200, """{"portal": "p1", "portalName": "Main", "id": "series:3", "kind": "series",
            "name": "Dark", "seasons": [{"id": 1, "number": 1, "name": "Season 1", "episodeCount": 10}]}""")
        respond(200, """[{"id": "9", "seasonId": "1", "number": 1, "name": null,
            "progress": {"positionSec": null, "durationSec": null, "watched": true, "updatedAt": 5}}]""")
        val detail = api().fetchOnDemandItem("p1", "series:3")
        val episodes = api().fetchOnDemandSeason("p1", "series:3", "1")

        assertEquals("/api/ondemand/item/p1/series:3", server.takeRequest().path)
        assertEquals("/api/ondemand/series/p1/series:3/season/1", server.takeRequest().path)
        assertEquals("1", detail.seasons.single().id)
        assertEquals(10, detail.seasons.single().episodeCount)
        assertEquals(true, episodes.single().progress?.watched)
    }

    @Test
    fun `continue watching unwraps its items`() = runBlocking {
        respond(200, """{"items": [{"portal": "p1", "id": "1", "kind": "movie", "name": "Heat"}]}""")
        val items = api().fetchOnDemandContinue()

        assertEquals("/api/ondemand/continue", server.takeRequest().path)
        assertEquals("Heat", items.single().name)
    }

    // ---- error mapping ----

    @Test
    fun `an error body's code and text ride on the exception`() = runBlocking {
        respond(404, """{"error": "That isn't in On Demand", "code": "not_found"}""")
        val e = failure { api().fetchOnDemandItem("p1", "1") }

        assertEquals(404, e?.code)
        assertEquals("not_found", e?.errorCode)
        assertEquals("That isn't in On Demand", e?.serverMessage)
    }

    @Test
    fun `a session_ended body carries its reason`() = runBlocking {
        respond(410, """{"error": "ended", "code": "session_ended", "reason": "evicted"}""")
        val e = failure { api().fetchOnDemandSeason("p1", "1", "1") }

        assertEquals("session_ended", e?.errorCode)
        assertEquals("evicted", e?.reason)
    }

    @Test
    fun `a body that is not an error object still gives the status`() = runBlocking {
        respond(404, "<html>nope</html>")
        val e = failure { api().fetchOnDemandItem("p1", "1") }

        assertEquals(404, e?.code)
        assertNull(e?.errorCode)
    }

    @Test
    fun `on_demand_off switches On Demand off with a notice`() = runBlocking {
        availability.onLineup(true)
        respond(404, """{"error": "On Demand isn't available on this login", "code": "on_demand_off"}""")
        val e = failure { api().fetchOnDemandCategories() }

        assertEquals(true, e?.isOnDemandOff)
        assertEquals(false, availability.enabled.value)
        assertEquals(ON_DEMAND_OFF_NOTICE, availability.notice.value)
    }

    @Test
    fun `the lineup's onDemand flag drives availability`() = runBlocking {
        respond(200, """{"account": "katie", "onDemand": true, "channels": []}""")
        api().fetchLineup()
        assertEquals(true, availability.enabled.value)

        respond(200, """{"account": "katie", "channels": []}""")
        api().fetchLineup()
        assertEquals(false, availability.enabled.value)
        assertNull("a lineup refresh removes it silently", availability.notice.value)
    }

    // ---- mutations ----

    @Test
    fun `play posts the Episode key with replaces and is never retried`() = runBlocking {
        respond(503, """{"error": "All tuners are busy", "code": "busy"}""")
        val e = failure {
            api().playOnDemand(OnDemandKey.Episode("p1", "series:3", "2", "41"), replaces = "old")
        }

        assertEquals("busy", e?.errorCode)
        assertEquals(1, server.requestCount)
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/ondemand/play", request.path)
        assertEquals(
            json.parseToJsonElement(
                """{"portal": "p1", "seriesId": "series:3", "seasonId": "2", "episodeId": "41", "replaces": "old"}""",
            ),
            json.parseToJsonElement(request.body.readUtf8()),
        )
    }

    @Test
    fun `play returns the session with an absolute url`() = runBlocking {
        respond(200, """{"session": "abc", "type": "hls", "url": "/api/ondemand/session/abc/master.m3u8",
            "durationSec": 5400}""")
        val playback = api().playOnDemand(OnDemandKey.Movie("p1", "7"))

        assertEquals(
            json.parseToJsonElement("""{"portal": "p1", "id": "7"}"""),
            json.parseToJsonElement(server.takeRequest().body.readUtf8()),
        )
        assertEquals("abc", playback.session)
        assertEquals(5400, playback.durationSec)
        assertEquals(server.url("/api/ondemand/session/abc/master.m3u8").toString(), playback.absoluteUrl)
    }

    @Test
    fun `progress reports and marks are PUT once`() = runBlocking {
        respond(204)
        respond(500)
        api().reportOnDemandProgress(OnDemandKey.Movie("p1", "7"), positionSec = 61, durationSec = null)
        val e = failure { api().markOnDemandWatched(OnDemandKey.Movie("p1", "7"), watched = true) }

        val report = server.takeRequest()
        assertEquals("PUT", report.method)
        assertEquals("/api/ondemand/progress", report.path)
        assertEquals(
            json.parseToJsonElement("""{"portal": "p1", "id": "7", "positionSec": 61, "durationSec": null}"""),
            json.parseToJsonElement(report.body.readUtf8()),
        )
        assertEquals(
            json.parseToJsonElement("""{"portal": "p1", "id": "7", "watched": true}"""),
            json.parseToJsonElement(server.takeRequest().body.readUtf8()),
        )
        assertEquals(500, e?.code)
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `ending a session sends DELETE`() = runBlocking {
        respond(204)
        api().endOnDemandSession("abc")

        val request = server.takeRequest()
        assertEquals("DELETE", request.method)
        assertEquals("/api/ondemand/session/abc", request.path)
    }
}
