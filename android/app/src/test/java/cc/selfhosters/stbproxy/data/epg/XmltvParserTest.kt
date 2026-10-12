package cc.selfhosters.stbproxy.data.epg

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.kxml2.io.KXmlParser
import java.io.ByteArrayInputStream
import java.time.Instant
import java.nio.charset.StandardCharsets

class XmltvParserTest {

    private val parser = XmltvParser { KXmlParser() }

    private val now = Instant.parse("2024-01-01T12:30:00Z")

    private val sample = """
        <?xml version="1.0" encoding="UTF-8"?>
        <tv>
          <channel id="bbc1.uk"><display-name>BBC One</display-name></channel>
          <channel id="itv1.uk"><display-name>ITV1</display-name></channel>
          <channel id="c4.uk"><display-name>Channel 4</display-name></channel>

          <programme start="20240101110000 +0000" stop="20240101120000 +0000" channel="bbc1.uk">
            <title lang="en">Morning News</title>
          </programme>
          <programme start="20240101120000 +0000" stop="20240101130000 +0000" channel="bbc1.uk">
            <title lang="en">News at Noon</title>
          </programme>
          <programme start="20240101130000 +0000" stop="20240101140000 +0000" channel="bbc1.uk">
            <title lang="en">Afternoon</title>
          </programme>

          <programme start="20240101121500 +0000" channel="itv1.uk">
            <title lang="en">Open Ended</title>
          </programme>
          <programme start="20240101133000 +0000" stop="20240101143000 +0000" channel="itv1.uk">
            <title lang="en">Later</title>
          </programme>
          <programme start="20240101131000 +0000" stop="20240101132000 +0000" channel="itv1.uk">
            <title lang="en">Earlier Next</title>
          </programme>

          <programme start="20240101140000 +0000" stop="20240101150000 +0000" channel="c4.uk">
            <title lang="en">Future Only</title>
          </programme>

          <programme start="20240101120000" channel="five.uk">
            <title lang="en">No Offset</title>
          </programme>

          <programme start="20240101120000 +0000" stop="20240101130000 +0000">
            <title lang="en">No Channel</title>
          </programme>
          <programme stop="20240101130000 +0000" channel="c4.uk">
            <title lang="en">No Start</title>
          </programme>
        </tv>
    """.trimIndent()

    private fun parse(): Map<String, NowNext> =
        ByteArrayInputStream(sample.toByteArray(StandardCharsets.UTF_8)).use { parser.parse(it, now) }

    @Test
    fun `keeps now and earliest-future next per channel`() {
        val guide = parse()

        assertEquals("News at Noon", guide.getValue("bbc1.uk").now?.title)
        assertEquals("Afternoon", guide.getValue("bbc1.uk").next?.title)

        // "Earlier Next" (13:10) must win over "Later" (13:30) even though it
        // appears later in the document.
        assertEquals("Earlier Next", guide.getValue("itv1.uk").next?.title)
    }

    @Test
    fun `tolerates a programme with no stop attribute`() {
        val guide = parse()
        val itv = guide.getValue("itv1.uk")
        assertEquals("Open Ended", itv.now?.title)
        assertNull(itv.now?.stop)
    }

    @Test
    fun `a channel with only future programmes has no now`() {
        val guide = parse()
        val c4 = guide.getValue("c4.uk")
        assertNull(c4.now)
        assertEquals("Future Only", c4.next?.title)
    }

    @Test
    fun `a programme with no offset still resolves as now`() {
        val guide = parse()
        assertEquals("No Offset", guide.getValue("five.uk").now?.title)
    }

    @Test
    fun `programmes missing channel or start are ignored`() {
        val guide = parse()
        // "No Channel" and "No Start" must not create phantom entries.
        assertEquals(setOf("bbc1.uk", "itv1.uk", "c4.uk", "five.uk"), guide.keys)
    }

    @Test
    fun `a timestamp with no offset is treated as UTC`() {
        assertEquals(Instant.parse("2024-01-01T12:00:00Z"), parseXmltvTime("20240101120000"))
    }

    @Test
    fun `timestamps parse with a numeric offset`() {
        assertEquals(Instant.parse("2024-01-01T12:00:00Z"), parseXmltvTime("20240101120000 +0000"))
        assertEquals(Instant.parse("2024-01-01T12:00:00Z"), parseXmltvTime("20240101130000 +0100"))
    }

    @Test
    fun `blank and malformed timestamps return null`() {
        assertNull(parseXmltvTime(null))
        assertNull(parseXmltvTime(""))
        assertNull(parseXmltvTime("not-a-time"))
    }
}
