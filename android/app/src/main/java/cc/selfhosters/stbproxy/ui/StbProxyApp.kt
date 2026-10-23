package cc.selfhosters.stbproxy.ui

import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import cc.selfhosters.stbproxy.data.SessionState
import cc.selfhosters.stbproxy.data.ZapScope
import cc.selfhosters.stbproxy.data.ZapScopeStore
import cc.selfhosters.stbproxy.di.AppContainer
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.isTvDevice
import cc.selfhosters.stbproxy.ui.guide.GuideScreen
import cc.selfhosters.stbproxy.ui.login.LoginScreen
import cc.selfhosters.stbproxy.ui.multiview.MultiviewScreen
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandPlayback
import cc.selfhosters.stbproxy.ui.ondemand.OnDemandCategoryScreen
import cc.selfhosters.stbproxy.ui.ondemand.OnDemandItemScreen
import cc.selfhosters.stbproxy.ui.ondemand.OnDemandPlayStart
import cc.selfhosters.stbproxy.ui.ondemand.OnDemandPlayerScreen
import cc.selfhosters.stbproxy.ui.ondemand.OnDemandScreen
import cc.selfhosters.stbproxy.ui.ondemand.PlayChoice
import cc.selfhosters.stbproxy.ui.picker.PickerScreen
import cc.selfhosters.stbproxy.ui.player.PlayerScreen
import cc.selfhosters.stbproxy.ui.settings.SettingsScreen

object Routes {
    const val PICKER = "picker"
    const val PLAYER = "player"
    const val MULTIVIEW = "multiview"
    const val GUIDE = "guide"
    const val SETTINGS = "settings"
    const val ON_DEMAND = "ondemand"

    const val ARG_PORTAL = "portal"
    const val ARG_CHANNEL_ID = "channelId"
    const val ARG_SCOPE = "scope"
    const val ARG_BLOCK = "block"
    const val ARG_LABEL = "label"
    const val ARG_KEYS = "keys"
    const val ARG_TOKEN = "token"
    const val ARG_CATEGORY = "category"
    const val ARG_NAME = "name"
    const val ARG_ID = "id"
    const val ARG_BACK = "back"

    /** Phone: one On Demand category's titles. */
    const val ON_DEMAND_CATEGORY_ROUTE = "$ON_DEMAND/category?$ARG_CATEGORY={$ARG_CATEGORY}&$ARG_NAME={$ARG_NAME}"

    /** Phone: one title's detail page. */
    const val ON_DEMAND_ITEM_ROUTE = "$ON_DEMAND/item?$ARG_PORTAL={$ARG_PORTAL}&$ARG_ID={$ARG_ID}&$ARG_BACK={$ARG_BACK}"

    fun onDemandCategory(category: String, name: String): String =
        "$ON_DEMAND/category?$ARG_CATEGORY=${Uri.encode(category)}&$ARG_NAME=${Uri.encode(name)}"

    fun onDemandItem(portal: String, id: String, backLabel: String): String =
        "$ON_DEMAND/item?$ARG_PORTAL=${Uri.encode(portal)}&$ARG_ID=${Uri.encode(id)}&$ARG_BACK=${Uri.encode(backLabel)}"

    const val ARG_SERIES = "series"
    const val ARG_SEASON = "season"
    const val ARG_EPISODE = "episode"
    const val ARG_START = "start"
    const val ARG_TITLE = "title"
    const val ARG_SUBTITLE = "subtitle"
    const val ARG_SESSION = "session"
    const val ARG_URL = "url"
    const val ARG_DURATION = "duration"

    /** The On Demand player, with the session Play started (ticket 14 → 15). */
    const val ON_DEMAND_PLAYER_ROUTE = "$ON_DEMAND/play?$ARG_PORTAL={$ARG_PORTAL}&$ARG_ID={$ARG_ID}" +
        "&$ARG_SERIES={$ARG_SERIES}&$ARG_SEASON={$ARG_SEASON}&$ARG_EPISODE={$ARG_EPISODE}" +
        "&$ARG_START={$ARG_START}&$ARG_TITLE={$ARG_TITLE}&$ARG_SUBTITLE={$ARG_SUBTITLE}" +
        "&$ARG_SESSION={$ARG_SESSION}&$ARG_URL={$ARG_URL}&$ARG_DURATION={$ARG_DURATION}"

    val ON_DEMAND_PLAYER_ARGS: List<String> = listOf(
        ARG_PORTAL, ARG_ID, ARG_SERIES, ARG_SEASON, ARG_EPISODE, ARG_START,
        ARG_TITLE, ARG_SUBTITLE, ARG_SESSION, ARG_URL, ARG_DURATION,
    )

    fun onDemandPlayer(start: OnDemandPlayStart): String {
        val key = start.choice.key
        val args = mapOf(
            ARG_PORTAL to key.portal,
            ARG_ID to (key as? OnDemandKey.Movie)?.id.orEmpty(),
            ARG_SERIES to (key as? OnDemandKey.Episode)?.seriesId.orEmpty(),
            ARG_SEASON to (key as? OnDemandKey.Episode)?.seasonId.orEmpty(),
            ARG_EPISODE to (key as? OnDemandKey.Episode)?.episodeId.orEmpty(),
            ARG_START to start.choice.startSec.toString(),
            ARG_TITLE to start.choice.title,
            ARG_SUBTITLE to start.choice.subtitle.orEmpty(),
            ARG_SESSION to start.playback.session,
            ARG_URL to start.playback.absoluteUrl,
            ARG_DURATION to (start.playback.durationSec?.toString() ?: ""),
        )
        return "$ON_DEMAND/play?" + args.entries.joinToString("&") { (k, v) -> "$k=${Uri.encode(v)}" }
    }

    /** The player route's args back as the hand-off [onDemandPlayer] encoded. */
    fun onDemandPlayStartOf(arg: (String) -> String): OnDemandPlayStart {
        val portal = arg(ARG_PORTAL)
        val series = arg(ARG_SERIES)
        val key = if (series.isEmpty()) {
            OnDemandKey.Movie(portal, arg(ARG_ID))
        } else {
            OnDemandKey.Episode(portal, series, arg(ARG_SEASON), arg(ARG_EPISODE))
        }
        val url = arg(ARG_URL)
        return OnDemandPlayStart(
            choice = PlayChoice(
                key = key,
                startSec = arg(ARG_START).toIntOrNull() ?: 0,
                title = arg(ARG_TITLE),
                subtitle = arg(ARG_SUBTITLE).takeIf { it.isNotEmpty() },
            ),
            playback = OnDemandPlayback(
                session = arg(ARG_SESSION),
                url = url,
                durationSec = arg(ARG_DURATION).toIntOrNull(),
                absoluteUrl = url,
            ),
        )
    }

    /** True for On Demand's screens (its destination and the phone's pushed screens). */
    fun isOnDemand(route: String): Boolean = route == ON_DEMAND || route.startsWith("$ON_DEMAND/")

    private const val SCOPE_GROUP = "group"
    private const val SCOPE_LIST = "list"

    /** A list scope this short rides inline; longer ones go through the [ZapScopeStore]. */
    const val INLINE_KEY_LIMIT = 50

    /** Player route carrying the channel identity and its launch Block (zap list). */
    fun player(portal: String, channelId: String, block: String): String =
        playerRoute(portal, channelId, SCOPE_GROUP, block, "", "", block)

    /** Player route for a Guide group context: an explicit label over the launch group. */
    fun playerGroup(portal: String, channelId: String, block: String, label: String): String =
        playerRoute(portal, channelId, SCOPE_GROUP, block, "", "", label)

    /** Player route for a Guide search/on-now context: an explicit ordered channel set. */
    fun playerList(
        portal: String,
        channelId: String,
        keys: List<String>,
        label: String,
        store: ZapScopeStore,
    ): String = if (keys.size <= INLINE_KEY_LIMIT) {
        playerRoute(portal, channelId, SCOPE_LIST, "", keys.joinToString(","), "", label)
    } else {
        val token = store.put(ZapScope.Channels(keys, label))
        playerRoute(portal, channelId, SCOPE_LIST, "", "", token, label)
    }

    /** The player route's zap scope, resolved from its args (token via [store]). */
    fun scopeOf(
        scope: String?,
        block: String?,
        keys: String?,
        token: String?,
        label: String?,
        store: ZapScopeStore,
    ): ZapScope = if (scope == SCOPE_LIST) {
        val parsed = keys
            ?.takeIf { it.isNotEmpty() }
            ?.split(",")
            ?.filter { it.isNotEmpty() }
            ?: store.get(token)?.keys
            ?: emptyList()
        ZapScope.Channels(parsed, label.orEmpty())
    } else {
        ZapScope.Group(block.orEmpty(), label?.takeIf { it.isNotEmpty() } ?: block.orEmpty())
    }

    private fun playerRoute(
        portal: String,
        channelId: String,
        scope: String,
        block: String,
        keys: String,
        token: String,
        label: String,
    ): String = "$PLAYER?$ARG_PORTAL=${Uri.encode(portal)}" +
        "&$ARG_CHANNEL_ID=${Uri.encode(channelId)}" +
        "&$ARG_SCOPE=${Uri.encode(scope)}" +
        "&$ARG_BLOCK=${Uri.encode(block)}" +
        "&$ARG_LABEL=${Uri.encode(label)}" +
        "&$ARG_KEYS=${Uri.encode(keys)}" +
        "&$ARG_TOKEN=${Uri.encode(token)}"
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
    val container = LocalAppContainer.current
    val isTv = isTvDevice()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val route = backStackEntry?.destination?.route
    val current = Destination.of(route)
    // Multiview and the player are full-screen video; every other screen gets the nav.
    val showNav = current != null && current != Destination.MULTIVIEW
    val availability = container.onDemandAvailability
    val onDemand by availability.enabled.collectAsStateWithLifecycle()
    val notice by availability.notice.collectAsStateWithLifecycle()
    val destinations = visibleDestinations(onDemand)
    val context = LocalContext.current

    // Switching top-level screens keeps one copy of each on the stack, with Channels
    // at the root, so Back from any of them returns to Channels and then exits.
    // Multiview is full-screen video like the player, so it stacks on top instead
    // and Back returns to whichever screen opened it.
    fun navigateTo(destination: Destination) {
        if (destination == current) return
        if (destination == Destination.MULTIVIEW) {
            navController.navigate(destination.route) { launchSingleTop = true }
            return
        }
        navController.navigate(destination.route) {
            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    // On Demand switched off (a 404 on_demand_off, or a lineup without it): leave its
    // screens for Channels; a 404 also says why, once.
    LaunchedEffect(onDemand, route) {
        if (leavesOnDemand(route, onDemand)) {
            navController.navigate(Routes.PICKER) {
                popUpTo(navController.graph.findStartDestination().id)
                launchSingleTop = true
            }
        }
    }
    LaunchedEffect(notice) {
        notice?.let {
            Toast.makeText(context, it, Toast.LENGTH_LONG).show()
            availability.consumeNotice()
        }
    }

    if (isTv) {
        TvShell(current = current, destinations = destinations, showRail = showNav, onSelect = ::navigateTo) {
            AppNavHost(navController, container)
        }
    } else {
        Scaffold(
            contentWindowInsets = WindowInsets(0),
            bottomBar = {
                if (showNav) PhoneNavBar(current = current, destinations = destinations, onSelect = ::navigateTo)
            },
        ) { padding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .consumeWindowInsets(padding),
            ) {
                AppNavHost(navController, container)
            }
        }
    }
}

@Composable
private fun AppNavHost(
    navController: NavHostController,
    container: AppContainer,
) {
    NavHost(navController = navController, startDestination = Routes.PICKER) {
        composable(Routes.PICKER) {
            PickerScreen(
                onChannelClick = { channel, launchBlock ->
                    navController.navigate(
                        Routes.player(channel.portal, channel.channelId, launchBlock),
                    )
                },
            )
        }
        composable(
            route = "${Routes.PLAYER}?${Routes.ARG_PORTAL}={${Routes.ARG_PORTAL}}" +
                "&${Routes.ARG_CHANNEL_ID}={${Routes.ARG_CHANNEL_ID}}" +
                "&${Routes.ARG_SCOPE}={${Routes.ARG_SCOPE}}" +
                "&${Routes.ARG_BLOCK}={${Routes.ARG_BLOCK}}" +
                "&${Routes.ARG_LABEL}={${Routes.ARG_LABEL}}" +
                "&${Routes.ARG_KEYS}={${Routes.ARG_KEYS}}" +
                "&${Routes.ARG_TOKEN}={${Routes.ARG_TOKEN}}",
            arguments = listOf(
                navArgument(Routes.ARG_PORTAL) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_CHANNEL_ID) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_SCOPE) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_BLOCK) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_LABEL) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_KEYS) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_TOKEN) { type = NavType.StringType; defaultValue = "" },
            ),
        ) { entry ->
            val args = entry.arguments
            val portal = args?.getString(Routes.ARG_PORTAL).orEmpty()
            val channelId = args?.getString(Routes.ARG_CHANNEL_ID).orEmpty()
            val scope = Routes.scopeOf(
                scope = args?.getString(Routes.ARG_SCOPE),
                block = args?.getString(Routes.ARG_BLOCK),
                keys = args?.getString(Routes.ARG_KEYS),
                token = args?.getString(Routes.ARG_TOKEN),
                label = args?.getString(Routes.ARG_LABEL),
                store = container.zapScopeStore,
            )
            PlayerScreen(
                portal = portal,
                channelId = channelId,
                scope = scope,
                // Pushed on top of the player, so Back comes straight back to it.
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                onOpenMultiview = { navController.navigate(Routes.MULTIVIEW) },
            )
        }
        composable(Routes.GUIDE) {
            GuideScreen(
                onChannelClick = { channel, scope ->
                    val route = when (scope) {
                        is ZapScope.Channels -> Routes.playerList(
                            channel.portal,
                            channel.channelId,
                            scope.keys,
                            scope.label,
                            container.zapScopeStore,
                        )
                        is ZapScope.Group -> Routes.playerGroup(
                            channel.portal,
                            channel.channelId,
                            scope.block,
                            scope.label,
                        )
                    }
                    navController.navigate(route)
                },
            )
        }
        composable(Routes.ON_DEMAND) {
            OnDemandScreen(
                onOpenCategory = { id, name -> navController.navigate(Routes.onDemandCategory(id, name)) },
                onOpenItem = { item, back -> navController.navigate(Routes.onDemandItem(item.portal, item.id, back)) },
                onPlay = { navController.navigate(Routes.onDemandPlayer(it)) },
            )
        }
        composable(
            route = Routes.ON_DEMAND_PLAYER_ROUTE,
            arguments = Routes.ON_DEMAND_PLAYER_ARGS.map { name ->
                navArgument(name) { type = NavType.StringType; defaultValue = "" }
            },
        ) { entry ->
            val args = entry.arguments
            OnDemandPlayerScreen(
                start = Routes.onDemandPlayStartOf { args?.getString(it).orEmpty() },
                onBack = { navController.popBackStack() },
            )
        }
        composable(
            route = Routes.ON_DEMAND_CATEGORY_ROUTE,
            arguments = listOf(
                navArgument(Routes.ARG_CATEGORY) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_NAME) { type = NavType.StringType; defaultValue = "" },
            ),
        ) { entry ->
            val name = entry.arguments?.getString(Routes.ARG_NAME).orEmpty()
            OnDemandCategoryScreen(
                category = entry.arguments?.getString(Routes.ARG_CATEGORY).orEmpty(),
                name = name,
                onBack = { navController.popBackStack() },
                onOpenItem = { item, back -> navController.navigate(Routes.onDemandItem(item.portal, item.id, back)) },
            )
        }
        composable(
            route = Routes.ON_DEMAND_ITEM_ROUTE,
            arguments = listOf(
                navArgument(Routes.ARG_PORTAL) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_ID) { type = NavType.StringType; defaultValue = "" },
                navArgument(Routes.ARG_BACK) { type = NavType.StringType; defaultValue = "" },
            ),
        ) { entry ->
            val args = entry.arguments
            OnDemandItemScreen(
                portal = args?.getString(Routes.ARG_PORTAL).orEmpty(),
                id = args?.getString(Routes.ARG_ID).orEmpty(),
                backLabel = args?.getString(Routes.ARG_BACK).orEmpty(),
                onBack = { navController.popBackStack() },
                onPlay = { navController.navigate(Routes.onDemandPlayer(it)) },
            )
        }
        composable(Routes.MULTIVIEW) {
            MultiviewScreen(onBack = { navController.popBackStack() })
        }
        composable(Routes.SETTINGS) {
            SettingsScreen()
        }
    }
}
