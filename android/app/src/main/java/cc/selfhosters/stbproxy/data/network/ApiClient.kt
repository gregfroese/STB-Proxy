package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.OnDemandAvailability
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.model.GuideChannelProgrammes
import cc.selfhosters.stbproxy.data.model.GuideSearchResult
import cc.selfhosters.stbproxy.data.model.Lineup
import cc.selfhosters.stbproxy.data.model.OnDemandCategories
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandEpisode
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandItemList
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandPage
import cc.selfhosters.stbproxy.data.model.OnDemandPlayback
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException

/**
 * A non-2xx HTTP response: the status [code] (e.g. 401 for re-auth) plus, when the body
 * is the API's `{error, code[, reason]}` shape, its machine [errorCode], human
 * [serverMessage] and an On Demand session's end [reason]. Built in one place,
 * [ApiClient]'s response handling.
 */
class ApiException(
    val code: Int,
    val errorCode: String? = null,
    val serverMessage: String? = null,
    val reason: String? = null,
) : IOException(serverMessage?.let { "HTTP $code: $it" } ?: "HTTP $code") {

    /** On Demand is switched off for this login (ADR 0004). */
    val isOnDemandOff: Boolean get() = code == 404 && errorCode == ON_DEMAND_OFF

    companion object {
        const val ON_DEMAND_OFF = "on_demand_off"
        const val NOT_FOUND = "not_found"
        const val BAD_REQUEST = "bad_request"
        const val BUSY = "busy"
        const val PORTAL_ERROR = "portal_error"
        const val UNSUPPORTED_STREAM = "unsupported_stream"
        const val SESSION_ENDED = "session_ended"
    }
}

/**
 * Minimal OkHttp wrapper for the viewer API: the lineup, the Guide and On Demand.
 * Relative channel `url`s are joined onto the base URL via [playUrl].
 *
 * Reads follow spec 2.3: two retries after the first attempt, waiting
 * [retryDelaysMs] between attempts (0.5s then 1.5s by default), then the failure
 * is surfaced. Only network/HTTP failures are retried; a malformed body fails
 * immediately. Writes (On Demand play, progress, session end) are never retried.
 *
 * Every non-2xx becomes an [ApiException] in one place, carrying the `{error, code}`
 * body; a 404 `on_demand_off` also switches [onDemandAvailability] off.
 */
class ApiClient(
    private val client: OkHttpClient,
    private val json: Json,
    private val baseUrlProvider: () -> String? = { null },
    private val retryDelaysMs: List<Long> = DEFAULT_RETRY_DELAYS_MS,
    /** Kept in step with the lineup's `onDemand` and with any 404 `on_demand_off`. */
    private val onDemandAvailability: OnDemandAvailability? = null,
) {

    /** The normalised base URL currently in force, or null if not yet configured. */
    val baseUrl: String? get() = baseUrlProvider()

    suspend fun fetchLineup(): Lineup = withContext(Dispatchers.IO) {
        val base = requireNotNull(baseUrl) { "baseUrl is not set" }
        getJson("$base/api/lineup", Lineup.serializer())
            .also { onDemandAvailability?.onLineup(it.onDemand) }
    }

    /**
     * The account-scoped Guide search (ADR 0002), for the Guide screen. A bad
     * regex / unknown channel comes back as [ApiException] 400/404.
     */
    suspend fun fetchGuideSearch(
        query: String,
        mode: String,
        onNow: Boolean,
        channel: String,
        limit: Int,
    ): GuideSearchResult = withContext(Dispatchers.IO) {
        val base = requireNotNull(baseUrl) { "baseUrl is not set" }
        val url = "$base/api/guide/search".toHttpUrl().newBuilder().apply {
            if (query.isNotEmpty()) addQueryParameter("q", query)
            addQueryParameter("mode", mode)
            if (onNow) addQueryParameter("now", "true")
            if (channel.isNotEmpty()) addQueryParameter("channel", channel)
            addQueryParameter("limit", limit.toString())
        }.build()
        getJson(url.toString(), GuideSearchResult.serializer())
    }

    /** One Channel's upcoming programmes for the Guide's inline timeline. */
    suspend fun fetchGuideChannel(
        portal: String,
        channelId: String,
        refresh: Boolean = false,
    ): GuideChannelProgrammes = withContext(Dispatchers.IO) {
        val base = requireNotNull(baseUrl) { "baseUrl is not set" }
        val url = "$base/api/guide/channel".toHttpUrl().newBuilder().apply {
            addQueryParameter("portal", portal)
            addQueryParameter("channelId", channelId)
            if (refresh) addQueryParameter("refresh", "1")
        }.build()
        getJson(url.toString(), GuideChannelProgrammes.serializer())
    }

    // ---- On Demand (ADR 0005/0006) ----

    /** The merged categories with exact counts, and each portal's index status. */
    suspend fun fetchOnDemandCategories(): OnDemandCategories = withContext(Dispatchers.IO) {
        getJson(onDemandUrl("categories").toString(), OnDemandCategories.serializer())
    }

    /**
     * One page of browse or search. A null [category] is All; [q] ranks by relevance,
     * and [sort] (`added`, `name`, `year`, `rating`) is sent only when chosen.
     */
    suspend fun fetchOnDemandItems(
        category: String?,
        q: String?,
        sort: String?,
        offset: Int,
        limit: Int,
    ): OnDemandPage = withContext(Dispatchers.IO) {
        val url = onDemandUrl("items").newBuilder().apply {
            if (!category.isNullOrEmpty()) addQueryParameter("category", category)
            if (!q.isNullOrEmpty()) addQueryParameter("q", q)
            if (!sort.isNullOrEmpty()) addQueryParameter("sort", sort)
            addQueryParameter("offset", offset.toString())
            addQueryParameter("limit", limit.toString())
        }.build()
        getJson(url.toString(), OnDemandPage.serializer())
    }

    /** A Movie's or Series' detail; a Series' includes its Seasons. */
    suspend fun fetchOnDemandItem(portal: String, id: String): OnDemandDetail = withContext(Dispatchers.IO) {
        getJson(onDemandUrl("item", portal, id).toString(), OnDemandDetail.serializer())
    }

    /** One Season's Episodes, ascending. */
    suspend fun fetchOnDemandSeason(
        portal: String,
        seriesId: String,
        seasonId: String,
    ): List<OnDemandEpisode> = withContext(Dispatchers.IO) {
        getJson(
            onDemandUrl("series", portal, seriesId, "season", seasonId).toString(),
            ListSerializer(OnDemandEpisode.serializer()),
        )
    }

    /** Continue watching: up to 20 items, most recently played first. */
    suspend fun fetchOnDemandContinue(): List<OnDemandItem> = withContext(Dispatchers.IO) {
        getJson(onDemandUrl("continue").toString(), OnDemandItemList.serializer()).items
    }

    /**
     * Starts an On Demand session; [replaces] hands over a session this login holds.
     * Never retried: a 503 `busy` or a 502 surfaces at once as [ApiException].
     */
    suspend fun playOnDemand(key: OnDemandKey, replaces: String? = null): OnDemandPlayback =
        withContext(Dispatchers.IO) {
            val body = buildJsonObject {
                putKey(key)
                if (replaces != null) put("replaces", replaces)
            }
            val request = Request.Builder().url(onDemandUrl("play")).post(body.asRequestBody()).build()
            val playback = execute(request, OnDemandPlayback.serializer())
            playback.copy(absoluteUrl = joinUrl(requireBase(), playback.url))
        }

    /** A playback report (ADR 0006): fire-and-forget, never retried. */
    suspend fun reportOnDemandProgress(key: OnDemandKey, positionSec: Int, durationSec: Int?) =
        putProgress(
            buildJsonObject {
                putKey(key)
                put("positionSec", positionSec)
                put("durationSec", durationSec)
            },
        )

    /** The Mark watched toggle. */
    suspend fun markOnDemandWatched(key: OnDemandKey, watched: Boolean) =
        putProgress(
            buildJsonObject {
                putKey(key)
                put("watched", watched)
            },
        )

    /** Releases an On Demand session's slot now (idempotent for this login's own). */
    suspend fun endOnDemandSession(sid: String) = withContext(Dispatchers.IO) {
        execute(Request.Builder().url(onDemandUrl("session", sid)).delete().build())
    }

    /** A server-relative poster path as an absolute URL, or null when there is none. */
    fun onDemandPosterUrl(poster: String?): String? =
        poster?.takeIf { it.isNotEmpty() }?.let { path -> baseUrl?.let { joinUrl(it, path) } }

    private suspend fun putProgress(body: JsonObject) = withContext(Dispatchers.IO) {
        execute(Request.Builder().url(onDemandUrl("progress")).put(body.asRequestBody()).build())
    }

    private fun requireBase(): String = requireNotNull(baseUrl) { "baseUrl is not set" }

    private fun onDemandUrl(vararg segments: String): HttpUrl =
        "${requireBase()}/api/ondemand".toHttpUrl().newBuilder().apply {
            segments.forEach { addPathSegment(it) }
        }.build()

    private fun JsonObject.asRequestBody(): RequestBody = toString().toRequestBody(JSON_MEDIA_TYPE)

    private fun JsonObjectBuilder.putKey(key: OnDemandKey) {
        put("portal", key.portal)
        when (key) {
            is OnDemandKey.Movie -> put("id", key.id)
            is OnDemandKey.Episode -> {
                put("seriesId", key.seriesId)
                put("seasonId", key.seasonId)
                put("episodeId", key.episodeId)
            }
        }
    }

    /** A GET with the spec-2.3 retry policy, decoding a json body into [T]. */
    private suspend fun <T> getJson(url: String, deserializer: DeserializationStrategy<T>): T {
        val request = Request.Builder().url(url).build()
        var lastError: IOException? = null
        repeat(retryDelaysMs.size + 1) { attempt ->
            try {
                return execute(request, deserializer)
            } catch (e: IOException) {
                if (e is ApiException && e.code in 400..499) throw e
                lastError = e
                if (attempt < retryDelaysMs.size) {
                    delay(retryDelaysMs[attempt])
                }
            }
        }
        throw lastError ?: IOException("Request failed")
    }

    /**
     * Best-effort reads of the proxy's Tuner budget from `GET /discover.json`
     * (spec 2.7). This drives the app's proactive "all tuners busy" marking; a
     * missing key, non-2xx, or unreachable proxy returns null and the caller
     * falls back to a default. A single attempt only — it is a hint, not a
     * correctness requirement.
     */
    suspend fun fetchTunerCount(): Int? = withContext(Dispatchers.IO) {
        val base = baseUrl ?: return@withContext null
        try {
            val request = Request.Builder().url("$base/discover.json").build()
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return@withContext null
                val body = response.body?.string() ?: return@withContext null
                val obj = json.parseToJsonElement(body) as? JsonObject
                obj?.get("TunerCount")?.jsonPrimitive?.intOrNull?.takeIf { it > 0 }
            }
        } catch (e: Exception) {
            null
        }
    }

    private fun <T> execute(request: Request, deserializer: DeserializationStrategy<T>): T {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw failure(response)
            val body = response.body?.string() ?: throw IOException("Empty response body")
            return json.decodeFromString(deserializer, body)
        }
    }

    /** A request whose success carries no body worth reading (a 204). */
    private fun execute(request: Request) {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw failure(response)
        }
    }

    /**
     * The one place a non-2xx becomes an [ApiException]: the `{error, code, reason}` body
     * is read when there is one, and `on_demand_off` switches On Demand off app-wide.
     */
    private fun failure(response: Response): ApiException {
        val body = runCatching {
            json.parseToJsonElement(response.body?.string().orEmpty()) as? JsonObject
        }.getOrNull()

        fun field(name: String): String? =
            (body?.get(name) as? JsonPrimitive)?.takeIf { it.isString }?.content

        val exception = ApiException(
            code = response.code,
            errorCode = field("code"),
            serverMessage = field("error"),
            reason = field("reason"),
        )
        if (exception.isOnDemandOff) onDemandAvailability?.switchedOff()
        return exception
    }

    fun playUrl(channel: Channel): String? = baseUrl?.let { joinUrl(it, channel.url) }

    companion object {
        val DEFAULT_RETRY_DELAYS_MS: List<Long> = listOf(500L, 1500L)
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()
    }
}
