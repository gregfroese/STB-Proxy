package cc.selfhosters.stbproxy

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.CompositionLocalProvider
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.StbProxyApp
import cc.selfhosters.stbproxy.ui.theme.StbProxyTheme

/**
 * Single activity for phone and Android TV (spec 2.10). Declares both
 * LAUNCHER and LEANBACK_LAUNCHER in the manifest.
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as StbProxyApplication).container
        setContent {
            CompositionLocalProvider(LocalAppContainer provides container) {
                StbProxyTheme {
                    StbProxyApp()
                }
            }
        }
    }
}
