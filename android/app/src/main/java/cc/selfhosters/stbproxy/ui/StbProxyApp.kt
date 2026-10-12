package cc.selfhosters.stbproxy.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import cc.selfhosters.stbproxy.data.SessionState
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.login.LoginScreen
import cc.selfhosters.stbproxy.ui.multiview.MultiviewScreen
import cc.selfhosters.stbproxy.ui.picker.PickerScreen
import cc.selfhosters.stbproxy.ui.player.PlayerScreen
import cc.selfhosters.stbproxy.ui.settings.SettingsScreen

object Routes {
    const val PICKER = "picker"
    const val PLAYER = "player"
    const val MULTIVIEW = "multiview"
    const val SETTINGS = "settings"
}

/**
 * Root of the app. Nothing but Login is reachable until a session is
 * established (spec 2.4); once LoggedIn the picker is the start destination.
 */
@Composable
fun StbProxyApp() {
    val container = LocalAppContainer.current
    viewModel<SessionViewModel>(factory = SessionViewModel.factory(container.sessionController))
    val sessionState by container.sessionController.state.collectAsStateWithLifecycle()

    when (val state = sessionState) {
        SessionState.Checking -> Splash()
        is SessionState.LoggedOut -> LoginScreen(reason = state.message)
        is SessionState.LoggedIn -> MainNavHost()
    }
}

@Composable
private fun Splash() {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun MainNavHost() {
    val navController = rememberNavController()
    NavHost(navController = navController, startDestination = Routes.PICKER) {
        composable(Routes.PICKER) {
            PickerScreen(
                onChannelClick = { navController.navigate(Routes.PLAYER) },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
            )
        }
        composable(Routes.PLAYER) {
            PlayerScreen()
        }
        composable(Routes.MULTIVIEW) {
            MultiviewScreen()
        }
        composable(Routes.SETTINGS) {
            SettingsScreen(onBack = { navController.popBackStack() })
        }
    }
}
