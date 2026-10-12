package cc.selfhosters.stbproxy.data.network

import org.junit.Assert.assertEquals
import org.junit.Test

class ProbeMessageTest {

    @Test
    fun `unreachable wording names the host`() {
        assertEquals(
            "Can't reach 192.168.1.10:8000. Check the address and that this device is on the same network.",
            probeMessage(ProbeResult.Unreachable("192.168.1.10:8000")),
        )
    }

    @Test
    fun `wrong credentials wording`() {
        assertEquals("Wrong username or password.", probeMessage(ProbeResult.WrongCredentials))
    }

    @Test
    fun `not stb proxy wording names the host`() {
        assertEquals(
            "proxy.local doesn't look like STB-Proxy.",
            probeMessage(ProbeResult.NotStbProxy("proxy.local")),
        )
    }

    @Test
    fun `server error wording carries the code`() {
        assertEquals(
            "STB-Proxy returned an error (502).",
            probeMessage(ProbeResult.ServerError(502)),
        )
    }

    @Test
    fun `hostOf keeps the port and drops the scheme`() {
        assertEquals("192.168.1.10:8000", hostOf("http://192.168.1.10:8000"))
        assertEquals("proxy.local", hostOf("https://proxy.local"))
    }
}
