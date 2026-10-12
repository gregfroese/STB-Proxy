package cc.selfhosters.stbproxy.data.epg

import org.xmlpull.v1.XmlPullParser
import java.io.InputStream
import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

/**
 * Parses an XMLTV guide into a `Map<epgId, NowNext>` (spec 2.8).
 *
 * The guide is multi-MB, so this is a **single-pass** [XmlPullParser] scan
 * (never DOM). `start`/`stop`/`channel` are attributes on the `<programme>`
 * start tag, so a programme is classified as *now* (`start <= now < stop`) or
 * *next* (`start > now`) from its attributes alone; everything else is skipped
 * without reading its title/description. Only the kept programmes have their
 * `<title>` read.
 *
 * The pull-parser is injected so the pure logic can be unit-tested on the JVM
 * with any `XmlPullParser` implementation.
 */
class XmltvParser(
    private val parserProvider: () -> XmlPullParser,
) {

    fun parse(input: InputStream, now: Instant): Map<String, NowNext> {
        val parser = parserProvider()
        parser.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false)
        parser.setInput(input, null)

        val nowByChannel = HashMap<String, Programme>()
        val nextByChannel = HashMap<String, Programme>()
        val nextStartByChannel = HashMap<String, Instant>()

        var event = parser.next()
        while (event != XmlPullParser.END_DOCUMENT) {
            if (event == XmlPullParser.START_TAG && parser.name == TAG_PROGRAMME) {
                val channel = parser.getAttributeValue(null, ATTR_CHANNEL)
                val start = parseXmltvTime(parser.getAttributeValue(null, ATTR_START))
                val stop = parseXmltvTime(parser.getAttributeValue(null, ATTR_STOP))

                if (channel != null && start != null) {
                    val isNow = !start.isAfter(now) && (stop == null || now.isBefore(stop))
                    val isNext = start.isAfter(now)

                    if (isNow || isNext) {
                        val info = readProgrammeInfo(parser)
                        if (!info.title.isNullOrBlank()) {
                            val programme = Programme(
                                title = info.title,
                                start = start,
                                stop = stop,
                                description = info.description,
                            )
                            if (isNow) {
                                val existing = nowByChannel[channel]
                                if (existing == null || start.isAfter(existing.start)) {
                                    nowByChannel[channel] = programme
                                }
                            } else {
                                val existingStart = nextStartByChannel[channel]
                                if (existingStart == null || start.isBefore(existingStart)) {
                                    nextStartByChannel[channel] = start
                                    nextByChannel[channel] = programme
                                }
                            }
                        }
                        // readProgrammeInfo left the parser on </programme>.
                        event = parser.eventType
                        continue
                    }
                }
            }
            event = parser.next()
        }

        val channels = nowByChannel.keys + nextByChannel.keys
        return channels.associateWith { NowNext(now = nowByChannel[it], next = nextByChannel[it]) }
    }

    /**
     * Consumes the current `<programme>` element up to (and including) its end
     * tag, returning its `<title>` and (optional) `<desc>` text. Leaves the
     * parser on the programme's END_TAG.
     */
    private fun readProgrammeInfo(parser: XmlPullParser): ProgrammeInfo {
        var title: String? = null
        var description: String? = null
        var depth = 1
        while (depth > 0) {
            when (parser.next()) {
                XmlPullParser.START_TAG -> {
                    when {
                        depth == 1 && parser.name == TAG_TITLE -> title = readElementText(parser)
                        depth == 1 && parser.name == TAG_DESC -> description = readElementText(parser)
                        else -> depth++
                    }
                }
                XmlPullParser.END_TAG -> depth--
            }
        }
        return ProgrammeInfo(title = title, description = description)
    }

    /** Reads text of the element the parser is currently on, consuming its end tag. */
    private fun readElementText(parser: XmlPullParser): String? {
        val text = StringBuilder()
        var depth = 1
        while (depth > 0) {
            when (parser.next()) {
                XmlPullParser.TEXT -> text.append(parser.text)
                XmlPullParser.START_TAG -> depth++
                XmlPullParser.END_TAG -> depth--
            }
        }
        return text.toString().trim().ifEmpty { null }
    }

    private companion object {
        const val TAG_PROGRAMME = "programme"
        const val TAG_TITLE = "title"
        const val TAG_DESC = "desc"
        const val ATTR_START = "start"
        const val ATTR_STOP = "stop"
        const val ATTR_CHANNEL = "channel"
    }
}

/** The bits of a kept `<programme>` read from its body: title and description. */
private data class ProgrammeInfo(
    val title: String?,
    val description: String?,
)

private val XMLTV_TIME_FORMATTER: DateTimeFormatter =
    DateTimeFormatter.ofPattern("uuuuMMddHHmmss[ Z]")

/**
 * Parses an XMLTV `YYYYMMDDHHmmss +0000` timestamp to an [Instant] (spec 2.8).
 * A missing offset is treated as UTC (the XMLTV DTD default). Returns null for
 * blank or malformed input.
 */
fun parseXmltvTime(raw: String?): Instant? {
    val value = raw?.trim().orEmpty()
    if (value.isEmpty()) return null
    return try {
        when (val parsed = XMLTV_TIME_FORMATTER.parseBest(
            value,
            OffsetDateTime::from,
            LocalDateTime::from,
        )) {
            is OffsetDateTime -> parsed.toInstant()
            is LocalDateTime -> parsed.toInstant(ZoneOffset.UTC)
            else -> null
        }
    } catch (e: DateTimeParseException) {
        null
    }
}
