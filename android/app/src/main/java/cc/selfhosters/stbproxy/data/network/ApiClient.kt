package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.model.Lineup
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException

/**
 * Minimal OkHttp wrapper. Only `GET /api/lineup` is modelled for now; `/xmltv`
 * and `/play` land in later tickets. Relative channel `url`s are joined onto the
 * base URL via [playUrl].
 *
 * Reads follow spec 2.3: two retries after the first attempt, waiting
 * [retryDelaysMs] between attempts (0.5s then 1.5s by default), then the failure
 * is surfaced. Only network/HTTP failures are retried; a malformed body fails
 * immediately.
 */
class ApiClient(
    private val client: OkHttpClient,
    private val json: Json,
    private val baseUrlProvider: () -> String? = { null },
    private val retryDelaysMs: List<Long> = DEFAULT_RETRY_DELAYS_MS,
) {

    /** The normalised base URL currently in force, or null if not yet configured. */
    val baseUrl: String? get() = baseUrlProvider()

    suspend fun fetchLineup(): Lineup = withContext(Dispatchers.IO) {
        val base = requireNotNull(baseUrl) { "baseUrl is not set" }
        val request = Request.Builder().url("$base/api/lineup").build()

        var lastError: IOException? = null
        repeat(retryDelaysMs.size + 1) { attempt ->
            try {
                return@withContext execute(request)
            } catch (e: IOException) {
                lastError = e
                if (attempt < retryDelaysMs.size) {
                    delay(retryDelaysMs[attempt])
                }
            }
        }
        throw lastError ?: IOException("Request failed")
    }

    private fun execute(request: Request): Lineup {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("HTTP ${response.code}")
            }
            val body = response.body?.string() ?: throw IOException("Empty response body")
            return json.decodeFromString(Lineup.serializer(), body)
        }
    }

    fun playUrl(channel: Channel): String? = baseUrl?.let { joinUrl(it, channel.url) }

    companion object {
        val DEFAULT_RETRY_DELAYS_MS: List<Long> = listOf(500L, 1500L)
    }
}
