package cc.selfhosters.stbproxy.ui.common

import androidx.compose.foundation.border
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** The accent used for the TV focus ring. */
val TvFocusColor = Color(0xFFFFD34D)

/**
 * A bright ring around an element while it holds TV focus, so the remote's current
 * position is obvious. Applied on top of a button's own modifier.
 */
@Composable
fun Modifier.focusRing(
    shape: Shape = RoundedCornerShape(50),
    color: Color = TvFocusColor,
    width: Dp = 3.dp,
): Modifier {
    var focused by remember { mutableStateOf(false) }
    return this
        .onFocusChanged { focused = it.isFocused }
        .border(
            width = if (focused) width else 0.dp,
            color = if (focused) color else Color.Transparent,
            shape = shape,
        )
}
