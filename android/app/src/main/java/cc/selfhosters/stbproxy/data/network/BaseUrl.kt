package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.model.Channel

/**
 * Normalises a manually entered proxy address into the canonical
 * `scheme://host[:port]` form (spec 2.3/2.4).
 *
 * Accepts `host`, `host:port`, or a full `http(s)://…` URL. The scheme defaults
 * to `http` and `https` is preserved when typed; any trailing `/` (and any path)
 * is stripped. Throws [IllegalArgumentException] on an empty input or an
 * unsupported scheme.
 */
fun normaliseBaseUrl(raw: String): String {
    val trimmed = raw.trim()
    require(trimmed.isNotEmpty()) { "Enter a proxy address" }

    val schemeSeparator = trimmed.indexOf("://")
    val scheme: String
    val remainder: String
    if (schemeSeparator >= 0) {
        scheme = trimmed.substring(0, schemeSeparator).lowercase()
        remainder = trimmed.substring(schemeSeparator + 3)
    } else {
        scheme = "http"
        remainder = trimmed
    }
    require(scheme == "http" || scheme == "https") {
        "Unsupported scheme '$scheme' — use http or https"
    }

    val authority = remainder.substringBefore('/').trim()
    require(authority.isNotEmpty()) { "Enter a proxy address" }

    return "$scheme://$authority"
}

/** Joins a relative channel `url` onto a normalised [baseUrl]. */
fun joinUrl(baseUrl: String, relative: String): String {
    val base = baseUrl.trimEnd('/')
    return if (relative.startsWith("/")) base + relative else "$base/$relative"
}

/** The absolute `/play/...` URL for this channel against [baseUrl]. */
fun Channel.playUrl(baseUrl: String): String = joinUrl(baseUrl, url)
