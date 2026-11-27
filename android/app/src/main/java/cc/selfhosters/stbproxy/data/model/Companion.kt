package cc.selfhosters.stbproxy.data.model

import kotlinx.serialization.Serializable

/**
 * `GET /api/companion`: the Companion APK the server offers. [url] is relative to the
 * app's base address (`/companion.apk`); [sizeBytes] is the file's size, when known.
 */
@Serializable
data class CompanionRelease(
    val versionName: String,
    val url: String,
    val sizeBytes: Long? = null,
)
