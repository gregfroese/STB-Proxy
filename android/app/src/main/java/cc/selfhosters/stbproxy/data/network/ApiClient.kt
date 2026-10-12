package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.model.Lineup
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException

/**
 * Minimal OkHttp wrapper. Only `GET /api/lineup` is modelled for now; `/xmltv`
 * and `/play` land in later tickets. Relative channel `url`s are joined onto
 * [baseUrl].
 */
class ApiClient(
    private val client: OkHttpClient,
    private val json: Json,
) {

    @Volatile
    var baseUrl: String? = null

    suspend fun fetchLineup(): Lineup = withContext(Dispatchers.IO) {
        val base = requireNotNull(baseUrl) { "baseUrl is not set" }
        val request = Request.Builder().url("$base/api/lineup").build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("HTTP ${response.code}")
            }
            val body = response.body?.string() ?: throw IOException("Empty response body")
            json.decodeFromString(Lineup.serializer(), body)
        }
    }

    fun playUrl(channel: cc.selfhosters.stbproxy.data.model.Channel): String? {
        val base = baseUrl ?: return null
        return base + channel.url
    }
}
