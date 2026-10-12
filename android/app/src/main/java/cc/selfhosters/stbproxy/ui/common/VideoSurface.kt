package cc.selfhosters.stbproxy.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.ui.compose.PlayerSurface
import androidx.media3.ui.compose.SURFACE_TYPE_SURFACE_VIEW
import androidx.media3.ui.compose.SURFACE_TYPE_TEXTURE_VIEW

/**
 * A letterboxed video surface: the stream keeps its own aspect ratio inside the
 * given box (black bars fill the rest) instead of being stretched to fit. The
 * ratio is read from the player's video size and updated as it becomes known.
 *
 * Multiview Tiles pass [useTextureView] — several `TextureView`s in one grid are
 * more reliable than several `SurfaceView`s, which can stall on some devices.
 */
@Composable
fun VideoSurface(
    player: Player,
    modifier: Modifier = Modifier,
    useTextureView: Boolean = false,
) {
    var ratio by remember { mutableFloatStateOf(player.aspectRatio()) }

    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onVideoSizeChanged(videoSize: VideoSize) {
                ratio = videoSize.aspectRatio()
            }
        }
        player.addListener(listener)
        onDispose { player.removeListener(listener) }
    }

    Box(
        modifier = modifier.background(Color.Black),
        contentAlignment = Alignment.Center,
    ) {
        PlayerSurface(
            player = player,
            modifier = if (ratio > 0f) Modifier.aspectRatio(ratio) else Modifier.fillMaxSize(),
            surfaceType = if (useTextureView) SURFACE_TYPE_TEXTURE_VIEW else SURFACE_TYPE_SURFACE_VIEW,
        )
    }
}

private fun Player.aspectRatio(): Float = videoSize.aspectRatio()

private fun VideoSize.aspectRatio(): Float =
    if (height > 0) width * pixelWidthHeightRatio / height else 0f
