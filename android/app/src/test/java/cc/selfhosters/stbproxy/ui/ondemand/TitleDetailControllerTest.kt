package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.OnDemandAvailability
import cc.selfhosters.stbproxy.data.OnDemandChanges
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.network.ApiClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** The detail controller against a fake STB-Proxy: Play's inline errors and the Series' Up next. */
class TitleDetailControllerTest {

    private lateinit var server: MockWebServer

    /** "METHOD path" or path → queued responses (the last one repeats). */
    private val routes = mutableMapOf<String, MutableList<MockResponse>>()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.path?.substringBefore('?')
                val queue = routes["${request.method} $path"] ?: routes[path] ?: return MockResponse().setResponseCode(599)
                return if (queue.size > 1) queue.removeAt(0) else queue.first()
            }
        }
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun route(path: String, vararg responses: Pair<Int, String>) {
        routes[path] = responses.map { (code, body) -> MockResponse().setResponseCode(code).setBody(body) }.toMutableList()
    }

    private fun api() = ApiClient(
        client = OkHttpClient(),
        json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
        },
        baseUrlProvider = { server.url("/").toString().trimEnd('/') },
        retryDelaysMs = listOf(0L, 0L),
        onDemandAvailability = OnDemandAvailability(),
    )

    private fun test(block: suspend CoroutineScope.(TitleDetailController) -> Unit) = runBlocking {
        val scope = CoroutineScope(coroutineContext + Job())
        try {
            withTimeout(5_000) { block(TitleDetailController(api(), scope, OnDemandChanges(), onUnauthorized = {})) }
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun `a busy Play shows the web's wording inline, and Try again starts the session`() = test { controller ->
        route("/api/ondemand/item/p1/m1", 200 to """{"portal": "p1", "id": "m1", "kind": "movie", "name": "Heat"}""")
        route(
            "/api/ondemand/play",
            503 to """{"error": "All tuners are busy", "code": "busy"}""",
            200 to """{"session": "sid1", "type": "hls", "url": "/api/ondemand/session/sid1/master.m3u8", "durationSec": 6000}""",
        )
        controller.load("p1", "m1")
        val loaded = controller.state.first { it.detail != null }

        controller.play(loaded.buttons?.primary?.choice)
        val failed = controller.state.first { it.actionError != null }
        assertEquals(ON_DEMAND_ERROR_TEXT.getValue("busy"), failed.actionError)
        assertFalse(failed.busy)

        controller.retry()
        val start = controller.playStarts.first()
        assertEquals(PlayChoice(OnDemandKey.Movie("p1", "m1"), 0, "Heat"), start.choice)
        assertEquals("sid1", start.playback.session)
        assertNull(controller.state.value.actionError)
    }

    @Test
    fun `a Series opens on its Up next Season and plays the Up next Episode`() = test { controller ->
        route(
            "/api/ondemand/item/p1/s1",
            200 to """{"portal": "p1", "id": "s1", "kind": "series", "name": "Dark",
                       "upNext": {"seasonId": "se2", "seasonNumber": 2, "episodeId": "e24", "episodeNumber": 4,
                                  "name": "Lost and Found", "positionSec": 600, "durationSec": 3000},
                       "seasons": [{"id": "se1", "number": 1}, {"id": "se2", "number": 2}]}""",
        )
        route(
            "/api/ondemand/series/p1/s1/season/se2",
            200 to """[{"id": "e23", "seasonId": "se2", "number": 3},
                       {"id": "e24", "seasonId": "se2", "number": 4, "name": "Lost and Found",
                        "progress": {"positionSec": 600, "durationSec": 3000, "watched": false}}]""",
        )
        controller.load("p1", "s1")
        val shown = controller.state.first { it.episodeRows != null }

        assertEquals("se2", shown.seasonId)
        assertEquals(listOf(false, true), shown.episodeRows?.map { it.upNext })
        assertEquals("▶ Resume S2 E4", shown.buttons?.primary?.label)
        assertEquals(
            listOf("/api/ondemand/item/p1/s1", "/api/ondemand/series/p1/s1/season/se2"),
            List(server.requestCount) { server.takeRequest().path },
        )
    }

    // ---- downloads ----

    private val heat = """{"portal": "p1", "id": "m1", "kind": "movie", "name": "Heat", "canDownload": true}"""

    private fun download(id: String, item: String, status: String, progress: Int = 0, mine: Boolean = true) =
        """{"id": "$id", "kind": "movie", "item": $item, "title": "t", "poster": "", "status": "$status",
            "progress": $progress, "error": null, "sizeBytes": null, "mine": $mine, "createdAt": 1.0, "finishedAt": null}"""

    private fun requests(): List<String> = List(server.requestCount) {
        server.takeRequest().let { "${it.method} ${it.path} ${it.body.readUtf8()}".trim() }
    }

    @Test
    fun `Download asks the server and shows the 202's status at once`() = test { controller ->
        route("/api/ondemand/item/p1/m1", 200 to heat)
        route(
            "POST /api/ondemand/downloads",
            202 to """{"items": [${download("d1", """{"portal": "p1", "id": "m1"}""", "queued")}]}""",
        )
        controller.load("p1", "m1")
        assertEquals(DownloadButton("Download", true), controller.state.first { it.detail != null }.movieDownload)

        controller.downloadMovie()
        val queued = controller.state.first { it.detail?.download != null && !it.downloadBusy }
        assertEquals(DownloadButton("Queued", false), queued.movieDownload)
        assertTrue(queued.canCancelMovieDownload)
        assertTrue(queued.hasActiveDownload)
        assertEquals(
            listOf("GET /api/ondemand/item/p1/m1", """POST /api/ondemand/downloads {"portal":"p1","id":"m1"}"""),
            requests(),
        )
    }

    @Test
    fun `a refused Download shows the server's text inline`() = test { controller ->
        route("/api/ondemand/item/p1/m1", 200 to heat)
        route(
            "POST /api/ondemand/downloads",
            403 to """{"error": "Downloads are off for this Account", "code": "downloads_off"}""",
        )
        controller.load("p1", "m1")
        controller.state.first { it.detail != null }

        controller.downloadMovie()
        val failed = controller.state.first { it.downloadError != null }
        assertEquals("Downloads are off for this Account", failed.downloadError)
        assertFalse(failed.downloadBusy)
        assertEquals(DownloadButton("Download", true), failed.movieDownload)
    }

    @Test
    fun `Download Season posts the shown Season and marks its Episodes`() = test { controller ->
        route(
            "/api/ondemand/item/p1/s1",
            200 to """{"portal": "p1", "id": "s1", "kind": "series", "name": "Dark", "canDownload": true,
                       "seasons": [{"id": "se1", "number": 1}]}""",
        )
        route(
            "/api/ondemand/series/p1/s1/season/se1",
            200 to """[{"id": "e1", "seasonId": "se1", "number": 1}, {"id": "e2", "seasonId": "se1", "number": 2}]""",
        )
        route(
            "POST /api/ondemand/downloads",
            202 to """{"items": [
                ${download("d1", """{"portal": "p1", "seriesId": "s1", "seasonId": "se1", "episodeId": "e1"}""", "downloading", 42)},
                ${download("d2", """{"portal": "p1", "seriesId": "s1", "seasonId": "se1", "episodeId": "e2"}""", "queued")}]}""",
        )
        controller.load("p1", "s1")
        val shown = controller.state.first { it.episodeRows != null }
        assertEquals(DownloadButton("Download Season 1", true), shown.seasonDownload)

        controller.downloadSeason()
        val marked = controller.state.first { s -> s.episodeRows?.all { it.download != null } == true }
        assertEquals(listOf("Downloading 42%", "Queued"), marked.episodeRows?.map { it.download })
        assertEquals(DownloadButton("Season queued (0 of 2 downloaded)", false), marked.seasonDownload)
        val asked = server.requestCount
        controller.downloadSeason() // nothing left to ask for
        assertEquals(asked, server.requestCount)
        assertEquals(
            """POST /api/ondemand/downloads {"portal":"p1","seriesId":"s1","seasonId":"se1"}""",
            requests().last(),
        )
    }

    @Test
    fun `Cancel download deletes it and clears the status`() = test { controller ->
        route(
            "/api/ondemand/item/p1/m1",
            200 to """{"portal": "p1", "id": "m1", "kind": "movie", "name": "Heat", "canDownload": true,
                       "download": {"id": "d1", "status": "downloading", "progress": 10, "mine": true}}""",
        )
        route("DELETE /api/ondemand/downloads/d1", 204 to "")
        controller.load("p1", "m1")
        controller.state.first { it.detail != null }

        controller.cancelMovieDownload()
        val cleared = controller.state.first { it.detail?.download == null }
        assertEquals(DownloadButton("Download", true), cleared.movieDownload)
        assertEquals("DELETE /api/ondemand/downloads/d1", requests().last())
    }

    @Test
    fun `while a download is active the detail looks again and follows the list`() = test { controller ->
        route(
            "/api/ondemand/item/p1/m1",
            200 to """{"portal": "p1", "id": "m1", "kind": "movie", "name": "Heat", "canDownload": true,
                       "download": {"id": "d1", "status": "queued", "progress": 0}}""",
        )
        route(
            "GET /api/ondemand/downloads",
            200 to """{"canDownload": true, "items": [${download("d1", """{"portal": "p1", "id": "m1"}""", "downloading", 5)}]}""",
            200 to """{"canDownload": true, "items": [${download("d1", """{"portal": "p1", "id": "m1"}""", "done", 100)}]}""",
        )
        controller.load("p1", "m1")
        controller.state.first { it.detail != null }

        val watcher = launch { controller.watchDownloads(intervalMs = 10) }
        assertEquals(DownloadButton("Downloading 5%", false), controller.state.first { it.detail?.download?.progress == 5 }.movieDownload)
        val done = controller.state.first { it.detail?.download?.status == "done" }
        assertEquals(DownloadButton("Downloaded", false), done.movieDownload)
        assertFalse(done.hasActiveDownload)

        // Nothing active: no more looking.
        val seen = server.requestCount
        kotlinx.coroutines.delay(60)
        assertEquals(seen, server.requestCount)
        watcher.cancel()
    }
}
