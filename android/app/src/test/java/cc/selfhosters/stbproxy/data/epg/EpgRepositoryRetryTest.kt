package cc.selfhosters.stbproxy.data.epg

import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.kxml2.io.KXmlParser
import java.time.Instant

class EpgRepositoryRetryTest {

    private val now = Instant.parse("2024-01-01T12:30:00Z")

    private val xmltvBody = """
        <?xml version="1.0" encoding="UTF-8"?>
        <tv>
          <programme start="20240101120000 +0000" stop="20240101130000 +0000" channel="p1.1">
            <title lang="en">News at Noon</title>
          </programme>
        </tv>
    """.trimIndent()

    private fun repositoryFor(server: MockWebServer): EpgRepository = EpgRepository(
        client = OkHttpClient(),
        baseUrlProvider = { server.url("/").toString().trimEnd('/') },
        parser = XmltvParser { KXmlParser() },
        clock = { now },
        retryDelaysMs = listOf(0L, 0L),
    )

    @Test
    fun `a transient 500 is retried and then succeeds`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(500))
        server.enqueue(MockResponse().setResponseCode(200).setBody(xmltvBody))
        server.start()
        try {
            val guide = repositoryFor(server).fetch()
            assertEquals("News at Noon", guide.getValue("p1.1").now?.title)
            assertEquals(2, server.requestCount)
            assertEquals("/xmltv", server.takeRequest().path)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `two retries are attempted before an empty map is returned`() = runBlocking {
        val server = MockWebServer()
        repeat(3) { server.enqueue(MockResponse().setResponseCode(500)) }
        server.start()
        try {
            assertTrue(repositoryFor(server).fetch().isEmpty())
            assertEquals(3, server.requestCount)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `a 401 is not retried`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(401))
        server.start()
        try {
            assertTrue(repositoryFor(server).fetch().isEmpty())
            assertEquals(1, server.requestCount)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `a malformed body is not retried`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody("not xml"))
        server.start()
        try {
            assertTrue(repositoryFor(server).fetch().isEmpty())
            assertEquals(1, server.requestCount)
        } finally {
            server.shutdown()
        }
    }
}
