package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.model.Lineup
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LineupSerializationTest {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    @Test
    fun `deserialises a representative api-lineup body`() {
        val body = """
            {
              "account": "katie",
              "blocks": ["Kids", "News", "Sports"],
              "channels": [
                {
                  "portal": "1",
                  "portalName": "Provider A",
                  "channelId": "12345",
                  "name": "BBC One",
                  "number": "101",
                  "logo": "https://cdn.example.com/bbc1.png",
                  "genre": "News",
                  "epgId": "bbc1.uk",
                  "blocks": ["News", "Sports"],
                  "url": "/play/1/12345"
                }
              ],
              "failedPortals": []
            }
        """.trimIndent()

        val lineup = json.decodeFromString(Lineup.serializer(), body)

        assertEquals("katie", lineup.account)
        assertEquals(listOf("Kids", "News", "Sports"), lineup.blocks)
        assertEquals(1, lineup.channels.size)

        val channel = lineup.channels.first()
        assertEquals("1", channel.portal)
        assertEquals("Provider A", channel.portalName)
        assertEquals("12345", channel.channelId)
        assertEquals("BBC One", channel.name)
        assertEquals("101", channel.number)
        assertEquals("https://cdn.example.com/bbc1.png", channel.logo)
        assertEquals("News", channel.genre)
        assertEquals("bbc1.uk", channel.epgId)
        assertEquals(listOf("News", "Sports"), channel.blocks)
        assertEquals("/play/1/12345", channel.url)
        assertTrue(lineup.failedPortals.isEmpty())
    }

    @Test
    fun `operator and public-channel shapes deserialise`() {
        val body = """
            {
              "account": null,
              "blocks": [],
              "channels": [
                {
                  "portal": "2",
                  "portalName": "Provider B",
                  "channelId": "9",
                  "name": "Public Channel",
                  "number": null,
                  "logo": null,
                  "genre": null,
                  "epgId": "2.9",
                  "blocks": [],
                  "url": "/play/2/9"
                }
              ],
              "failedPortals": ["Provider C"]
            }
        """.trimIndent()

        val lineup = json.decodeFromString(Lineup.serializer(), body)

        assertNull(lineup.account)
        assertTrue(lineup.blocks.isEmpty())
        assertEquals(listOf("Provider C"), lineup.failedPortals)
        val channel = lineup.channels.first()
        assertNull(channel.number)
        assertNull(channel.logo)
        assertTrue(channel.blocks.isEmpty())
    }

    @Test
    fun `unknown fields are ignored`() {
        val body = """
            {
              "account": "op",
              "blocks": ["A"],
              "channels": [],
              "failedPortals": [],
              "futureField": {"nested": true}
            }
        """.trimIndent()

        val lineup = json.decodeFromString(Lineup.serializer(), body)
        assertEquals("op", lineup.account)
    }
}
