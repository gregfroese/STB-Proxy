package cc.selfhosters.stbproxy.data.epg

import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.time.Instant

/**
 * Best-effort XMLTV source for the now/next teaser (spec 2.8). Fetches `/xmltv`
 * with the active account's Basic (attached by the shared OkHttp client) and
 * parses it into an in-memory `Map<epgId, NowNext>`.
 *
 * Reads follow spec 2.3 like the lineup: two retries after the first attempt,
 * waiting [retryDelaysMs] between attempts (0.5s then 1.5s by default). Only
 * transient failures — a network error or a 5xx — are retried; a 4xx is not.
 * If the request or parse still fails, an empty map is returned and tiles simply
 * show no teaser. Ticket 09 adds the every-minute recompute / foreground refresh
 * on top of this repository.
 */
class EpgRepository(
    private val client: OkHttpClient,
    private val baseUrlProvider: () -> String?,
    private val parser: XmltvParser,
    private val clock: () -> Instant = Instant::now,
    private val retryDelaysMs: List<Long> = ApiClient.DEFAULT_RETRY_DELAYS_MS,
) {

    suspend fun fetch(): Map<String, NowNext> = withContext(Dispatchers.IO) {
        val base = baseUrlProvider() ?: return@withContext emptyMap()
        val request = Request.Builder().url("$base/xmltv").build()

        repeat(retryDelaysMs.size + 1) { attempt ->
            try {
                return@withContext execute(request)
            } catch (e: ApiException) {
                if (e.code in 400..499) return@withContext emptyMap()
                if (attempt < retryDelaysMs.size) delay(retryDelaysMs[attempt])
            } catch (e: IOException) {
                if (attempt < retryDelaysMs.size) delay(retryDelaysMs[attempt])
            } catch (e: Exception) {
                return@withContext emptyMap()
            }
        }
        emptyMap()
    }

    private fun execute(request: Request): Map<String, NowNext> {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw ApiException(response.code)
            val body = response.body ?: return emptyMap()
            return body.byteStream().use { parser.parse(it, clock()) }
        }
    }
}
