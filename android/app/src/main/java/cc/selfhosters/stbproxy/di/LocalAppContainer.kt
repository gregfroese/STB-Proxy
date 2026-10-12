package cc.selfhosters.stbproxy.di

import androidx.compose.runtime.staticCompositionLocalOf

/** Provides the app's manual-DI [AppContainer] to the Compose tree. */
val LocalAppContainer = staticCompositionLocalOf<AppContainer> {
    error("No AppContainer provided")
}
