package cc.selfhosters.stbproxy.di

import android.content.Context
import android.util.Xml
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import cc.selfhosters.stbproxy.BuildConfig
import cc.selfhosters.stbproxy.data.AccountStore
import cc.selfhosters.stbproxy.data.AccountStorage
import cc.selfhosters.stbproxy.data.AndroidAccountStorage
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.ViewerPreferences
import cc.selfhosters.stbproxy.data.ZapScopeStore
import cc.selfhosters.stbproxy.data.epg.EpgRepository
import cc.selfhosters.stbproxy.data.epg.XmltvParser
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.BasicAuthInterceptor
import cc.selfhosters.stbproxy.data.network.ConnectionProbe
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/**
 * Hand-written dependency container (manual DI, no Hilt).
 *
 * The single instance lives on [cc.selfhosters.stbproxy.StbProxyApplication] and is
 * exposed to Compose through [LocalAppContainer]. The [accountStore] is a
 * constructor parameter so tests can inject a fake-backed one.
 */
class AppContainer(
    context: Context,
    storage: AccountStorage = AndroidAccountStorage(context.applicationContext),
    val accountStore: AccountStore = AccountStore(storage),
) {

    /** Per-device viewer preferences (the picker's grouping taxonomy). */
    val viewerPreferences: ViewerPreferences = ViewerPreferences(storage)

    /** Holds list zap scopes the player route carries by token (ticket 07). */
    val zapScopeStore: ZapScopeStore = ZapScopeStore()

    private val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    /** Client for the app's reads; carries the active account's Basic on every call. */
    private val okHttpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .addInterceptor(BasicAuthInterceptor { accountStore.activeCredentials() })
        .build()

    /** Dedicated ~10s probe client with its own credentials attached per request. */
    private val probeClient: OkHttpClient = OkHttpClient.Builder()
        .callTimeout(10, TimeUnit.SECONDS)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    val connectionProbe: ConnectionProbe = ConnectionProbe(client = probeClient, json = json)

    val sessionController: SessionController = SessionController(accountStore, connectionProbe)

    val apiClient: ApiClient = ApiClient(
        client = okHttpClient,
        json = json,
        baseUrlProvider = { accountStore.state.value.baseUrl },
    )

    /** Best-effort now/next source for the picker teaser and the player (spec 2.8). */
    val epgRepository: EpgRepository = EpgRepository(
        client = okHttpClient,
        baseUrlProvider = { accountStore.state.value.baseUrl },
        parser = XmltvParser { Xml.newPullParser() },
    )

    /**
     * ExoPlayer's data source (spec 2.9): the shared OkHttp client so the account
     * Basic rides along, with cross-protocol redirects left disabled (spec 2.6).
     * Streaming reads get a longer timeout than the API reads.
     */
    val playerDataSourceFactory: DataSource.Factory = OkHttpDataSource.Factory(
        okHttpClient.newBuilder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .followSslRedirects(false)
            .build(),
    ).setUserAgent("STBProxy/${BuildConfig.VERSION_NAME}")
}
