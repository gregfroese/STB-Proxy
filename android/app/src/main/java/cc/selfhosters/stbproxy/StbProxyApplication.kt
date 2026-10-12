package cc.selfhosters.stbproxy

import android.app.Application
import cc.selfhosters.stbproxy.di.AppContainer

class StbProxyApplication : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
