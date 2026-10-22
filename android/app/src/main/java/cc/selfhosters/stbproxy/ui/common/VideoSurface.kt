package cc.selfhosters.stbproxy.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.compose.PlayerSurface
import androidx.media3.ui.compose.SURFACE_TYPE_SURFACE_VIEW
import androidx.media3.ui.compose.SURFACE_TYPE_TEXTURE_VIEW
import androidx.media3.ui.compose.modifiers.resizeWithContentScale
import androidx.media3.ui.compose.state.rememberPresentationState
import cc.selfhosters.stbproxy.data.AspectMode

/**
 * A letterboxed video surface: the stream keeps its shape inside the given box
 * (black bars fill the rest) instead of being stretched to fit. [aspect] can
 * force 16:9 or 4:3 for a stream that reports the wrong shape, or zoom to fill.
 *
 * Shape comes from media3's presentation state, which accounts for non-square
 * (anamorphic SD) pixels. Until a stream's first frame is drawn the surface is
 * covered, so a zap never shows the last channel's frame at the wrong size.
 *
 * Multiview Tiles pass [useTextureView] — several `TextureView`s in one grid are
 * more reliable than several `SurfaceView`s, which can stall on some devices.
 */
@androidx.annotation.OptIn(UnstableApi::class)
@Composable
fun VideoSurface(
    player: Player,
    modifier: Modifier = Modifier,
    useTextureView: Boolean = false,
    aspect: AspectMode = AspectMode.AUTO,
) {
    val presentation = rememberPresentationState(player)
    val shape = when (aspect) {
        AspectMode.WIDE -> Size(16f, 9f)
        AspectMode.STANDARD -> Size(4f, 3f)
        AspectMode.AUTO, AspectMode.ZOOM -> presentation.videoSizeDp
    }

    Box(
        modifier = modifier
            .background(Color.Black)
            .clipToBounds(),
        contentAlignment = Alignment.Center,
    ) {
        PlayerSurface(
            player = player,
            modifier = Modifier.resizeWithContentScale(
                contentScale = if (aspect == AspectMode.ZOOM) ContentScale.Crop else ContentScale.Fit,
                sourceSizeDp = shape,
            ),
            surfaceType = if (useTextureView) SURFACE_TYPE_TEXTURE_VIEW else SURFACE_TYPE_SURFACE_VIEW,
        )
        if (presentation.coverSurface) {
            Box(modifier = Modifier.matchParentSize().background(Color.Black))
        }
    }
}
