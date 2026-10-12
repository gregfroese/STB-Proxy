package cc.selfhosters.stbproxy.data.network

import cc.selfhosters.stbproxy.data.model.Lineup
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import okhttp3.Credentials
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.net.URI

/**
 * Outcome of the *Connect* connection probe — `GET /api/lineup` with the entered
 * Basic and a ~10s timeout (spec 2.4). A single attempt only: the operator /
 * security-off ambiguity is accepted, not retried.
 */
sealed interface ProbeResult {
    /** Reachable and shaped like STB-Proxy. [account] is null for operator/security-off. */
    data class Connected(val lineup: Lineup) : ProbeResult

    /** 401 — the credentials were rejected. */
    data object WrongCredentials : ProbeResult

    /** Network / timeout / DNS failure. */
    data class Unreachable(val host: String) : ProbeResult

    /** 404, an unexpected non-2xx (e.g. 403), a non-JSON body, or JSON without a `channels` key. */
    data class NotStbProxy(val host: String) : ProbeResult

    /** 5xx. */
    data class ServerError(val code: Int) : ProbeResult
}

/** The credentialled line shown for an operator or security-off session. */
const val OPERATOR_LABEL = "Full lineup (operator / security off)"

/** The notice shown when credentials were supplied but the proxy did not verify them. */
const val SECURITY_OFF_NOTICE = "Credentials weren't verified — proxy security is off."

/** The notice shown by the picker for a connected but empty lineup. */
const val NO_CHANNELS_NOTICE = "This account has no channels."

/** The line shown when a mid-session or auto-login request is rejected. */
const val REAUTH_MESSAGE = "Your credentials are no longer valid."

/** Maps a failed [ProbeResult] to its spec 2.4 wording. */
fun probeMessage(result: ProbeResult): String = when (result) {
    is ProbeResult.Connected -> ""
    ProbeResult.WrongCredentials -> "Wrong username or password."
    is ProbeResult.Unreachable ->
        "Can't reach ${result.host}. Check the address and that this device is on the same network."
    is ProbeResult.NotStbProxy -> "${result.host} doesn't look like STB-Proxy."
    is ProbeResult.ServerError -> "STB-Proxy returned an error (${result.code})."
}

/** Host (with port, when present) of a normalised base URL, for error wording. */
fun hostOf(baseUrl: String): String =
    try {
        URI(baseUrl).authority ?: baseUrl.substringAfter("://")
    } catch (_: Exception) {
        baseUrl.substringAfter("://")
    }

/**
 * Probes `GET /api/lineup` and classifies the response. Credentials are attached
 * directly to this request (the shared Basic-auth interceptor is not involved, so
 * the probe works before any account is stored). Pass blank credentials for an
 * anonymous probe.
 */
class ConnectionProbe(
    private val client: OkHttpClient,
    private val json: Json,
) {

    suspend fun probe(
        baseUrl: String,
        username: String?,
        password: String?,
    ): ProbeResult = withContext(Dispatchers.IO) {
        val host = hostOf(baseUrl)
        val requestBuilder = Request.Builder().url("${baseUrl.trimEnd('/')}/api/lineup")
        if (!username.isNullOrBlank() && password != null) {
            requestBuilder.header("Authorization", Credentials.basic(username, password))
        }

        try {
            client.newCall(requestBuilder.build()).execute().use { response ->
                when {
                    response.code == 401 -> ProbeResult.WrongCredentials
                    response.code == 404 -> ProbeResult.NotStbProxy(host)
                    response.code in 500..599 -> ProbeResult.ServerError(response.code)
                    !response.isSuccessful -> ProbeResult.NotStbProxy(host)
                    else -> classifyOk(host, response.body?.string())
                }
            }
        } catch (e: IOException) {
            ProbeResult.Unreachable(host)
        }
    }

    private fun classifyOk(host: String, body: String?): ProbeResult {
        if (body.isNullOrBlank()) return ProbeResult.NotStbProxy(host)
        val element = try {
            json.parseToJsonElement(body)
        } catch (_: Exception) {
            return ProbeResult.NotStbProxy(host)
        }
        val obj = element as? kotlinx.serialization.json.JsonObject ?: return ProbeResult.NotStbProxy(host)
        if (!obj.jsonObject.containsKey("channels")) return ProbeResult.NotStbProxy(host)
        val lineup = try {
            json.decodeFromJsonElement(Lineup.serializer(), obj)
        } catch (_: Exception) {
            return ProbeResult.NotStbProxy(host)
        }
        return ProbeResult.Connected(lineup)
    }
}
