package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.OnDemandAvailability
import cc.selfhosters.stbproxy.data.OnDemandChanges
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandPlayback
import cc.selfhosters.stbproxy.data.network.ApiClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
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
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.Collections

/**
 * The On Demand player's controller against a fake STB-Proxy and a fake Media3
 * player: the start seek, progress reports, the end card's hand-over, the 410
 * states and leaving.
 */
class OnDemandPlayerControllerTest {

    private lateinit var server: MockWebServer
    private val routes = mutableMapOf<String, MutableList<MockResponse>>()

    /** "METHOD path body" of every request, in order. */
    private val requests: MutableList<String> = Collections.synchronizedList(mutableListOf())

    private var now = 0L
    private val port = FakePort()
    private val changes = OnDemandChanges()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.path?.substringBefore('?').orEmpty()
                requests += "${request.method} $path ${request.body.readUtf8()}".trim()
                val queue = routes[path] ?: return MockResponse().setResponseCode(204)
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

    private fun session(sid: String, duration: Int = 3000) =
        200 to """{"session": "$sid", "type": "hls", "url": "/api/ondemand/session/$sid/master.m3u8", "durationSec": $duration}"""

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

    private val movie = OnDemandPlayStart(
        choice = PlayChoice(OnDemandKey.Movie("p1", "m1"), 754, "Heat"),
        playback = OnDemandPlayback("sid1", url = "/s/sid1/master.m3u8", durationSec = 6000, absoluteUrl = "http://x/s/sid1/master.m3u8"),
    )

    private val episode = OnDemandPlayStart(
        choice = PlayChoice(OnDemandKey.Episode("p1", "s1", "se2", "e23"), 0, "Dark", "S2 E3 · Ghosts"),
        playback = OnDemandPlayback("sid1", url = "/s/sid1/master.m3u8", durationSec = 3000, absoluteUrl = "http://x/s/sid1/master.m3u8"),
    )

    /** The Series s1: Season 2 has E3 and E4, Season 3 has E1. */
    private fun dark(e4Resume: Int? = null) {
        route(
            "/api/ondemand/item/p1/s1",
            200 to """{"portal": "p1", "id": "s1", "kind": "series", "name": "Dark", "description": "Time travel.",
                       "seasons": [{"id": "se2", "number": 2}, {"id": "se3", "number": 3}]}""",
        )
        val e4Progress = e4Resume?.let { """, "progress": {"positionSec": $it, "durationSec": 3000, "watched": false}""" }.orEmpty()
        route(
            "/api/ondemand/series/p1/s1/season/se2",
            200 to """[{"id": "e23", "seasonId": "se2", "number": 3, "name": "Ghosts"},
                       {"id": "e24", "seasonId": "se2", "number": 4, "name": "Lost"$e4Progress}]""",
        )
        route(
            "/api/ondemand/series/p1/s1/season/se3",
            200 to """[{"id": "e31", "seasonId": "se3", "number": 1, "name": "Deja vu"}]""",
        )
    }

    private fun test(start: OnDemandPlayStart, block: suspend CoroutineScope.(OnDemandPlayerController) -> Unit) = runBlocking {
        val scope = CoroutineScope(coroutineContext + Job())
        try {
            withTimeout(5_000) {
                val controller = OnDemandPlayerController(
                    start = start,
                    api = api(),
                    port = port,
                    scope = scope,
                    background = scope,
                    changes = changes,
                    clock = { now },
                    onUnauthorized = {},
                )
                controller.begin()
                block(controller)
            }
        } finally {
            scope.cancel()
        }
    }

    /** Waits for a request starting with [prefix] (e.g. "POST /api/ondemand/play") and returns it. */
    private suspend fun awaitRequest(prefix: String, nth: Int = 1): String {
        while (true) {
            val matching = synchronized(requests) { requests.filter { it.startsWith(prefix) } }
            if (matching.size >= nth) return matching[nth - 1]
            delay(5)
        }
    }

    private fun count(prefix: String) = synchronized(requests) { requests.count { it.startsWith(prefix) } }

    private suspend fun settle() = delay(150)

    private val progress = "PUT /api/ondemand/progress"
    private val play = "POST /api/ondemand/play"

    // ---- start ----

    @Test
    fun `it plays the session Play minted, from the chosen start position`() = test(movie) {
        assertEquals(listOf("http://x/s/sid1/master.m3u8" to 754_000L), port.loads)
        assertEquals(0, count(play))
    }

    // ---- progress reports ----

    @Test
    fun `it reports every 30 s of playback`() = test(movie) { controller ->
        port.playing = true
        port.positionMs = 800_000
        controller.tick()
        now = 29_000
        controller.tick()
        settle()
        assertEquals(0, count(progress))
        now = 30_000
        port.positionMs = 830_000
        controller.tick()
        assertEquals(
            """$progress {"portal":"p1","id":"m1","positionSec":830,"durationSec":6000}""",
            awaitRequest(progress),
        )
    }

    @Test
    fun `pausing reports, and the same position isn't sent twice`() = test(movie) { controller ->
        port.playing = true
        port.positionMs = 900_500
        controller.togglePause()
        assertEquals(false, port.playWhenReady)
        assertTrue(awaitRequest(progress).contains("\"positionSec\":900"))
        controller.onStop()
        settle()
        assertEquals(1, count(progress))
    }

    @Test
    fun `leaving reports, then ends the session, then announces the title's change`() = test(movie) { controller ->
        val announced = async { changes.changes.first() }
        port.positionMs = 1_000_000
        controller.close()
        assertEquals("p1/m1", announced.await())
        val order = synchronized(requests) { requests.filterNot { it.startsWith("GET") } }
        assertTrue(order[0].startsWith("$progress {\"portal\":\"p1\",\"id\":\"m1\",\"positionSec\":1000"))
        assertEquals("DELETE /api/ondemand/session/sid1", order[1])
    }

    // ---- end card ----

    @Test
    fun `a Movie's end reports the end and shows the Watched card, which leaves after 15 s`() = test(movie) { controller ->
        port.positionMs = 6_000_000
        controller.onEnded()
        assertTrue(awaitRequest(progress).contains("\"positionSec\":6000"))
        assertEquals(EndCard.Watched, controller.state.value.endCard)
        assertEquals(15, controller.state.value.endSecondsLeft)
        now = 15_000
        controller.tick()
        assertTrue(controller.state.value.finished)
    }

    @Test
    fun `an Episode's end card plays the next one after 15 s, handing the session over`() = test(episode) { controller ->
        dark(e4Resume = 120)
        controller.state.first { it.next != null }
        port.positionMs = 3_000_000
        controller.onEnded()
        assertEquals(EndCard.Next, controller.state.value.endCard)
        assertEquals("S2 E4 · Lost", controller.state.value.next?.subtitle)

        route(play.removePrefix("POST "), session("sid2"))
        now = 15_000
        controller.tick()
        assertEquals(
            """$play {"portal":"p1","seriesId":"s1","seasonId":"se2","episodeId":"e24","replaces":"sid1"}""",
            awaitRequest(play),
        )
        val playing = controller.state.first { it.session == "sid2" }
        assertEquals(OnDemandKey.Episode("p1", "s1", "se2", "e24"), playing.choice.key)
        assertNull(playing.endCard)
        assertEquals("the next Episode starts at its own Resume point", 120_000L, port.loads.last().second)
        assertTrue(port.loads.last().first.endsWith("/api/ondemand/session/sid2/master.m3u8"))
    }

    @Test
    fun `the last Episode of a Season hands over to the next Season's first`() = test(episode.copy(
        choice = episode.choice.copy(key = OnDemandKey.Episode("p1", "s1", "se2", "e24")),
    )) { controller ->
        dark()
        val next = controller.state.first { it.next != null }.next
        assertEquals(OnDemandKey.Episode("p1", "s1", "se3", "e31"), next?.key)
    }

    @Test
    fun `the Series' last Episode ends on the Watched card`() = test(episode.copy(
        choice = episode.choice.copy(key = OnDemandKey.Episode("p1", "s1", "se3", "e31")),
    )) { controller ->
        dark()
        controller.state.first { it.seasonNumber != null }
        settle()
        assertNull(controller.state.value.next)
        controller.onEnded()
        assertEquals(EndCard.Watched, controller.state.value.endCard)
    }

    @Test
    fun `Next Episode in the controls reports and hands over at once`() = test(episode) { controller ->
        dark()
        controller.state.first { it.next != null }
        route(play.removePrefix("POST "), session("sid2"))
        port.positionMs = 1_234_000
        controller.nextEpisode()
        assertTrue(awaitRequest(progress).contains("\"episodeId\":\"e23\",\"positionSec\":1234"))
        assertTrue(awaitRequest(play).contains("\"replaces\":\"sid1\""))
        assertTrue("the old session's player stops first", port.stops >= 1)
    }

    @Test
    fun `Play again on the end card seeks to the start in the same session`() = test(movie) { controller ->
        controller.onEnded()
        controller.playAgain()
        assertNull(controller.state.value.endCard)
        assertEquals(0L, port.positionMs)
        assertEquals(true, port.playWhenReady)
        assertEquals(0, count(play))
    }

    @Test
    fun `seeking back from the end card dismisses it and plays from there`() = test(movie) { controller ->
        port.positionMs = 6_000_000
        controller.onEnded()
        controller.seekBy(-10)
        assertNull(controller.state.value.endCard)
        assertEquals(5_990_000L, port.positionMs)
        assertEquals(true, port.playWhenReady)
    }

    // ---- session states ----

    @Test
    fun `a 410 idle restarts silently with replaces, at the same position`() = test(movie) { controller ->
        route(play.removePrefix("POST "), session("sid2"))
        port.positionMs = 2_000_000
        controller.onPlaybackFailed(410, """{"code": "session_ended", "reason": "idle"}""".toByteArray())
        assertTrue(awaitRequest(play).endsWith(""""id":"m1","replaces":"sid1"}"""))
        controller.state.first { it.session == "sid2" }
        assertNull(controller.state.value.overlay)
        assertEquals(2_000_000L, port.loads.last().second)
    }

    @Test
    fun `an idle restart while paused stays paused`() = test(movie) { controller ->
        route(play.removePrefix("POST "), session("sid2"))
        controller.togglePause()
        controller.onPlaybackFailed(410, """{"code": "session_ended", "reason": "idle"}""".toByteArray())
        controller.state.first { it.session == "sid2" }
        assertEquals(false, port.playWhenReady)
    }

    @Test
    fun `a 503 on the idle restart shows the toast and the busy overlay, and Try again mints fresh`() = test(movie) { controller ->
        route(play.removePrefix("POST "), 503 to """{"error": "All tuners are busy", "code": "busy"}""", session("sid3"))
        port.positionMs = 2_000_000
        controller.onPlaybackFailed(410, """{"code": "session_ended", "reason": "idle"}""".toByteArray())
        val busy = controller.state.first { it.overlay != null }
        assertEquals("Couldn't restart — someone else on this login is watching.", busy.toast)
        assertEquals(ON_DEMAND_ERROR_TEXT.getValue("busy"), busy.overlay?.message)
        assertEquals("Try again", busy.overlay?.action)
        assertTrue(awaitRequest(progress).contains("\"positionSec\":2000"))

        controller.resume()
        assertEquals("""$play {"portal":"p1","id":"m1"}""", awaitRequest(play, nth = 2))
        controller.state.first { it.session == "sid3" }
        assertEquals(2_000_000L, port.loads.last().second)
    }

    @Test
    fun `a 410 evicted shows the overlay with Resume, which mints a fresh session`() = test(movie) { controller ->
        port.positionMs = 2_345_000
        controller.onPlaybackFailed(410, """{"code": "session_ended", "reason": "evicted"}""".toByteArray())
        val overlay = controller.state.value.overlay
        assertEquals(
            "Playback stopped — someone started watching on another device with this login, " +
                "and the provider only allows one stream at a time",
            overlay?.message,
        )
        assertEquals("▶ Resume from 39:05", overlay?.action)
        assertNull(controller.state.value.session)
        assertTrue(awaitRequest(progress).contains("\"positionSec\":2345"))

        route(play.removePrefix("POST "), session("sid2"))
        controller.resume()
        assertEquals("""$play {"portal":"p1","id":"m1"}""", awaitRequest(play))
        controller.state.first { it.session == "sid2" && it.overlay == null }
        assertEquals(2_345_000L, port.loads.last().second)
    }

    @Test
    fun `a 410 stopped says it was stopped from the Streams page`() = test(movie) { controller ->
        controller.onPlaybackFailed(410, """{"code": "session_ended", "reason": "stopped"}""".toByteArray())
        assertEquals("The stream was stopped from the server's Streams page.", controller.state.value.overlay?.message)
    }

    @Test
    fun `leaving after the session ended doesn't end it again`() = test(movie) { controller ->
        port.positionMs = 100_000
        controller.onPlaybackFailed(410, """{"code": "session_ended", "reason": "evicted"}""".toByteArray())
        awaitRequest(progress)
        val announced = async { changes.changes.first() }
        controller.close()
        announced.await()
        settle()
        assertEquals(0, count("DELETE"))
        assertEquals(1, count(progress))
    }
}

/** A Media3 stand-in: what was loaded, and a position the test sets. */
private class FakePort : PlaybackPort {
    val loads = mutableListOf<Pair<String, Long>>()
    var stops = 0
    var playing = false
    override var positionMs = 0L
    override val durationMs: Long? = null
    override val isPlaying: Boolean get() = playing
    override var playWhenReady = false

    override fun load(url: String, startMs: Long) {
        loads += url to startMs
        positionMs = startMs
        playWhenReady = true
    }

    override fun seekTo(ms: Long) {
        positionMs = ms
    }

    override fun play() {
        playWhenReady = true
    }

    override fun pause() {
        playWhenReady = false
        playing = false
    }

    override fun stop() {
        stops++
    }
}
