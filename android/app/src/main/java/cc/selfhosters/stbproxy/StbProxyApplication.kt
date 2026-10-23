package cc.selfhosters.stbproxy

import android.app.Application
import cc.selfhosters.stbproxy.di.AppContainer
import coil.ImageLoader
import coil.ImageLoaderFactory

class StbProxyApplication : Application(), ImageLoaderFactory {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }

    /** Coil's app-wide loader, on a client that sends the login to STB-Proxy only (posters). */
    override fun newImageLoader(): ImageLoader =
        ImageLoader.Builder(this)
            .okHttpClient { container.imageHttpClient }
            .build()
}
