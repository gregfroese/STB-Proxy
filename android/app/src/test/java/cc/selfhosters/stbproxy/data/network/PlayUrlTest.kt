package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.model.Channel
import org.junit.Assert.assertEquals
import org.junit.Test

class PlayUrlTest {

    @Test
    fun `joins a relative url with a leading slash`() {
        assertEquals(
            "http://host:8000/play/1/12345",
            joinUrl("http://host:8000", "/play/1/12345"),
        )
    }

    @Test
    fun `joins a relative url without a leading slash`() {
        assertEquals(
            "http://host:8000/play/1/12345",
            joinUrl("http://host:8000", "play/1/12345"),
        )
    }

    @Test
    fun `a trailing slash on the base does not double up`() {
        assertEquals(
            "https://proxy.example.com/play/2/99",
            joinUrl("https://proxy.example.com/", "/play/2/99"),
        )
    }

    @Test
    fun `channel playUrl uses its relative url`() {
        val channel = Channel(
            portal = "1",
            channelId = "12345",
            name = "BBC One",
            url = "/play/1/12345",
        )
        assertEquals("http://host:8000/play/1/12345", channel.playUrl("http://host:8000"))
    }
}
