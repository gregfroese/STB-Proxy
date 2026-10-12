package cc.selfhosters.stbproxy.ui.player

import android.content.res.Configuration
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberBottomSheetScaffoldState
import androidx.compose.material3.BottomSheetScaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.ImmersiveEffect
import cc.selfhosters.stbproxy.ui.common.KeepScreenOnEffect
import cc.selfhosters.stbproxy.ui.common.VideoSurface
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.common.rememberAutoHideControls
import kotlin.math.roundToInt

/**
 * The split player screen (spec 2.6): video plus a persistent now/next sidebar.
 * TV = video pane + right-hand sidebar; phone = video with the sidebar as a
 * bottom sheet, or full-screen in landscape. On-screen controls fade after a
 * few seconds and return on a tap or a remote key.
 */
@Composable
fun PlayerScreen(
    portal: String,
    channelId: String,
    launchBlock: String,
    onOpenSettings: () -> Unit,
    onOpenMultiview: () -> Unit,
    viewModel: PlayerViewModel = viewModel(
        factory = PlayerViewModel.factory(
            apiClient = LocalAppContainer.current.apiClient,
            epgRepository = LocalAppContainer.current.epgRepository,
            session = LocalAppContainer.current.sessionController,
            portal = portal,
            channelId = channelId,
            launchBlock = launchBlock,
        ),
    ),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val container = LocalAppContainer.current
    val context = LocalContext.current
    val configuration = LocalConfiguration.current
    val isTv = configuration.uiMode and Configuration.UI_MODE_TYPE_MASK ==
        Configuration.UI_MODE_TYPE_TELEVISION
    val isLandscape = configuration.orientation == Configuration.ORIENTATION_LANDSCAPE

    val player = remember { buildStreamPlayer(context, container.playerDataSourceFactory) }
    DisposableEffect(player) {
        onDispose { player.release() }
    }

    var playing by remember { mutableStateOf(false) }
    var buffering by remember { mutableStateOf(false) }
    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                buffering = playbackState == Player.STATE_BUFFERING
                playing = playbackState == Player.STATE_READY
            }

            override fun onIsPlayingChanged(isPlaying: Boolean) {
                playing = isPlaying
            }

            override fun onPlayerError(error: PlaybackException) {
                viewModel.onPlayerError(classifyPlaybackException(error))
            }
        }
        player.addListener(listener)
        onDispose { player.removeListener(listener) }
    }

    LaunchedEffect(state.streamUrl, state.prepareNonce) {
        val url = state.streamUrl ?: return@LaunchedEffect
        player.setMediaItem(mediaItemFor(url))
        player.prepare()
        player.playWhenReady = true
    }

    LifecycleEventEffect(Lifecycle.Event.ON_START) { viewModel.onForeground() }

    KeepScreenOnEffect()
    var immersive by remember { mutableStateOf(shouldAutoFullscreen(isTv, isLandscape)) }
    var guideVisible by remember { mutableStateOf(false) }
    LaunchedEffect(isTv, isLandscape) {
        if (!isTv) immersive = shouldAutoFullscreen(isTv, isLandscape)
    }
    ImmersiveEffect(enabled = immersive)

    val controls = rememberAutoHideControls()

    // Back closes the guide first; a second Back leaves the player.
    BackHandler(enabled = guideVisible) { guideVisible = false }

    // Compose for TV needs something focused for the D-pad. Focus the first action
    // button while the controls are up, and the screen itself once they fade, so any
    // key still reaches the app and brings the controls back.
    val screenFocus = remember { FocusRequester() }
    val actionFocus = remember { FocusRequester() }
    LaunchedEffect(isTv, controls.visible, guideVisible) {
        if (!isTv || guideVisible) return@LaunchedEffect
        runCatching {
            if (controls.visible) actionFocus.requestFocus() else screenFocus.requestFocus()
        }
    }

    val interactions = Modifier
        .onPreviewKeyEvent { event ->
            if (event.type != KeyEventType.KeyDown) {
                false
            } else {
                controls.show()
                // While the guide is open the D-pad navigates its list instead of zapping.
                if (guideVisible) {
                    false
                } else {
                    when (event.key) {
                        Key.DirectionUp, Key.ChannelUp -> {
                            viewModel.zap(1); true
                        }
                        Key.DirectionDown, Key.ChannelDown -> {
                            viewModel.zap(-1); true
                        }
                        else -> false
                    }
                }
            }
        }
        .pointerInput(Unit) { detectTapGestures { controls.show() } }

    if (isTv) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.Black)
                .then(interactions)
                .focusRequester(screenFocus)
                .focusable(),
        ) {
            VideoPane(
                state = state,
                player = player,
                playing = playing,
                buffering = buffering,
                controlsVisible = controls.visible,
                onOpenSettings = onOpenSettings,
                onRetry = viewModel::retry,
                onWaitForTuner = viewModel::waitForTuner,
                onTryNext = { viewModel.zap(1) },
                onOpenMultiview = onOpenMultiview,
                onToggleFullscreen = null,
                immersive = false,
                onToggleGuide = { guideVisible = !guideVisible },
                guideVisible = guideVisible,
                multiviewFocusRequester = actionFocus,
                modifier = Modifier.fillMaxSize(),
            )
            if (guideVisible) {
                GuideOverlay(
                    state = state,
                    onSelectChannel = viewModel::selectChannel,
                    onClose = { guideVisible = false },
                    modifier = Modifier
                        .align(Alignment.CenterEnd)
                        .fillMaxHeight()
                        .width(SidebarWidth)
                        .padding(top = 56.dp),
                )
            }
        }
    } else if (immersive) {
        Box(modifier = Modifier.fillMaxSize().background(Color.Black).then(interactions)) {
            VideoPane(
                state = state,
                player = player,
                playing = playing,
                buffering = buffering,
                controlsVisible = controls.visible,
                onOpenSettings = onOpenSettings,
                onRetry = viewModel::retry,
                onWaitForTuner = viewModel::waitForTuner,
                onTryNext = { viewModel.zap(1) },
                onOpenMultiview = onOpenMultiview,
                onToggleFullscreen = { immersive = false },
                immersive = true,
                onToggleGuide = { guideVisible = !guideVisible },
                guideVisible = guideVisible,
                modifier = Modifier.fillMaxSize(),
            )
            if (guideVisible) {
                GuideOverlay(
                    state = state,
                    onSelectChannel = viewModel::selectChannel,
                    onClose = { guideVisible = false },
                    modifier = Modifier
                        .align(Alignment.CenterEnd)
                        .fillMaxHeight()
                        .width(320.dp)
                        .padding(top = 56.dp),
                )
            }
        }
    } else {
        PhonePlayerLayout(
            state = state,
            player = player,
            playing = playing,
            buffering = buffering,
            controlsVisible = controls.visible,
            onOpenSettings = onOpenSettings,
            onRetry = viewModel::retry,
            onWaitForTuner = viewModel::waitForTuner,
            onTryNext = { viewModel.zap(1) },
            onSelectChannel = viewModel::selectChannel,
            onOpenMultiview = onOpenMultiview,
            onToggleFullscreen = { immersive = true },
            modifier = interactions,
        )
    }
}

/**
 * The full-screen now/next panel. Dismissed with its ✕ button, or by dragging
 * it off to the right.
 */
@Composable
private fun GuideOverlay(
    state: PlayerUiState,
    onSelectChannel: (Int) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var offsetX by remember { mutableFloatStateOf(0f) }
    // A remote lands on the ✕ first, then the D-pad walks the channel list.
    val closeFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { closeFocus.requestFocus() } }
    Box(
        modifier = modifier
            .offset { IntOffset(offsetX.roundToInt(), 0) }
            .draggable(
                orientation = Orientation.Horizontal,
                state = rememberDraggableState { delta ->
                    offsetX = (offsetX + delta).coerceAtLeast(0f)
                },
                onDragStopped = { if (offsetX > 120f) onClose() else offsetX = 0f },
            ),
    ) {
        PlayerSidebar(
            state = state,
            isTv = false,
            onSelectChannel = onSelectChannel,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(8.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(Color(0xCC000000))
                .focusRing(RoundedCornerShape(8.dp))
                .focusRequester(closeFocus)
                .clickable(onClick = onClose)
                .padding(horizontal = 12.dp, vertical = 6.dp),
        ) {
            Text(text = "✕ Close", color = Color.White, fontSize = 12.sp)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PhonePlayerLayout(
    state: PlayerUiState,
    player: Player,
    playing: Boolean,
    buffering: Boolean,
    controlsVisible: Boolean,
    onOpenSettings: () -> Unit,
    onRetry: () -> Unit,
    onWaitForTuner: () -> Unit,
    onTryNext: () -> Unit,
    onSelectChannel: (Int) -> Unit,
    onOpenMultiview: () -> Unit,
    onToggleFullscreen: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val sheetPeek = 300.dp
    val sheetState = rememberBottomSheetScaffoldState()
    BottomSheetScaffold(
        scaffoldState = sheetState,
        sheetPeekHeight = sheetPeek,
        sheetContainerColor = MaterialTheme.colorScheme.surface,
        sheetContent = {
            PlayerSidebar(
                state = state,
                isTv = false,
                onSelectChannel = onSelectChannel,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        modifier = modifier,
    ) { padding ->
        VideoPane(
            state = state,
            player = player,
            playing = playing,
            buffering = buffering,
            controlsVisible = controlsVisible,
            onOpenSettings = onOpenSettings,
            onRetry = onRetry,
            onWaitForTuner = onWaitForTuner,
            onTryNext = onTryNext,
            onOpenMultiview = onOpenMultiview,
            onToggleFullscreen = onToggleFullscreen,
            immersive = false,
            onToggleGuide = null,
            guideVisible = false,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(bottom = sheetPeek),
        )
    }
}

@Composable
private fun VideoPane(
    state: PlayerUiState,
    player: Player,
    playing: Boolean,
    buffering: Boolean,
    controlsVisible: Boolean,
    onOpenSettings: () -> Unit,
    onRetry: () -> Unit,
    onWaitForTuner: () -> Unit,
    onTryNext: () -> Unit,
    onOpenMultiview: () -> Unit,
    onToggleFullscreen: (() -> Unit)?,
    immersive: Boolean,
    onToggleGuide: (() -> Unit)?,
    guideVisible: Boolean,
    multiviewFocusRequester: FocusRequester? = null,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier.background(Color.Black)) {
        if (state.streamUrl != null) {
            VideoSurface(player = player, modifier = Modifier.fillMaxSize())
        }

        if (state.loading || state.lineupError != null) {
            Overlay {
                if (state.loading) {
                    CircularProgressIndicator()
                } else {
                    ErrorCopy(
                        title = "Channel unavailable",
                        body = state.lineupError.orEmpty(),
                    )
                    Button(onClick = onRetry) { Text("Retry") }
                }
            }
        } else if (state.waitingForTuner) {
            Overlay {
                ErrorCopy(
                    title = "Waiting for a free tuner",
                    body = "Every tuner is in use. This will retry automatically.",
                )
                Button(onClick = onRetry) { Text("Retry now") }
            }
        } else if (state.playbackError != null) {
            Overlay {
                ErrorBody(
                    error = state.playbackError!!,
                    onRetry = onRetry,
                    onOpenSettings = onOpenSettings,
                    onWaitForTuner = onWaitForTuner,
                    onTryNext = onTryNext,
                )
            }
        } else {
            AnimatedVisibility(
                visible = controlsVisible,
                enter = fadeIn(),
                exit = fadeOut(),
                modifier = Modifier.align(Alignment.TopStart),
            ) {
                LiveBadge(playing = playing, buffering = buffering, block = state.launchBlock)
            }
        }

        AnimatedVisibility(
            visible = controlsVisible,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.TopEnd),
        ) {
            Row(
                modifier = Modifier.padding(10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OverlayButton("Multiview", onOpenMultiview, focusRequester = multiviewFocusRequester)
                onToggleGuide?.let { OverlayButton(if (guideVisible) "Hide guide" else "Guide", it) }
                onToggleFullscreen?.let {
                    OverlayButton(if (immersive) "Exit full" else "Full screen", it)
                }
            }
        }
    }
}

@Composable
private fun OverlayButton(
    text: String,
    onClick: () -> Unit,
    focusRequester: FocusRequester? = null,
) {
    OutlinedButton(
        onClick = onClick,
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
        modifier = Modifier
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .focusRing(RoundedCornerShape(50)),
    ) {
        Text(text = text, fontSize = 12.sp, maxLines = 1, softWrap = false)
    }
}

@Composable
private fun ErrorBody(
    error: PlaybackError,
    onRetry: () -> Unit,
    onOpenSettings: () -> Unit,
    onWaitForTuner: () -> Unit,
    onTryNext: () -> Unit,
) {
    when (error) {
        PlaybackError.AllTunersBusy -> {
            ErrorCopy(
                title = "All tuners are busy",
                body = "STB-Proxy has no free tuner right now. Every tuner is in use by another viewer.",
            )
            ActionRow {
                Button(onClick = onRetry) { Text("Retry") }
                OutlinedButton(onClick = onWaitForTuner) { Text("Wait for a free tuner") }
                OutlinedButton(onClick = onTryNext) { Text("Try next channel") }
            }
        }
        PlaybackError.Unreachable -> {
            ErrorCopy(
                title = "Stream unreachable",
                body = "Couldn't connect to the proxy. Check the base URL and that you're on the LAN.",
            )
            ActionRow {
                Button(onClick = onRetry) { Text("Retry") }
                OutlinedButton(onClick = onOpenSettings) { Text("Open Settings") }
                OutlinedButton(onClick = onTryNext) { Text("Try next channel") }
            }
        }
        is PlaybackError.RedirectingToPortal -> {
            ErrorCopy(
                title = "Redirecting to portal",
                body = "This proxy answered a redirect the player can't follow. The target is shown for diagnostics.",
            )
            error.target?.let { target ->
                Text(
                    text = target,
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 12.sp,
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(Color(0x66000000))
                        .padding(horizontal = 8.dp, vertical = 4.dp),
                )
            }
            ActionRow {
                Button(onClick = onRetry) { Text("Retry") }
                OutlinedButton(onClick = onTryNext) { Text("Try next channel") }
            }
        }
    }
}

@Composable
private fun ActionRow(content: @Composable () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) { content() }
}

@Composable
private fun ErrorCopy(title: String, body: String) {
    Text(
        text = title,
        color = MaterialTheme.colorScheme.onSurface,
        style = MaterialTheme.typography.titleMedium,
    )
    Text(
        text = body,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodySmall,
    )
}

@Composable
private fun Overlay(content: @Composable () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xF20A0E14)),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier.padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            content()
        }
    }
}

@Composable
private fun LiveBadge(playing: Boolean, buffering: Boolean, block: String) {
    Row(
        modifier = Modifier
            .padding(14.dp)
            .clip(RoundedCornerShape(20.dp))
            .background(Color(0x88000000))
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        val label = when {
            buffering -> "BUFFERING"
            playing -> "LIVE"
            else -> "CONNECTING"
        }
        Text(text = label, color = Color.White, fontSize = 11.sp)
        Text(text = "· $block", color = Color(0xFF9AA7B4), fontSize = 11.sp)
    }
}
