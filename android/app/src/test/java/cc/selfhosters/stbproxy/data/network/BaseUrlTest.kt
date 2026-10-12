package cc.selfhosters.stbproxy.data.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class BaseUrlTest {

    @Test
    fun `bare host defaults to http`() {
        assertEquals("http://192.168.1.10", normaliseBaseUrl("192.168.1.10"))
    }

    @Test
    fun `host with port defaults to http`() {
        assertEquals("http://192.168.1.10:8080", normaliseBaseUrl("192.168.1.10:8080"))
    }

    @Test
    fun `full http url keeps http and strips trailing slash`() {
        assertEquals("http://example.com:8000", normaliseBaseUrl("http://example.com:8000/"))
    }

    @Test
    fun `full https url preserves https`() {
        assertEquals("https://proxy.example.com", normaliseBaseUrl("https://proxy.example.com/"))
    }

    @Test
    fun `whitespace and a path are stripped`() {
        assertEquals("https://proxy.example.com:9000", normaliseBaseUrl("  https://proxy.example.com:9000/some/path/  "))
    }

    @Test
    fun `scheme is case-insensitive`() {
        assertEquals("https://host", normaliseBaseUrl("HTTPS://host"))
    }

    @Test
    fun `empty input is rejected`() {
        assertThrows(IllegalArgumentException::class.java) { normaliseBaseUrl("   ") }
    }

    @Test
    fun `unsupported scheme is rejected`() {
        assertThrows(IllegalArgumentException::class.java) { normaliseBaseUrl("ftp://host") }
    }
}
