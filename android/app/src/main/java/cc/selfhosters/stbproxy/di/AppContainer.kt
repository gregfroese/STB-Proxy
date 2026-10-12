package cc.selfhosters.stbproxy.di

import android.content.Context
import cc.selfhosters.stbproxy.BuildConfig
import cc.selfhosters.stbproxy.data.CredentialStore
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.BasicAuthInterceptor
import cc.selfhosters.stbproxy.data.network.normaliseBaseUrl
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/**
 * Hand-written dependency container (manual DI, no Hilt).
 *
 * The single instance lives on [cc.selfhosters.stbproxy.StbProxyApplication] and is
 * exposed to Compose through [LocalAppContainer]. The [credentialStore] is a
 * constructor parameter so tests and the walking skeleton can inject one.
 */
class AppContainer(
    context: Context,
    val credentialStore: CredentialStore = seededCredentialStore(),
) {

    private val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private val okHttpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .addInterceptor(BasicAuthInterceptor { credentialStore.activeCredentials })
        .build()

    val apiClient: ApiClient = ApiClient(
        client = okHttpClient,
        json = json,
        baseUrlProvider = { credentialStore.baseUrl },
    )

    private companion object {
        /**
         * Temporary walking-skeleton seed (ticket 06): the base URL / credentials
         * supplied at build time via `-PstbProxyBaseUrl=… -PstbProxyUsername=…
         * -PstbProxyPassword=…`. Ticket 07 replaces this with real login/config.
         */
        fun seededCredentialStore(): CredentialStore = CredentialStore().apply {
            if (BuildConfig.STB_PROXY_BASE_URL.isNotBlank()) {
                baseUrl = normaliseBaseUrl(BuildConfig.STB_PROXY_BASE_URL)
            }
            if (BuildConfig.STB_PROXY_USERNAME.isNotBlank()) {
                upsert(BuildConfig.STB_PROXY_USERNAME, BuildConfig.STB_PROXY_PASSWORD)
            }
        }
    }
}
