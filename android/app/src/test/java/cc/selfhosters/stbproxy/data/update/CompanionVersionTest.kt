package cc.selfhosters.stbproxy.data.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionVersionTest {

    @Test
    fun `later dotted versions are newer, part by part`() {
        assertTrue(isNewerVersion("1.13.1", "1.13.0"))
        assertTrue(isNewerVersion("1.14.0", "1.13.1"))
        assertTrue(isNewerVersion("2.0", "1.14.0"))
        assertTrue(isNewerVersion("1.10.0", "1.9.9"))
    }

    @Test
    fun `the same or an older version is not newer`() {
        assertFalse(isNewerVersion("1.13.0", "1.13.0"))
        assertFalse(isNewerVersion("1.12.9", "1.13.0"))
        assertFalse(isNewerVersion("1.9.0", "1.10.0"))
    }

    @Test
    fun `missing parts count as zero`() {
        assertFalse(isNewerVersion("1.13", "1.13.0"))
        assertFalse(isNewerVersion("1.13.0.0", "1.13"))
        assertTrue(isNewerVersion("1.13.0.1", "1.13"))
        assertTrue(isNewerVersion("2", "1.99.99"))
    }

    @Test
    fun `a suffix is ignored`() {
        assertFalse(isNewerVersion("1.13.0-beta", "1.13.0"))
        assertTrue(isNewerVersion("1.14.0-rc1", "1.13.0"))
        assertFalse(isNewerVersion("1.13.0", "1.13.0-debug"))
        assertTrue(isNewerVersion("1.13.1+build7", "1.13.0"))
    }

    @Test
    fun `an unparseable version is never newer`() {
        assertFalse(isNewerVersion("", "1.13.0"))
        assertFalse(isNewerVersion("latest", "1.13.0"))
        assertFalse(isNewerVersion("1.x", "1.0"))
        assertFalse(isNewerVersion("1..2", "1.0"))
        assertFalse(isNewerVersion("v2.0", "1.13.0"))
        assertFalse(isNewerVersion("2.0", "dev"))
        assertFalse(isNewerVersion("99999999999.0", "1.0"))
    }

    @Test
    fun `parts parse to numbers`() {
        assertEquals(listOf(1, 13, 0), versionParts(" 1.13.0-beta "))
        assertNull(versionParts("-beta"))
    }
}
