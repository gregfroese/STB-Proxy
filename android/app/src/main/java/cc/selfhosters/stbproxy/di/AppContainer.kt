package cc.selfhosters.stbproxy.di

import android.content.Context
import cc.selfhosters.stbproxy.data.CredentialStore
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.BasicAuthInterceptor
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/**
 * Hand-written dependency container (manual DI, no Hilt).
 *
 * The single instance lives on [cc.selfhosters.stbproxy.StbProxyApplication] and is
 * exposed to Compose through [LocalAppContainer].
 */
class AppContainer(context: Context) {

    val credentialStore: CredentialStore = CredentialStore()

    private val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private val okHttpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .addInterceptor(BasicAuthInterceptor { credentialStore.activeCredentials })
        .build()

    val apiClient: ApiClient = ApiClient(okHttpClient, json)
}
