package cc.selfhosters.stbproxy.data.network

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.Credentials
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.TimeUnit

class ConnectionProbeTest {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private val channelsBody = """
        {
          "account": "katie",
          "blocks": ["News"],
          "channels": [
            {"portal": "1", "channelId": "1", "name": "BBC One", "url": "/play/1/1",
             "blocks": ["News"]}
          ],
          "failedPortals": []
        }
    """.trimIndent()

    private val emptyBody = """
        {"account": "katie", "blocks": [], "channels": [], "failedPortals": []}
    """.trimIndent()

    private val nullAccountBody = """
        {"account": null, "blocks": [], "channels": [
          {"portal": "1", "channelId": "1", "name": "BBC One", "url": "/play/1/1"}
        ], "failedPortals": []}
    """.trimIndent()

    private fun probeFor(
        server: MockWebServer,
        client: OkHttpClient = OkHttpClient(),
    ): ConnectionProbe = ConnectionProbe(client, json)

    private fun base(server: MockWebServer): String = server.url("/").toString().trimEnd('/')

    @Test
    fun `200 with channels is connected`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody(channelsBody))
        server.start()
        try {
            val result = probeFor(server).probe(base(server), "katie", "s3cret")
            assertTrue(result is ProbeResult.Connected)
            val lineup = (result as ProbeResult.Connected).lineup
            assertEquals("katie", lineup.account)
            assertEquals(1, lineup.channels.size)
            assertEquals("/api/lineup", server.takeRequest().path)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `200 with zero channels is still connected`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody(emptyBody))
        server.start()
        try {
            val result = probeFor(server).probe(base(server), "katie", "s3cret")
            assertEquals(0, (result as ProbeResult.Connected).lineup.channels.size)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `200 with a null account is accepted`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody(nullAccountBody))
        server.start()
        try {
            val result = probeFor(server).probe(base(server), "katie", "s3cret")
            val lineup = (result as ProbeResult.Connected).lineup
            assertNull(lineup.account)
            assertEquals(1, lineup.channels.size)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `401 is wrong credentials`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(401))
        server.start()
        try {
            assertEquals(ProbeResult.WrongCredentials, probeFor(server).probe(base(server), "katie", "bad"))
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `404 is not stb proxy`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(404))
        server.start()
        try {
            assertTrue(probeFor(server).probe(base(server), "katie", "x") is ProbeResult.NotStbProxy)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `a non-json 200 is not stb proxy`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody("<html>hello</html>"))
        server.start()
        try {
            assertTrue(probeFor(server).probe(base(server), "katie", "x") is ProbeResult.NotStbProxy)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `json without a channels key is not stb proxy`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"account":"katie"}"""))
        server.start()
        try {
            assertTrue(probeFor(server).probe(base(server), "katie", "x") is ProbeResult.NotStbProxy)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `500 is a server error carrying the code`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(500))
        server.start()
        try {
            val result = probeFor(server).probe(base(server), "katie", "x")
            assertEquals(ProbeResult.ServerError(500), result)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `an unexpected 403 is not stb proxy, not a server error`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(403))
        server.start()
        try {
            val result = probeFor(server).probe(base(server), "katie", "x")
            assertTrue(result is ProbeResult.NotStbProxy)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `a timeout is unreachable`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(channelsBody)
                .setHeadersDelay(2, TimeUnit.SECONDS),
        )
        server.start()
        try {
            val client = OkHttpClient.Builder()
                .callTimeout(300, TimeUnit.MILLISECONDS)
                .build()
            val result = probeFor(server, client).probe(base(server), "katie", "x")
            assertTrue(result is ProbeResult.Unreachable)
            assertEquals(server.hostName + ":" + server.port, (result as ProbeResult.Unreachable).host)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `entered credentials are attached as basic auth`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody(channelsBody))
        server.start()
        try {
            probeFor(server).probe(base(server), "katie", "s3cret")
            val recorded = server.takeRequest()
            assertEquals(Credentials.basic("katie", "s3cret"), recorded.getHeader("Authorization"))
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `blank credentials attach no authorization header`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody(emptyBody))
        server.start()
        try {
            probeFor(server).probe(base(server), "", null)
            assertNull(server.takeRequest().getHeader("Authorization"))
        } finally {
            server.shutdown()
        }
    }
}
