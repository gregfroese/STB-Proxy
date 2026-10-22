package cc.selfhosters.stbproxy.data

import org.junit.Assert.assertEquals
import org.junit.Test

class AspectModeTest {

    @Test
    fun `next cycles through every mode and wraps`() {
        assertEquals(AspectMode.WIDE, AspectMode.AUTO.next())
        assertEquals(AspectMode.AUTO, AspectMode.ZOOM.next())
    }

    @Test
    fun `overrides round-trip and auto is not stored`() {
        val modes = mapOf("p1/101" to AspectMode.WIDE, "p1/102" to AspectMode.AUTO, "p2/7" to AspectMode.ZOOM)
        val decoded = decodeAspectModes(encodeAspectModes(modes))
        assertEquals(mapOf("p1/101" to AspectMode.WIDE, "p2/7" to AspectMode.ZOOM), decoded)
    }

    @Test
    fun `junk lines are ignored`() {
        assertEquals(emptyMap<String, AspectMode>(), decodeAspectModes("garbage\n\tWIDE\np1/1\tNOPE"))
        assertEquals(emptyMap<String, AspectMode>(), decodeAspectModes(null))
    }

    @Test
    fun `preferences persist a choice and drop it on auto`() {
        val storage = FakeAccountStorage()
        val prefs = ViewerPreferences(storage)
        prefs.setAspectMode("p1/101", AspectMode.STANDARD)
        assertEquals(mapOf("p1/101" to AspectMode.STANDARD), ViewerPreferences(storage).aspectModes.value)
        prefs.setAspectMode("p1/101", AspectMode.AUTO)
        assertEquals(emptyMap<String, AspectMode>(), ViewerPreferences(storage).aspectModes.value)
    }
}
