package cc.selfhosters.stbproxy.data.network

import okhttp3.Credentials
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Attaches HTTP Basic credentials to every request (spec 2.3). The provider is
 * read per call so switching the active account takes effect immediately.
 */
class BasicAuthInterceptor(
    private val credentialsProvider: () -> Pair<String, String>?,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (request.header("Authorization") != null) {
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
