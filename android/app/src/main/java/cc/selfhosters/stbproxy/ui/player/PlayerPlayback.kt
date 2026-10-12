package cc.selfhosters.stbproxy.ui.player

import android.content.Context
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.HttpDataSource
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlaybackException
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy
import androidx.media3.exoplayer.upstream.LoadErrorHandlingPolicy
import java.io.IOException

/**
 * Builds the single live-stream player (spec 2.9): progressive-live MPEG-TS over
 * HTTP with **no** `LiveConfiguration`, decoder fallback enabled and **no** FFmpeg
 * extension in v1. The stream is fed by the app's OkHttp data source (so the
 * account Basic rides along); cross-protocol redirects are left disabled by the
 * client (spec 2.6/2.9).
 */
fun buildStreamPlayer(
    context: Context,
    dataSourceFactory: DataSource.Factory,
    handleAudioFocus: Boolean = true,
): ExoPlayer {
    val renderersFactory = DefaultRenderersFactory(context)
        .setEnableDecoderFallback(true)
        .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_OFF)
    val mediaSourceFactory = DefaultMediaSourceFactory(dataSourceFactory)
        .setLoadErrorHandlingPolicy(StreamLoadErrorPolicy())
    val player = ExoPlayer.Builder(context, renderersFactory)
        .setMediaSourceFactory(mediaSourceFactory)
        .build()
    // Multiview runs several players at once: they must not fight over audio
    // focus (the loser is paused and looks "frozen"). There, audio is managed by
    // per-tile volume instead.
    player.setAudioAttributes(AudioAttributes.DEFAULT, handleAudioFocus)
    return player
}

/**
 * The media item for `/play`. The MIME type is intentionally left unset so
 * ExoPlayer sniffs the `0x47` MPEG-TS sync byte (spec 2.9); `.setMimeType(
 * MimeTypes.VIDEO_MP2T)` is a valid determinism knob but would break any
 * HLS-answered stream.
 */
fun mediaItemFor(url: String): MediaItem = MediaItem.Builder()
    .setUri(url)
    .build()

/**
 * Surfaces a 503 immediately instead of letting the default policy retry it
 * (spec 2.6). Every other error delegates to the default policy.
 */
class StreamLoadErrorPolicy(
    private val delegate: LoadErrorHandlingPolicy = DefaultLoadErrorHandlingPolicy(),
) : LoadErrorHandlingPolicy {

    override fun getMinimumLoadableRetryCount(dataType: Int): Int =
        delegate.getMinimumLoadableRetryCount(dataType)

    override fun getRetryDelayMsFor(
        loadErrorInfo: LoadErrorHandlingPolicy.LoadErrorInfo,
    ): Long = if (responseCodeOf(loadErrorInfo.exception) == 503) {
        C.TIME_UNSET
    } else {
        delegate.getRetryDelayMsFor(loadErrorInfo)
    }

    override fun getFallbackSelectionFor(
        fallbackOptions: LoadErrorHandlingPolicy.FallbackOptions,
        loadErrorInfo: LoadErrorHandlingPolicy.LoadErrorInfo,
    ): LoadErrorHandlingPolicy.FallbackSelection? =
        delegate.getFallbackSelectionFor(fallbackOptions, loadErrorInfo)
}

/**
 * Distils a Media3 [PlaybackException] into the pure [SourceErrorInfo] the
 * classifier consumes: the HTTP status (if any) and a `Location` header for the
 * 302 diagnostic. Anything else is a plain network failure.
 */
fun classifyPlaybackException(error: PlaybackException): PlaybackError {
    val source = (error as? ExoPlaybackException)?.sourceException
    var cause: Throwable? = source
    while (cause != null) {
        if (cause is HttpDataSource.InvalidResponseCodeException) {
            val location = cause.headerFields["Location"]?.firstOrNull()
            return classifySourceError(
                SourceErrorInfo(
                    isHttpResponse = true,
                    responseCode = cause.responseCode,
                    location = location,
                ),
            )
        }
        cause = cause.cause
    }
    return classifySourceError(SourceErrorInfo())
}

private fun responseCodeOf(exception: IOException): Int? {
    var cause: Throwable? = exception
    while (cause != null) {
        if (cause is HttpDataSource.InvalidResponseCodeException) return cause.responseCode
        cause = cause.cause
    }
    return null
}
