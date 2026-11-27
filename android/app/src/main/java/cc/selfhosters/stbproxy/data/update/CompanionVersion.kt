package cc.selfhosters.stbproxy.data.update

/**
 * Whether the server's [candidate] version name is newer than the installed [current]
 * one, comparing dotted numeric parts (1.13.0 < 1.13.1 < 1.14.0 < 2.0). Missing parts
 * count as 0 and a `-suffix` (or `+build`) is ignored. Either name being unparseable
 * means "not newer", so a bad server value never prompts an update.
 */
fun isNewerVersion(candidate: String, current: String): Boolean {
    val a = versionParts(candidate) ?: return false
    val b = versionParts(current) ?: return false
    for (i in 0 until maxOf(a.size, b.size)) {
        val x = a.getOrElse(i) { 0 }
        val y = b.getOrElse(i) { 0 }
        if (x != y) return x > y
    }
    return false
}

/** `"1.13.0-beta"` → `[1, 13, 0]`; null when any part is not a whole number. */
internal fun versionParts(name: String): List<Int>? {
    val core = name.trim().substringBefore('-').substringBefore('+')
    if (core.isEmpty()) return null
    return core.split('.').map { part ->
        if (part.isEmpty() || !part.all(Char::isDigit)) return null
        part.toIntOrNull() ?: return null
    }
}
