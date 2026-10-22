package cc.selfhosters.stbproxy.data

/**
 * How the player fits a channel's picture to the screen. [AUTO] trusts the
 * stream's own shape (including non-square SD pixels); the others are for
 * channels whose stream reports the wrong shape, and are remembered per channel.
 */
enum class AspectMode(val label: String) {
    AUTO("Auto"),
    WIDE("16:9"),
    STANDARD("4:3"),

    /** Fill the screen, trimming the edges. */
    ZOOM("Zoom"),
    ;

    fun next(): AspectMode = entries[(ordinal + 1) % entries.size]
}

/** One `channelKey<TAB>MODE` line per channel that isn't [AspectMode.AUTO]. */
internal fun encodeAspectModes(modes: Map<String, AspectMode>): String =
    modes.filterValues { it != AspectMode.AUTO }
        .entries
        .joinToString("\n") { (key, mode) -> "$key\t${mode.name}" }

internal fun decodeAspectModes(stored: String?): Map<String, AspectMode> =
    stored.orEmpty()
        .lineSequence()
        .mapNotNull { line ->
            val key = line.substringBefore('\t', missingDelimiterValue = "")
            val mode = AspectMode.entries.firstOrNull { it.name == line.substringAfter('\t') }
            if (key.isEmpty() || mode == null || mode == AspectMode.AUTO) null else key to mode
        }
        .toMap()
