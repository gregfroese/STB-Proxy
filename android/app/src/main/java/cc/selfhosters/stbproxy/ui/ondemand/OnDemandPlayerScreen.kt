package cc.selfhosters.stbproxy.ui.ondemand

import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.os.SystemClock
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.C
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import cc.selfhosters.stbproxy.data.AspectMode
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.ImmersiveEffect
import cc.selfhosters.stbproxy.ui.common.KeepScreenOnEffect
import cc.selfhosters.stbproxy.ui.common.VideoSurface
import cc.selfhosters.stbproxy.ui.common.findActivity
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.common.isTvDevice
import cc.selfhosters.stbproxy.ui.common.rememberAutoHideControls
import cc.selfhosters.stbproxy.ui.picker.pickerPalette
import cc.selfhosters.stbproxy.ui.player.buildStreamPlayer
import cc.selfhosters.stbproxy.ui.player.httpFailureOf
import cc.selfhosters.stbproxy.ui.player.onDemandMediaItem
import cc.selfhosters.stbproxy.ui.player.shouldAutoFullscreen
import kotlinx.coroutines.delay
import kotlin.math.roundToInt

/** [PlaybackPort] over the Media3 player. */
private class ExoPlaybackPort(private val player: ExoPlayer) : PlaybackPort {
    override val positionMs: Long get() = player.currentPosition
    override val durationMs: Long? get() = player.duration.takeIf { it != C.TIME_UNSET && it > 0 }
    override val isPlaying: Boolean get() = player.isPlaying
    override val playWhenReady: Boolean get() = player.playWhenReady

    override fun load(url: String, startMs: Long) {
        player.setMediaItem(onDemandMediaItem(url), startMs)
        player.prepare()
        player.playWhenReady = true
    }

    override fun seekTo(ms: Long) = player.seekTo(ms)
    override fun play() {
        if (player.playbackState == Player.STATE_IDLE) player.prepare()
        player.play()
    }

    override fun pause() = player.pause()
    override fun stop() = player.stop()
}

/** What the Media3 listener sees, for the controls. */
private class PictureState {
    var playing by mutableStateOf(false)
    var buffering by mutableStateOf(true)
    var playWhenReady by mutableStateOf(true)
}

/**
 * The On Demand player (ticket 15; ticket 11's answer: A's transport bar with B's end
 * card). Play (the TV pane or the phone detail page) has already minted the session,
 * so [start] carries the item, the start position and the session; the player seeks
 * there once loaded and only mints again to hand over (`replaces`) or after a 410.
 *
 * Not a mode of the live `PlayerScreen`: no zap, sidebar or Guide. It shares the
 * Media3 setup, the auto-hide timer, immersive mode, the letterboxed surface with a
 * per-title Aspect, and the live player's focus approach (the actions while the
 * controls are up, the screen once they fade). Leaving ends the session and announces
 * the title's change after the last progress report.
 */
@Composable
fun OnDemandPlayerScreen(start: OnDemandPlayStart, onBack: () -> Unit) {
    val container = LocalAppContainer.current
    val context = LocalContext.current
    val configuration = LocalConfiguration.current
    val isTv = isTvDevice()
    val isLandscape = configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
    val scope = rememberCoroutineScope()

    val player = remember { buildStreamPlayer(context, container.playerDataSourceFactory) }
    val controller = remember {
        OnDemandPlayerController(
            start = start,
            api = container.apiClient,
            port = ExoPlaybackPort(player),
            scope = scope,
            background = container.backgroundScope,
            changes = container.onDemandChanges,
            clock = SystemClock::elapsedRealtime,
            onUnauthorized = container.sessionController::reportUnauthorized,
        )
    }
    val state by controller.state.collectAsStateWithLifecycle()
    val picture = remember { PictureState() }

    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                picture.buffering = playbackState == Player.STATE_BUFFERING
                if (playbackState == Player.STATE_ENDED) controller.onEnded()
            }

            override fun onIsPlayingChanged(isPlaying: Boolean) {
                picture.playing = isPlaying
            }

            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                picture.playWhenReady = playWhenReady
            }

            override fun onPlayerError(error: PlaybackException) {
                val (status, body) = httpFailureOf(error)
                controller.onPlaybackFailed(status, body)
            }
        }
        player.addListener(listener)
        controller.begin()
        onDispose {
            player.removeListener(listener)
            // The last report reads the position, so it goes before the release.
            controller.close()
            player.release()
        }
    }

    var positionMs by remember { mutableLongStateOf(start.choice.startSec * 1000L) }
    var durationMs by remember { mutableLongStateOf((start.playback.durationSec ?: 0) * 1000L) }
    LaunchedEffect(controller) {
        while (true) {
            positionMs = player.currentPosition
            durationMs = state.durationSec?.let { it * 1000L }
                ?: player.duration.takeIf { it != C.TIME_UNSET && it > 0 } ?: 0L
            controller.tick()
            delay(250)
        }
    }

    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { controller.onStop() }
    LaunchedEffect(state.finished) { if (state.finished) onBack() }
    LaunchedEffect(state.toast) {
        state.toast?.let {
            Toast.makeText(context, it, Toast.LENGTH_LONG).show()
            controller.toastShown()
        }
    }

    KeepScreenOnEffect()
    var immersive by remember { mutableStateOf(shouldAutoFullscreen(isTv, isLandscape)) }
    LaunchedEffect(isTv, isLandscape) {
        if (!isTv) immersive = shouldAutoFullscreen(isTv, isLandscape)
    }
    ImmersiveEffect(enabled = immersive)
    // ⛶ in portrait turns the phone to landscape; let it rotate freely again on leave.
    var forcedLandscape by remember { mutableStateOf(false) }
    DisposableEffect(forcedLandscape) {
        val activity = context.findActivity()
        if (forcedLandscape) activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        onDispose {
            if (forcedLandscape) activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        }
    }
    val onToggleFullscreen = {
        if (immersive) {
            immersive = false
            forcedLandscape = false
        } else {
            immersive = true
            if (!isLandscape) forcedLandscape = true
        }
    }

    // Aspect, remembered per title (an Episode shares its Series').
    val aspectModes by container.viewerPreferences.aspectModes.collectAsStateWithLifecycle()
    val aspectKey = "od:${state.choice.key.portal}/${state.choice.key.titleId}"
    val aspect = aspectModes[aspectKey] ?: AspectMode.AUTO
    val onCycleAspect = { container.viewerPreferences.setAspectMode(aspectKey, aspect.next()) }

    val controls = rememberAutoHideControls()
    var dragging by remember { mutableStateOf(false) }
    val modal = state.endCard != null || state.overlay != null
    val loading = state.starting || picture.buffering
    // Paused, loading or dragging keep the controls up.
    val pinned = !picture.playWhenReady || loading || dragging
    val shown = !modal && (controls.visible || pinned)
    LaunchedEffect(pinned) { if (!pinned) controls.show() }

    // TV focus: the overlay's / end card's default button, ▶/❚❚ (or the bar after a
    // seek) while the controls are up, else the screen itself so keys still arrive.
    val screenFocus = remember { FocusRequester() }
    val playFocus = remember { FocusRequester() }
    val barFocus = remember { FocusRequester() }
    val modalFocus = remember { FocusRequester() }
    var barFocused by remember { mutableStateOf(false) }
    var focusBar by remember { mutableStateOf(false) }
    LaunchedEffect(isTv, shown, state.endCard, state.overlay, state.starting) {
        if (!isTv) return@LaunchedEffect
        runCatching {
            when {
                modal -> modalFocus.requestFocus()
                shown && focusBar -> barFocus.requestFocus()
                shown -> playFocus.requestFocus()
                else -> screenFocus.requestFocus()
            }
        }
        focusBar = false
    }

    val seekKeys = remember { SeekKeys(SystemClock::uptimeMillis) }
    var flash by remember { mutableStateOf<Pair<String, Int>?>(null) }
    LaunchedEffect(flash) {
        if (flash != null) {
            delay(700)
            flash = null
        }
    }
    val seekBy = { seconds: Int ->
        controller.seekBy(seconds)
        flash = (if (seconds > 0) "+$seconds s" else "−${-seconds} s") to seconds
    }

    BackHandler {
        controller.input()
        if (isTv && shown && !pinned) controls.hide() else onBack()
    }

    val tvKeys = Modifier.onPreviewKeyEvent { event ->
        if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
        controller.input()
        when (event.key) {
            Key.MediaPlayPause, Key.MediaPlay, Key.MediaPause, Key.Spacebar -> {
                controller.togglePause()
                controls.show()
                true
            }
            Key.MediaFastForward -> {
                seekBy(10); controls.show(); true
            }
            Key.MediaRewind -> {
                seekBy(-10); controls.show(); true
            }
            else -> when {
                modal -> false
                (event.key == Key.DirectionLeft || event.key == Key.DirectionRight) && (!shown || barFocused) -> {
                    val direction = if (event.key == Key.DirectionLeft) -1 else 1
                    seekKeys.press(direction, event.nativeKeyEvent.repeatCount > 0)?.let(seekBy)
                    if (!shown) focusBar = true
                    controls.show()
                    true
                }
                !shown && (event.key == Key.DirectionCenter || event.key == Key.Enter || event.key == Key.NumPadEnter) -> {
                    controller.togglePause()
                    controls.show()
                    true
                }
                !shown -> {
                    controls.show(); true
                }
                else -> {
                    controls.show(); false
                }
            }
        }
    }

    val stage: @Composable (Modifier, Boolean) -> Unit = { modifier, compact ->
        PlayerStage(
            state = state,
            player = player,
            isTv = isTv,
            compact = compact,
            immersive = immersive,
            shown = shown,
            loading = loading,
            playWhenReady = picture.playWhenReady,
            positionMs = positionMs,
            durationMs = durationMs,
            aspect = aspect,
            flash = flash,
            focus = StageFocus(playFocus, barFocus, modalFocus),
            onBarFocus = { barFocused = it },
            onDragging = { dragging = it },
            onTap = {
                controller.input()
                if (shown && !pinned) controls.hide() else controls.show()
            },
            onDoubleTap = { fraction ->
                controller.input()
                doubleTapSeek(fraction)?.let(seekBy) ?: controls.show()
            },
            onSeekTo = { ms ->
                controller.input()
                controller.seekTo(ms)
                controls.show()
            },
            onSeekBy = { seconds ->
                controller.input()
                seekBy(seconds)
                controls.show()
            },
            onTogglePause = {
                controller.input()
                controller.togglePause()
                controls.show()
            },
            onNext = controller::nextEpisode,
            onPlayAgain = controller::playAgain,
            onResume = controller::resume,
            onCycleAspect = {
                onCycleAspect()
                controls.show()
            },
            onToggleFullscreen = if (isTv) null else onToggleFullscreen,
            onBack = onBack,
            modifier = modifier,
        )
    }

    if (isTv || immersive) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.Black)
                .then(if (isTv) tvKeys else Modifier)
                .focusRequester(screenFocus)
                .focusable(),
        ) {
            stage(Modifier.fillMaxSize(), false)
        }
    } else {
        PortraitLayout(
            state = state,
            onNext = controller::nextEpisode,
            stage = { stage(it, true) },
        )
    }
}

private class StageFocus(val play: FocusRequester, val bar: FocusRequester, val modal: FocusRequester)

/** The picture with the controls, spinner, end card and session overlay over it. */
@Composable
private fun PlayerStage(
    state: OnDemandPlayerState,
    player: Player,
    isTv: Boolean,
    compact: Boolean,
    immersive: Boolean,
    shown: Boolean,
    loading: Boolean,
    playWhenReady: Boolean,
    positionMs: Long,
    durationMs: Long,
    aspect: AspectMode,
    flash: Pair<String, Int>?,
    focus: StageFocus,
    onBarFocus: (Boolean) -> Unit,
    onDragging: (Boolean) -> Unit,
    onTap: () -> Unit,
    onDoubleTap: (Float) -> Unit,
    onSeekTo: (Long) -> Unit,
    onSeekBy: (Int) -> Unit,
    onTogglePause: () -> Unit,
    onNext: () -> Unit,
    onPlayAgain: () -> Unit,
    onResume: () -> Unit,
    onCycleAspect: () -> Unit,
    onToggleFullscreen: (() -> Unit)?,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val tap by rememberUpdatedState(onTap)
    val doubleTap by rememberUpdatedState(onDoubleTap)
    BoxWithConstraints(
        modifier = modifier
            .background(Color.Black)
            .pointerInput(Unit) {
                detectTapGestures(
                    onTap = { tap() },
                    onDoubleTap = { offset -> doubleTap(offset.x / size.width) },
                )
            },
    ) {
        val endCard = state.endCard
        // The end card shrinks the last frame into a corner.
        val surface = if (endCard != null && !compact) {
            Modifier
                .align(Alignment.TopEnd)
                .padding(top = maxHeight * 0.08f, end = maxWidth * 0.04f)
                .width(maxWidth * 0.34f)
                .aspectRatio(16f / 9f)
                .clip(RoundedCornerShape(6.dp))
        } else {
            Modifier.fillMaxSize()
        }
        if (endCard != null) Box(Modifier.fillMaxSize().background(EndCardBackground))
        if (endCard == null || !compact) VideoSurface(player = player, aspect = aspect, modifier = surface)

        if (loading && state.overlay == null && endCard == null) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center), color = Color.White)
        }

        flash?.let { (text, seconds) ->
            Text(
                text = text,
                color = Color.White,
                fontSize = 18.sp,
                modifier = Modifier
                    .align(if (seconds < 0) Alignment.CenterStart else Alignment.CenterEnd)
                    .padding(horizontal = 48.dp)
                    .clip(RoundedCornerShape(20.dp))
                    .background(Color(0x99000000))
                    .padding(horizontal = 14.dp, vertical = 6.dp),
            )
        }

        AnimatedVisibility(visible = shown, enter = fadeIn(), exit = fadeOut(), modifier = Modifier.fillMaxSize()) {
            ControlsOverlay(
                state = state,
                isTv = isTv,
                compact = compact,
                immersive = immersive,
                loading = loading,
                playWhenReady = playWhenReady,
                positionMs = positionMs,
                durationMs = durationMs,
                aspect = aspect,
                focus = focus,
                onBarFocus = onBarFocus,
                onDragging = onDragging,
                onSeekTo = onSeekTo,
                onSeekBy = onSeekBy,
                onTogglePause = onTogglePause,
                onNext = onNext,
                onCycleAspect = onCycleAspect,
                onToggleFullscreen = onToggleFullscreen,
                onBack = onBack,
            )
        }

        if (endCard != null) {
            EndCardView(
                state = state,
                card = endCard,
                compact = compact,
                focus = focus.modal,
                onNext = onNext,
                onPlayAgain = onPlayAgain,
                onSeekBack = { onSeekBy(-10) },
                onBack = onBack,
            )
        }

        state.overlay?.let { overlay ->
            SessionOverlayView(overlay, state.starting, focus.modal, onResume, onBack)
        }
    }
}

@Composable
private fun ControlsOverlay(
    state: OnDemandPlayerState,
    isTv: Boolean,
    compact: Boolean,
    immersive: Boolean,
    loading: Boolean,
    playWhenReady: Boolean,
    positionMs: Long,
    durationMs: Long,
    aspect: AspectMode,
    focus: StageFocus,
    onBarFocus: (Boolean) -> Unit,
    onDragging: (Boolean) -> Unit,
    onSeekTo: (Long) -> Unit,
    onSeekBy: (Int) -> Unit,
    onTogglePause: () -> Unit,
    onNext: () -> Unit,
    onCycleAspect: () -> Unit,
    onToggleFullscreen: (() -> Unit)?,
    onBack: () -> Unit,
) {
    val pauseLabel = if (playWhenReady) "❚❚" else "▶"
    val edge = if (immersive && !isTv) {
        Modifier.windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))
    } else {
        Modifier
    }
    Box(modifier = Modifier.fillMaxSize().background(Color(0x55000000)).then(edge)) {
        // Top: ‹ Back (not on TV, where the remote's Back does it) and the title.
        Row(
            modifier = Modifier.align(Alignment.TopStart).fillMaxWidth().padding(if (compact) 8.dp else 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (!isTv) ControlButton("‹", onBack)
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = state.choice.title,
                    color = Color.White,
                    fontSize = if (compact) 15.sp else 20.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                (state.choice.subtitle ?: state.facts)?.let {
                    Text(text = it, color = MutedText, fontSize = if (compact) 12.sp else 14.sp, maxLines = 1)
                }
            }
        }

        // Centre (phone, landscape): ⟲10 ▶/❚❚ 10⟳. TV keeps them in the bottom row,
        // so ↑ from ▶/❚❚ reaches the bar.
        if (!isTv && !compact && !loading) {
            Row(
                modifier = Modifier.align(Alignment.Center),
                horizontalArrangement = Arrangement.spacedBy(36.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RoundButton("⟲10", { onSeekBy(-10) }, 52.dp)
                RoundButton(pauseLabel, onTogglePause, 68.dp, focus.play)
                RoundButton("10⟳", { onSeekBy(10) }, 52.dp)
            }
        }

        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .padding(horizontal = if (compact) 8.dp else 20.dp, vertical = if (compact) 6.dp else 16.dp),
            verticalArrangement = Arrangement.spacedBy(if (compact) 4.dp else 10.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (compact) ControlButton(pauseLabel, onTogglePause)
                Text(clock((positionMs / 1000).toInt()), color = Color.White, fontSize = 12.sp)
                SeekBar(
                    positionMs = positionMs,
                    durationMs = durationMs,
                    onSeekTo = onSeekTo,
                    onDragging = onDragging,
                    focusRequester = focus.bar,
                    onFocus = onBarFocus,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    "−" + clock(((durationMs - positionMs).coerceAtLeast(0) / 1000).toInt()),
                    color = Color.White,
                    fontSize = 12.sp,
                )
                if (compact) onToggleFullscreen?.let { ControlButton("⛶", it) }
            }
            if (!compact) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (isTv) {
                        ControlButton("⟲ 10", { onSeekBy(-10) })
                        ControlButton(pauseLabel, onTogglePause, focus.play)
                        ControlButton("10 ⟳", { onSeekBy(10) })
                    }
                    if (state.next != null) ControlButton("⏭ Next Episode", onNext)
                    Spacer(Modifier.weight(1f))
                    ControlButton("Aspect: ${aspect.label}", onCycleAspect)
                    onToggleFullscreen?.let { ControlButton(if (immersive) "Exit full screen" else "⛶ Full screen", it) }
                }
            }
        }
    }
}

/**
 * The seek bar: tap or drag (with a time bubble; the seek happens on release). On TV
 * it takes focus and the screen's key handler seeks while it has it.
 */
@Composable
private fun SeekBar(
    positionMs: Long,
    durationMs: Long,
    onSeekTo: (Long) -> Unit,
    onDragging: (Boolean) -> Unit,
    focusRequester: FocusRequester,
    onFocus: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    var dragMs by remember { mutableStateOf<Long?>(null) }
    var focused by remember { mutableStateOf(false) }
    val duration by rememberUpdatedState(durationMs)
    val seek by rememberUpdatedState(onSeekTo)
    val shown = dragMs ?: positionMs
    val fraction = if (durationMs > 0) (shown.toFloat() / durationMs).coerceIn(0f, 1f) else 0f
    val density = LocalDensity.current

    BoxWithConstraints(
        modifier = modifier
            .height(28.dp)
            .focusRequester(focusRequester)
            .onFocusChanged {
                focused = it.isFocused
                onFocus(it.isFocused)
            }
            .focusable()
            .pointerInput(Unit) {
                detectTapGestures { offset ->
                    if (duration > 0) seek((offset.x / size.width * duration).toLong())
                }
            }
            .pointerInput(Unit) {
                fun at(x: Float) = (x / size.width).coerceIn(0f, 1f) * duration
                detectHorizontalDragGestures(
                    onDragStart = { offset ->
                        dragMs = at(offset.x).toLong()
                        onDragging(true)
                    },
                    onHorizontalDrag = { change, _ -> dragMs = at(change.position.x).toLong() },
                    onDragEnd = {
                        dragMs?.let(seek)
                        dragMs = null
                        onDragging(false)
                    },
                    onDragCancel = {
                        dragMs = null
                        onDragging(false)
                    },
                )
            },
        contentAlignment = Alignment.CenterStart,
    ) {
        val track = if (focused) 6.dp else 4.dp
        Box(Modifier.fillMaxWidth().height(track).clip(RoundedCornerShape(3.dp)).background(Color(0x55FFFFFF)))
        Box(
            Modifier
                .fillMaxWidth(fraction)
                .height(track)
                .clip(RoundedCornerShape(3.dp))
                .background(if (focused) FocusAccent else Color.White),
        )
        val thumb = if (focused || dragMs != null) 16.dp else 12.dp
        val x = with(density) { (maxWidth.toPx() * fraction).roundToInt() - (thumb.toPx() / 2).roundToInt() }
        Box(
            Modifier
                .offset { androidx.compose.ui.unit.IntOffset(x, 0) }
                .size(thumb)
                .clip(CircleShape)
                .background(if (focused) FocusAccent else Color.White),
        )
        dragMs?.let { ms ->
            Text(
                text = clock((ms / 1000).toInt()),
                color = Color.White,
                fontSize = 12.sp,
                modifier = Modifier
                    .offset { androidx.compose.ui.unit.IntOffset(x - 24.dp.roundToPx(), (-26).dp.roundToPx()) }
                    .clip(RoundedCornerShape(6.dp))
                    .background(Color(0xCC000000))
                    .padding(horizontal = 6.dp, vertical = 2.dp),
            )
        }
    }
}

/**
 * B's end card: the next Episode with its countdown, "Still watching?", or ✓ Watched
 * (a Movie or the last Episode). ← past the first button seeks back into the picture.
 */
@Composable
private fun EndCardView(
    state: OnDemandPlayerState,
    card: EndCard,
    compact: Boolean,
    focus: FocusRequester,
    onNext: () -> Unit,
    onPlayAgain: () -> Unit,
    onSeekBack: () -> Unit,
    onBack: () -> Unit,
) {
    val focusManager = LocalFocusManager.current
    val left = state.endSecondsLeft ?: 0
    val nextCode = state.next?.subtitle?.substringBefore(" · ")
    Box(
        modifier = Modifier
            .fillMaxSize()
            .onKeyEvent { event ->
                if (event.type == KeyEventType.KeyDown && event.key == Key.DirectionLeft &&
                    !focusManager.moveFocus(FocusDirection.Left)
                ) {
                    onSeekBack()
                }
                event.key == Key.DirectionLeft
            },
    ) {
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth(if (compact) 1f else 0.58f)
                .padding(if (compact) 14.dp else 40.dp),
            verticalArrangement = Arrangement.spacedBy(if (compact) 4.dp else 8.dp),
        ) {
            when (card) {
                EndCard.Next -> {
                    Kicker("NEXT EPISODE · in $left s")
                    Headline(state.next?.subtitle ?: state.next?.title.orEmpty(), compact)
                    state.nextSeasonNumber?.let { Text("Season $it", color = MutedText, fontSize = 13.sp) }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        PrimaryButton("▶ Play now", onNext, focus)
                        SecondaryButton("Back to Episodes", onBack)
                    }
                }
                EndCard.StillWatching -> {
                    Headline("Still watching ${state.choice.title}?", compact)
                    Text("$AUTOPLAY_LIMIT Episodes have played in a row with no input.", color = MutedText, fontSize = 13.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        PrimaryButton(listOfNotNull("▶ Continue with", nextCode).joinToString(" "), onNext, focus)
                        SecondaryButton("Back", onBack)
                    }
                }
                EndCard.Watched -> {
                    Kicker("✓ Watched", color = WatchedGreen)
                    val isEpisode = state.choice.key is OnDemandKey.Episode
                    Headline(
                        if (isEpisode) {
                            listOfNotNull(state.choice.title, state.seasonNumber?.let { "Season $it finished" }).joinToString(" · ")
                        } else {
                            state.choice.title
                        },
                        compact,
                    )
                    Text("Back to details in $left s", color = MutedText, fontSize = 13.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        SecondaryButton("↺ Play again", onPlayAgain)
                        PrimaryButton("Back to details", onBack, focus)
                    }
                }
            }
        }
    }
}

/** 410 `evicted`/`stopped`, a failed restart (503 `busy`) or another failure, with Resume / Try again and Back. */
@Composable
private fun SessionOverlayView(
    overlay: SessionOverlay,
    starting: Boolean,
    focus: FocusRequester,
    onResume: () -> Unit,
    onBack: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize().background(Color(0xF20A0E14)), contentAlignment = Alignment.Center) {
        Column(
            modifier = Modifier.padding(24.dp).fillMaxWidth(0.8f),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(overlay.message, color = Color.White, fontSize = 16.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PrimaryButton(overlay.action, onResume, focus, enabled = !starting)
                SecondaryButton("Back", onBack)
            }
        }
    }
}

/** Phone portrait: the video on top, then the title, ⏭ Next Episode and the description. */
@Composable
private fun PortraitLayout(
    state: OnDemandPlayerState,
    onNext: () -> Unit,
    stage: @Composable (Modifier) -> Unit,
) {
    val palette = pickerPalette()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background)
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal)),
    ) {
        stage(Modifier.fillMaxWidth().aspectRatio(16f / 9f))
        Column(
            modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(state.choice.title, color = palette.onSurface, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
            (state.choice.subtitle ?: state.facts)?.let { Text(it, color = palette.muted, fontSize = 14.sp) }
            state.next?.let { next ->
                Button(onClick = onNext, modifier = Modifier.fillMaxWidth()) {
                    Text(
                        listOfNotNull("⏭ Next Episode", next.subtitle?.replaceFirst(Regex("^S\\d+ "), "")).joinToString(" · "),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            state.description?.takeIf { it.isNotBlank() }?.let { Text(it, color = palette.muted, fontSize = 14.sp) }
        }
    }
}

@Composable
private fun ControlButton(text: String, onClick: () -> Unit, focusRequester: FocusRequester? = null) {
    OutlinedButton(
        onClick = onClick,
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
        modifier = Modifier
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .focusRing(RoundedCornerShape(50)),
    ) {
        Text(text = text, color = Color.White, fontSize = 13.sp, maxLines = 1, softWrap = false)
    }
}

@Composable
private fun RoundButton(text: String, onClick: () -> Unit, size: Dp, focusRequester: FocusRequester? = null) {
    Box(
        modifier = Modifier
            .size(size)
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .focusRing(CircleShape)
            .clip(CircleShape)
            .background(Color(0x88000000))
            .pointerInput(Unit) { detectTapGestures { onClick() } },
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = Color.White, fontSize = if (size > 60.dp) 26.sp else 15.sp)
    }
}

@Composable
private fun PrimaryButton(text: String, onClick: () -> Unit, focusRequester: FocusRequester? = null, enabled: Boolean = true) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .focusRing(RoundedCornerShape(50)),
    ) {
        Text(text, maxLines = 1, softWrap = false)
    }
}

@Composable
private fun SecondaryButton(text: String, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.focusRing(RoundedCornerShape(50))) {
        Text(text, color = Color.White, maxLines = 1, softWrap = false)
    }
}

@Composable
private fun Kicker(text: String, color: Color = MutedText) {
    Text(text, color = color, fontSize = 12.sp, letterSpacing = 1.sp, fontWeight = FontWeight.Medium)
}

@Composable
private fun Headline(text: String, compact: Boolean) {
    Text(
        text,
        color = Color.White,
        fontSize = if (compact) 18.sp else 26.sp,
        fontWeight = FontWeight.SemiBold,
        maxLines = 2,
        overflow = TextOverflow.Ellipsis,
    )
}

private val MutedText = Color(0xFFB4BCC8)
private val FocusAccent = Color(0xFF7FB2FF)
private val WatchedGreen = Color(0xFF7DD3A0)
private val EndCardBackground = Color(0xFF08080E)

/** The title a key belongs to: a Movie itself, or an Episode's Series. */
val OnDemandKey.titleId: String
    get() = when (this) {
        is OnDemandKey.Movie -> id
        is OnDemandKey.Episode -> seriesId
    }
