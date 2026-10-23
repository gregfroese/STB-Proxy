package cc.selfhosters.stbproxy.ui.ondemand

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.unit.sp
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.picker.pickerPalette
import kotlinx.coroutines.launch

/**
 * The On Demand player's entry point: Play (the TV pane or the phone detail page) has
 * already minted the session, so [start] carries the item key, the start position
 * and the session (`playback.session`, `playback.absoluteUrl`, `playback.durationSec`).
 *
 * TODO(ticket 15): this is a placeholder until the player is built. It keeps the
 * hand-off honest: leaving ends the session and announces the title's changed viewer
 * state ([cc.selfhosters.stbproxy.data.OnDemandChanges]), so the rows, the preview
 * pane / detail page and Continue watching refetch. The real player must do the same
 * after its last progress report.
 */
@Composable
fun OnDemandPlayerScreen(start: OnDemandPlayStart, onBack: () -> Unit) {
    val container = LocalAppContainer.current
    val palette = pickerPalette()
    val back = remember { FocusRequester() }

    DisposableEffect(start.playback.session) {
        onDispose {
            container.backgroundScope.launch {
                runCatching { container.apiClient.endOnDemandSession(start.playback.session) }
                container.onDemandChanges.changed(start.choice.key.portal, start.choice.key.titleId)
            }
        }
    }
    BackHandler(onBack = onBack)
    LaunchedEffect(Unit) { runCatching { back.requestFocus() } }

    Centered(modifier = Modifier.fillMaxSize().background(palette.background)) {
        Label(start.choice.title, palette.onSurface, 22.sp)
        start.choice.subtitle?.let { Label(it, palette.muted, 14.sp) }
        Label(
            if (start.choice.startSec > 0) "Would start at ${clock(start.choice.startSec)}" else "Would start at the beginning",
            palette.muted,
            13.sp,
        )
        Label("The On Demand player isn't built yet.", palette.muted, 13.sp)
        Button(onClick = onBack, modifier = Modifier.focusRequester(back).focusRing()) { Text("Back") }
    }
}

/** The title a key belongs to: a Movie itself, or an Episode's Series. */
val OnDemandKey.titleId: String
    get() = when (this) {
        is OnDemandKey.Movie -> id
        is OnDemandKey.Episode -> seriesId
    }
