package cc.selfhosters.stbproxy.data.network

import okhttp3.Credentials
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Posters come from STB-Proxy and need Basic; channel logos come from elsewhere and must not get it. */
class ProxyOnlyAuthTest {

    @Test
    fun `Basic goes to the proxy and nowhere else`() {
        val proxy = MockWebServer().apply { start() }
        val elsewhere = MockWebServer().apply { start() }
        try {
            proxy.enqueue(MockResponse().setBody("poster"))
            elsewhere.enqueue(MockResponse().setBody("logo"))
            val client = OkHttpClient.Builder()
                .addInterceptor(
                    BasicAuthInterceptor(
                        credentialsProvider = { "katie" to "s3cret" },
                        appliesTo = sameOriginAs { proxy.url("/").toString().trimEnd('/') },
                    ),
                )
                .build()

            client.newCall(Request.Builder().url(proxy.url("/api/ondemand/poster/p1/7")).build()).execute().close()
            client.newCall(Request.Builder().url(elsewhere.url("/logo.png")).build()).execute().close()

            assertEquals(Credentials.basic("katie", "s3cret"), proxy.takeRequest().getHeader("Authorization"))
            assertNull(elsewhere.takeRequest().getHeader("Authorization"))
        } finally {
            proxy.shutdown()
            elsewhere.shutdown()
        }
    }

    @Test
    fun `nothing is sent before a server is set`() {
        val server = MockWebServer().apply { start() }
        try {
            server.enqueue(MockResponse())
            val client = OkHttpClient.Builder()
                .addInterceptor(BasicAuthInterceptor(appliesTo = sameOriginAs { null }) { "katie" to "s3cret" })
                .build()
            client.newCall(Request.Builder().url(server.url("/x")).build()).execute().close()

            assertNull(server.takeRequest().getHeader("Authorization"))
        } finally {
            server.shutdown()
        }
    }
}
