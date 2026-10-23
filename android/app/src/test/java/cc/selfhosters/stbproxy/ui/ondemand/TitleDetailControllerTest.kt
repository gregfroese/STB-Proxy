package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.OnDemandAvailability
import cc.selfhosters.stbproxy.data.OnDemandChanges
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.network.ApiClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
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
import org.junit.Before
import org.junit.Test

/** The detail controller against a fake STB-Proxy: Play's inline errors and the Series' Up next. */
class TitleDetailControllerTest {

    private lateinit var server: MockWebServer

    /** Path → queued responses (the last one repeats). */
    private val routes = mutableMapOf<String, MutableList<MockResponse>>()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val queue = routes[request.path?.substringBefore('?')] ?: return MockResponse().setResponseCode(599)
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
}
