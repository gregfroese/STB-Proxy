package cc.selfhosters.stbproxy.data.network

import okhttp3.Credentials
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Attaches HTTP Basic credentials to every request (spec 2.3) that [appliesTo]
 * accepts. The provider is read per call so switching the active account takes
 * effect immediately.
 */
class BasicAuthInterceptor(
    private val appliesTo: (HttpUrl) -> Boolean = { true },
    private val credentialsProvider: () -> Pair<String, String>?,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (request.header("Authorization") != null || !appliesTo(request.url)) {
            return chain.proceed(request)
        }
        val credentials = credentialsProvider() ?: return chain.proceed(request)
        val (username, password) = credentials
        val authorised = request.newBuilder()
            .header("Authorization", Credentials.basic(username, password))
            .build()
        return chain.proceed(authorised)
    }
}

/**
 * True for URLs on the same scheme, host and port as the server [baseUrl] names, so a
 * client shared with third-party hosts (the image loader: channel logos come straight
 * from portals) sends the login only to STB-Proxy (On Demand posters).
 */
fun sameOriginAs(baseUrl: () -> String?): (HttpUrl) -> Boolean = { url ->
    val base = baseUrl()?.toHttpUrlOrNull()
    base != null && base.scheme == url.scheme && base.host == url.host && base.port == url.port
}
