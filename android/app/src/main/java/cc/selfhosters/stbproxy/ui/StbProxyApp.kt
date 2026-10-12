package cc.selfhosters.stbproxy.ui

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import cc.selfhosters.stbproxy.ui.multiview.MultiviewScreen
import cc.selfhosters.stbproxy.ui.picker.PickerScreen
import cc.selfhosters.stbproxy.ui.player.PlayerScreen
import cc.selfhosters.stbproxy.ui.settings.SettingsScreen

object Routes {
    const val HOME = "home"
    const val PICKER = "picker"
    const val PLAYER = "player"
    const val MULTIVIEW = "multiview"
    const val SETTINGS = "settings"
}

/**
 * Navigation-Compose graph. Standard back behaviour: system Back pops the
 * back stack and exits only from [Routes.HOME] — no exit-confirm loop.
 */
@Composable
fun StbProxyApp(navController: NavHostController = rememberNavController()) {
    NavHost(navController = navController, startDestination = Routes.HOME) {
        composable(Routes.HOME) {
            HomeScreen(onNavigate = { route -> navController.navigate(route) })
        }
        composable(Routes.PICKER) {
            PickerScreen(onChannelClick = { navController.navigate(Routes.PLAYER) })
        }
        composable(Routes.PLAYER) {
            PlayerScreen()
        }
        composable(Routes.MULTIVIEW) {
            MultiviewScreen()
        }
        composable(Routes.SETTINGS) {
            SettingsScreen()
        }
    }
}
