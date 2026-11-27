package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.model.CompanionRelease
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/** `GET /api/companion` and the APK download, against a fake server. */
class CompanionApiTest {

    @get:Rule
    val temp = TemporaryFolder()

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private lateinit var server: MockWebServer

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
        client = OkHttpClient.Builder()
            .addInterceptor(BasicAuthInterceptor { "alice" to "secret" })
            .build(),
        json = json,
        baseUrlProvider = { server.url("/").toString().trimEnd('/') },
        retryDelaysMs = listOf(0L, 0L),
    )

    private fun respond(code: Int, body: String = "") {
        server.enqueue(MockResponse().setResponseCode(code).setBody(body))
    }

    @Test
    fun `the release decodes, with the login sent`() = runBlocking {
        respond(200, """{"versionName": "1.14.0", "url": "/companion.apk", "sizeBytes": 12345678, "extra": 1}""")

        val release = api().fetchCompanion()

        val request = server.takeRequest()
        assertEquals("/api/companion", request.path)
        assertTrue(request.getHeader("Authorization").orEmpty().startsWith("Basic "))
        assertEquals(CompanionRelease("1.14.0", "/companion.apk", 12345678), release)
    }

    @Test
    fun `sizeBytes is optional`() = runBlocking {
        respond(200, """{"versionName": "1.14.0", "url": "/companion.apk"}""")
        assertNull(api().fetchCompanion()?.sizeBytes)
    }

    @Test
    fun `a 404 means the server has no APK`() = runBlocking {
        respond(404, """{"code": "not_found", "message": "No companion APK"}""")
        assertNull(api().fetchCompanion())
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `a server error is retried, then surfaces`() = runBlocking {
        repeat(3) { respond(500) }
        try {
            api().fetchCompanion()
            fail("expected an ApiException")
        } catch (e: ApiException) {
            assertEquals(500, e.code)
        }
        assertEquals(3, server.requestCount)
    }

    @Test
    fun `the APK downloads from the relative url with progress`() = runBlocking {
        val bytes = ByteArray(200_000) { (it % 251).toByte() }
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/vnd.android.package-archive")
                .setBody(Buffer().write(bytes)),
        )
        val target = temp.newFile("update.apk")
        val progress = mutableListOf<Pair<Long, Long?>>()

        api().downloadCompanion(CompanionRelease("1.14.0", "/companion.apk"), target) { read, total ->
            progress += read to total
        }

        val request = server.takeRequest()
        assertEquals("/companion.apk", request.path)
        assertTrue(request.getHeader("Authorization").orEmpty().startsWith("Basic "))
        assertArrayEquals(bytes, target.readBytes())
        assertEquals(0L to 200_000L, progress.first())
        assertEquals(200_000L to 200_000L, progress.last())
    }

    @Test
    fun `a failed download surfaces as an ApiException`() = runBlocking {
        respond(404, """{"code": "not_found", "message": "No companion APK"}""")
        try {
            api().downloadCompanion(CompanionRelease("1.14.0", "/companion.apk"), temp.newFile("update.apk"))
            fail("expected an ApiException")
        } catch (e: ApiException) {
            assertEquals(404, e.code)
            assertEquals("not_found", e.errorCode)
        }
    }
}
