package cc.selfhosters.stbproxy.ui

import android.net.Uri
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
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

    const val ARG_PORTAL = "portal"
    const val ARG_CHANNEL_ID = "channelId"
    const val ARG_BLOCK = "block"

    /** Player route carrying the channel identity and its launch Block (zap list). */
    fun player(portal: String, channelId: String, block: String): String =
        "$PLAYER?$ARG_PORTAL=${Uri.encode(portal)}" +
            "&$ARG_CHANNEL_ID=${Uri.encode(channelId)}" +
            "&$ARG_BLOCK=${Uri.encode(block)}"
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
                onChannelClick = { channel, launchBlock ->
                    navController.navigate(
                        Routes.player(channel.portal, channel.channelId, launchBlock),
                    )
                },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                onOpenMultiview = { navController.navigate(Routes.MULTIVIEW) },
            )
        }
        composable(
            route = "${Routes.PLAYER}?${Routes.ARG_PORTAL}={${Routes.ARG_PORTAL}}" +
                "&${Routes.ARG_CHANNEL_ID}={${Routes.ARG_CHANNEL_ID}}" +
                "&${Routes.ARG_BLOCK}={${Routes.ARG_BLOCK}}",
            arguments = listOf(
                navArgument(Routes.ARG_PORTAL) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_CHANNEL_ID) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_BLOCK) { type = NavType.StringType; defaultValue = "" },
            ),
        ) { entry ->
            PlayerScreen(
                portal = entry.arguments?.getString(Routes.ARG_PORTAL).orEmpty(),
                channelId = entry.arguments?.getString(Routes.ARG_CHANNEL_ID).orEmpty(),
                launchBlock = entry.arguments?.getString(Routes.ARG_BLOCK).orEmpty(),
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                onOpenMultiview = { navController.navigate(Routes.MULTIVIEW) },
            )
        }
        composable(Routes.MULTIVIEW) {
            MultiviewScreen(onBack = { navController.popBackStack() })
        }
        composable(Routes.SETTINGS) {
            SettingsScreen(onBack = { navController.popBackStack() })
        }
    }
}
