package cc.selfhosters.stbproxy.ui.common

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.view.Window
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.delay

/**
 * Hides the system bars while full-screen, and restores them (and normal window
 * fitting) on exit or when the screen leaves composition.
 */
@Composable
fun ImmersiveEffect(enabled: Boolean) {
    val view = LocalView.current
    DisposableEffect(enabled, view) {
        val window = view.context.findActivity()?.window
        val controller = window?.let { WindowCompat.getInsetsController(it, view) }
        if (window != null) {
            WindowCompat.setDecorFitsSystemWindows(window, !enabled)
        }
        if (enabled) {
            controller?.systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            controller?.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            controller?.show(WindowInsetsCompat.Type.systemBars())
        }
        onDispose {
            if (window != null) {
                WindowCompat.setDecorFitsSystemWindows(window, true)
            }
            controller?.show(WindowInsetsCompat.Type.systemBars())
        }
    }
}

/**
 * Keeps the screen awake while a video is on screen (spec follow-up).
 *
 * The window flag is reference-counted: the player and Multiview both hold it,
 * and when you move from one to the other the old screen's release must not
 * clear the flag the new screen just set.
 */
@Composable
fun KeepScreenOnEffect() {
    val view = LocalView.current
    DisposableEffect(Unit) {
        val window = view.context.findActivity()?.window
        if (window != null) ScreenAwake.acquire(window)
        onDispose { if (window != null) ScreenAwake.release(window) }
    }
}

private object ScreenAwake {
    private var holders = 0

    fun acquire(window: Window) {
        holders += 1
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    fun release(window: Window) {
        holders = (holders - 1).coerceAtLeast(0)
        if (holders == 0) {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }
}

fun Context.findActivity(): Activity? {
    var context: Context = this
    while (context is ContextWrapper) {
        if (context is Activity) return context
        context = context.baseContext
    }
    return null
}

/**
 * On-screen controls that fade away after [AutoHideControls] inactivity and
 * come back on any interaction (a tap or a remote key). Kept as a tiny holder
 * so the player and Multiview share the behaviour.
 */
@Stable
class AutoHideControls(
    private val visibleState: MutableState<Boolean>,
    private val interaction: MutableState<Int>,
) {
    val visible: Boolean get() = visibleState.value

    /** Show the controls and restart the idle timer. */
    fun show() {
        visibleState.value = true
        interaction.value += 1
    }

    /** Hide the controls immediately. */
    fun hide() {
        visibleState.value = false
    }
}

@Composable
fun rememberAutoHideControls(timeoutMillis: Long = 4000L): AutoHideControls {
    val visible = remember { mutableStateOf(true) }
    val interaction = remember { mutableIntStateOf(0) }
    val key by interaction
    LaunchedEffect(key) {
        if (visible.value) {
            delay(timeoutMillis)
            visible.value = false
        }
    }
    return remember { AutoHideControls(visible, interaction) }
}
