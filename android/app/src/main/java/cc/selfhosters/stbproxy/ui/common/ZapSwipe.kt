package cc.selfhosters.stbproxy.ui.common

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlin.math.abs

/**
 * What a channel swipe is doing: which way ([delta] +1 = next, from a swipe up),
 * the channel it lands on, whether it has gone far enough to switch on release
 * ([armed]), and whether the switch just happened ([done]).
 */
data class ZapHint(val delta: Int, val target: String?, val armed: Boolean, val done: Boolean)

/** A vertical swipe that changes channel, plus the hint to show while it runs. */
class ZapSwipe(val modifier: Modifier, val hint: ZapHint?)

/**
 * Phone channel swipe: up = next, down = previous, switching once the finger has
 * travelled far enough. [targetName] names the channel a direction lands on, for
 * the hint. A null [onZap] turns the gesture off.
 */
@Composable
fun rememberZapSwipe(onZap: ((Int) -> Unit)?, targetName: (Int) -> String? = { null }): ZapSwipe {
    val density = LocalDensity.current
    var hint by remember { mutableStateOf<ZapHint?>(null) }
    val zap by rememberUpdatedState(onZap)
    val name by rememberUpdatedState(targetName)

    // A finished switch stays up briefly as confirmation.
    LaunchedEffect(hint) {
        if (hint?.done == true) {
            delay(1_500)
            hint = null
        }
    }

    val modifier = if (onZap == null) {
        Modifier
    } else {
        Modifier.pointerInput(Unit) {
            val threshold = with(density) { 64.dp.toPx() }
            val showAfter = with(density) { 12.dp.toPx() }
            var total = 0f
            fun deltaOf(distance: Float) = if (distance < 0) 1 else -1
            detectVerticalDragGestures(
                onDragStart = { total = 0f },
                onVerticalDrag = { change, amount ->
                    total += amount
                    change.consume()
                    hint = if (abs(total) < showAfter) {
                        null
                    } else {
                        val delta = deltaOf(total)
                        ZapHint(delta, name(delta), armed = abs(total) >= threshold, done = false)
                    }
                },
                onDragEnd = {
                    hint = if (abs(total) >= threshold) {
                        val delta = deltaOf(total)
                        val target = name(delta)
                        zap?.invoke(delta)
                        ZapHint(delta, target, armed = true, done = true)
                    } else {
                        null
                    }
                    total = 0f
                },
                onDragCancel = {
                    hint = null
                    total = 0f
                },
            )
        }
    }
    return ZapSwipe(modifier, hint)
}

/** The pill telling you which way a swipe is changing channel. */
@Composable
fun ZapSwipeHint(hint: ZapHint?, modifier: Modifier = Modifier) {
    // Keep the last hint so the pill can fade out with its text intact.
    val last = remember { arrayOfNulls<ZapHint>(1) }
    if (hint != null) last[0] = hint
    AnimatedVisibility(visible = hint != null, enter = fadeIn(), exit = fadeOut(), modifier = modifier) {
        val shown = last[0] ?: return@AnimatedVisibility
        val arrow = if (shown.delta > 0) "↑" else "↓"
        val which = if (shown.delta > 0) "next channel" else "previous channel"
        val headline = when {
            shown.done -> "$arrow ${which.replaceFirstChar { it.uppercase() }}"
            shown.armed -> "$arrow Release for $which"
            else -> "$arrow Swipe for $which"
        }
        Column(
            modifier = Modifier
                .clip(RoundedCornerShape(16.dp))
                .background(Color(0xCC000000))
                .padding(horizontal = 20.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = headline,
                color = Color.White.copy(alpha = if (shown.armed) 1f else 0.75f),
                style = MaterialTheme.typography.titleMedium,
            )
            shown.target?.let {
                Text(
                    text = it,
                    color = Color(0xFFB8C4D0),
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
