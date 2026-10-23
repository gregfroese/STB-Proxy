package cc.selfhosters.stbproxy.ui

import androidx.annotation.StringRes
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import cc.selfhosters.stbproxy.R
import cc.selfhosters.stbproxy.ui.common.MultiviewIcon
import cc.selfhosters.stbproxy.ui.common.TvFocusColor

/**
 * The app's top-level destinations. Every browse screen shows the
 * [visibleDestinations], in this order: a left rail on TV, a bottom bar on phones.
 * Multiview opens full screen (like the player) and Back returns to where you were.
 */
enum class Destination(val route: String, @StringRes val label: Int, val icon: ImageVector) {
    CHANNELS(Routes.PICKER, R.string.nav_channels, Icons.AutoMirrored.Filled.List),
    GUIDE(Routes.GUIDE, R.string.nav_guide, Icons.Filled.DateRange),
    ON_DEMAND(Routes.ON_DEMAND, R.string.nav_on_demand, Icons.Filled.PlayArrow),
    MULTIVIEW(Routes.MULTIVIEW, R.string.nav_multiview, MultiviewIcon),
    SETTINGS(Routes.SETTINGS, R.string.nav_settings, Icons.Filled.Settings),
    ;

    companion object {
        /** The destination a route belongs to, or null for full-screen routes (the player). */
        fun of(route: String?): Destination? = entries.firstOrNull { it.route == route }
    }
}

/** The destinations the nav shows: On Demand only when the lineup offers it (ADR 0004). */
fun visibleDestinations(onDemand: Boolean): List<Destination> =
    Destination.entries.filter { it != Destination.ON_DEMAND || onDemand }

/** True when [route] is one of On Demand's screens and On Demand has gone: back to Channels. */
fun leavesOnDemand(route: String?, onDemand: Boolean): Boolean =
    !onDemand && route != null && Routes.isOnDemand(route)

/**
 * The TV nav rail, for screens that send focus to it (Back from On Demand's panes).
 * Requesting focus lands on the current destination. Null on phones.
 */
val LocalNavRail = staticCompositionLocalOf<FocusRequester?> { null }

private val RailCollapsed = 76.dp
private val RailExpanded = 232.dp

/**
 * TV shell: a slim icon rail on the left that widens to show labels while it has
 * focus (the usual Google TV pattern), overlaying the screen beside it. Press Left
 * from a screen's leftmost item to reach it; entering always lands on the current
 * destination.
 */
@Composable
fun TvShell(
    current: Destination?,
    destinations: List<Destination>,
    showRail: Boolean,
    onSelect: (Destination) -> Unit,
    content: @Composable () -> Unit,
) {
    val railFocus = remember { FocusRequester() }
    Box(modifier = Modifier.fillMaxSize()) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(start = if (showRail) RailCollapsed else 0.dp),
        ) {
            CompositionLocalProvider(LocalNavRail provides railFocus.takeIf { showRail }) {
                content()
            }
        }
        if (showRail) {
            TvNavRail(
                current = current,
                destinations = destinations,
                onSelect = onSelect,
                modifier = Modifier
                    .zIndex(1f)
                    .focusRequester(railFocus),
            )
        }
    }
}

@Composable
private fun TvNavRail(
    current: Destination?,
    destinations: List<Destination>,
    onSelect: (Destination) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    val width by animateDpAsState(if (expanded) RailExpanded else RailCollapsed, label = "rail")
    val requesters = remember { Destination.entries.associateWith { FocusRequester() } }
    val colors = MaterialTheme.colorScheme
    val background = if (expanded) {
        Brush.horizontalGradient(
            0f to colors.surface,
            0.75f to colors.surface,
            1f to colors.surface.copy(alpha = 0.92f),
        )
    } else {
        Brush.horizontalGradient(listOf(colors.background, colors.background))
    }

    Column(
        modifier = modifier
            .fillMaxHeight()
            .width(width)
            .background(background)
            .onFocusChanged { expanded = it.hasFocus }
            .focusProperties {
                onEnter = { current?.takeIf { it in destinations }?.let { requesters.getValue(it).requestFocus() } }
            }
            .focusGroup()
            .padding(horizontal = 14.dp, vertical = 28.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Image(
            painter = painterResource(R.drawable.ic_launcher_foreground),
            contentDescription = null,
            modifier = Modifier
                .padding(bottom = 16.dp)
                .size(48.dp),
        )
        destinations.forEach { destination ->
            RailItem(
                destination = destination,
                selected = destination == current,
                expanded = expanded,
                modifier = Modifier.focusRequester(requesters.getValue(destination)),
                onClick = { onSelect(destination) },
            )
        }
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun RailItem(
    destination: Destination,
    selected: Boolean,
    expanded: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val label = stringResource(destination.label)
    val colors = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(50)
    val tint = when {
        focused -> colors.onPrimary
        selected -> colors.primary
        else -> colors.onSurfaceVariant
    }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(48.dp)
            .clip(shape)
            .background(
                when {
                    focused -> colors.primary
                    selected -> colors.primary.copy(alpha = 0.16f)
                    else -> Color.Transparent
                },
            )
            .border(if (focused) 2.dp else 0.dp, if (focused) TvFocusColor else Color.Transparent, shape)
            .onFocusChanged { focused = it.isFocused }
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(destination.icon, contentDescription = label, tint = tint, modifier = Modifier.size(24.dp))
        AnimatedVisibility(visible = expanded, enter = fadeIn(), exit = fadeOut()) {
            Text(
                text = label,
                color = tint,
                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                maxLines = 1,
                softWrap = false,
                modifier = Modifier.padding(start = 16.dp),
            )
        }
    }
}

/** Phone bottom navigation, shown on the browse screens. */
@Composable
fun PhoneNavBar(
    current: Destination?,
    destinations: List<Destination>,
    onSelect: (Destination) -> Unit,
) {
    NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
        destinations.forEach { destination ->
            NavigationBarItem(
                selected = destination == current,
                onClick = { onSelect(destination) },
                icon = { Icon(destination.icon, contentDescription = null) },
                label = { Text(stringResource(destination.label), maxLines = 1) },
            )
        }
    }
}
