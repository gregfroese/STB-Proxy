package cc.selfhosters.stbproxy.data.epg

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.time.Instant

/**
 * Best-effort XMLTV source for the now/next teaser (spec 2.8). Fetches `/xmltv`
 * with the active account's Basic (attached by the shared OkHttp client) and
 * parses it into an in-memory `Map<epgId, NowNext>`.
 *
 * If the request or parse fails, an empty map is returned and tiles simply show
 * no teaser. Ticket 09 adds the every-minute recompute / foreground refresh on
 * top of this repository.
 */
class EpgRepository(
    private val client: OkHttpClient,
    private val baseUrlProvider: () -> String?,
    private val parser: XmltvParser,
    private val clock: () -> Instant = Instant::now,
) {

    suspend fun fetch(): Map<String, NowNext> = withContext(Dispatchers.IO) {
        val base = baseUrlProvider() ?: return@withContext emptyMap()
        try {
            val request = Request.Builder().url("$base/xmltv").build()
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return@withContext emptyMap()
                val body = response.body ?: return@withContext emptyMap()
                body.byteStream().use { parser.parse(it, clock()) }
            }
        } catch (e: Exception) {
            emptyMap()
        }
    }
}
