package cc.selfhosters.stbproxy.data.network

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.Credentials
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ApiClientRetryTest {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private val lineupBody = """
        {
          "account": "katie",
          "blocks": ["News"],
          "channels": [
            {"portal": "1", "portalName": "A", "channelId": "1", "name": "BBC One",
             "number": "101", "logo": null, "genre": null, "epgId": "1.1",
             "blocks": ["News"], "url": "/play/1/1"}
          ],
          "failedPortals": []
        }
    """.trimIndent()

    private fun apiClientFor(
        server: MockWebServer,
        client: OkHttpClient = OkHttpClient(),
    ): ApiClient = ApiClient(
        client = client,
        json = json,
        baseUrlProvider = { server.url("/").toString().trimEnd('/') },
        retryDelaysMs = listOf(0L, 0L),
    )

    @Test
    fun `two retries are attempted before the failure is surfaced`() = runBlocking {
        val server = MockWebServer()
        repeat(3) { server.enqueue(MockResponse().setResponseCode(500)) }
        server.start()
        try {
            var thrown: Exception? = null
            try {
                apiClientFor(server).fetchLineup()
            } catch (e: Exception) {
                thrown = e
            }
            assertNotNull(thrown)
            assertEquals(3, server.requestCount)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `a transient failure is retried and then succeeds`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(500))
        server.enqueue(MockResponse().setResponseCode(200).setBody(lineupBody))
        server.start()
        try {
            val lineup = apiClientFor(server).fetchLineup()
            assertEquals("katie", lineup.account)
            assertEquals("BBC One", lineup.channels.single().name)
            assertEquals(2, server.requestCount)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `basic auth is attached to the lineup request`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody(lineupBody))
        server.start()
        try {
            val client = OkHttpClient.Builder()
                .addInterceptor(BasicAuthInterceptor { "katie" to "s3cret" })
                .build()
            apiClientFor(server, client).fetchLineup()

            val recorded = server.takeRequest()
            assertEquals("/api/lineup", recorded.path)
            assertEquals(Credentials.basic("katie", "s3cret"), recorded.getHeader("Authorization"))
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `a malformed body is not retried`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody("not json"))
        server.start()
        try {
            var thrown: Exception? = null
            try {
                apiClientFor(server).fetchLineup()
            } catch (e: Exception) {
                thrown = e
            }
            assertTrue(thrown != null)
            assertEquals(1, server.requestCount)
        } finally {
            server.shutdown()
        }
    }
}
