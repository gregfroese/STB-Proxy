package cc.selfhosters.stbproxy.ui.multiview

import android.content.res.Configuration
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import cc.selfhosters.stbproxy.R
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.ZapSwipeHint
import cc.selfhosters.stbproxy.ui.common.rememberZapSwipe
import cc.selfhosters.stbproxy.ui.common.ImmersiveEffect
import cc.selfhosters.stbproxy.ui.common.KeepScreenOnEffect
import cc.selfhosters.stbproxy.ui.common.TvFocusColor
import cc.selfhosters.stbproxy.ui.common.VideoSurface
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.common.rememberAutoHideControls
import cc.selfhosters.stbproxy.ui.picker.ChannelPickerOverlay
import cc.selfhosters.stbproxy.ui.player.PlaybackError
import cc.selfhosters.stbproxy.ui.player.buildStreamPlayer
import cc.selfhosters.stbproxy.ui.player.classifyPlaybackException
import cc.selfhosters.stbproxy.ui.player.mediaItemFor
import cc.selfhosters.stbproxy.ui.player.zapWithin
import androidx.compose.ui.res.stringResource

/**
 * The Multiview grid (spec 2.7). TV a 2x2; phone landscape a 1x2; phone portrait
 * the two Tiles stacked. Each Tile is its own ExoPlayer fed
 * `/play/<portal>/<channelId>`, bounded by the proxy's tuner budget. Controls
 * fade after a few seconds and return on a tap or remote key; the phone has a
 * full-screen toggle.
 */
@Composable
fun MultiviewScreen(
    onBack: () -> Unit,
    viewModel: MultiviewViewModel = viewModel(
        factory = MultiviewViewModel.factory(
            LocalAppContainer.current.apiClient,
            LocalAppContainer.current.sessionController,
            LocalAppContainer.current.viewerPreferences,
        ),
    ),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val configuration = LocalConfiguration.current
    val isTv = configuration.uiMode and Configuration.UI_MODE_TYPE_MASK ==
        Configuration.UI_MODE_TYPE_TELEVISION
    val landscape = configuration.orientation == Configuration.ORIENTATION_LANDSCAPE

    var immersive by remember { mutableStateOf(isTv || landscape) }
    LaunchedEffect(isTv, landscape) {
        if (!isTv) immersive = landscape
    }
    ImmersiveEffect(enabled = immersive)
    KeepScreenOnEffect()

    val controls = rememberAutoHideControls()
    // TV: selecting a Tile opens a screen-level action bar for it, and the D-pad is driven
    // here rather than by Compose focus (which is unreliable across nested Tiles).
    var actionSlot by remember { mutableStateOf<Int?>(null) }
    var barIndex by remember { mutableIntStateOf(0) }
    // TV top bar (Back / Grid / Refresh) focus, reached by pressing Up on the top row.
    var topBarIndex by remember { mutableStateOf<Int?>(null) }
    BackHandler(enabled = actionSlot != null) { actionSlot = null }

    fun activateTopBar(index: Int) {
        when (index) {
            0 -> onBack()
            1 -> viewModel.cycleLayout()
            2 -> viewModel.load()
        }
    }

    fun selectTile(slot: Int) {
        val tile = state.tiles.firstOrNull { it.slot == slot } ?: return
        when {
            tile.channel == null -> viewModel.openPicker(slot)
            state.swapFrom != null && state.swapFrom != slot -> viewModel.onTileClick(slot)
            else -> {
                viewModel.onTileClick(slot)
                actionSlot = slot
                barIndex = 0
            }
        }
    }

    fun activateBar(slot: Int, index: Int) {
        when (index) {
            0 -> viewModel.openPicker(slot)
            1 -> viewModel.swap(slot)
            2 -> viewModel.setAudio(slot)
            3 -> viewModel.remove(slot)
        }
        actionSlot = null
    }

    fun moveTile(dx: Int, dy: Int) {
        viewModel.setFocus(
            moveFocusSlot(state.focusSlot, state.layout.columns, state.layout.rows, dx, dy),
        )
    }

    // Ticket 10: a phone vertical swipe zaps the audio tile (up = next), through the
    // same assign path as the picker overlay, with a hint naming where it lands.
    val audioChannel = state.audioSlot?.let { slot -> state.tiles.firstOrNull { it.slot == slot }?.channel }
    val swipe = rememberZapSwipe(
        onZap = if (isTv) null else { delta ->
            if (state.pickFor == null) state.audioSlot?.let { viewModel.zapTile(it, delta) }
        },
        targetName = { delta -> audioChannel?.let { zapWithin(state.channels, it, delta)?.name } },
    )

    val interactions = Modifier
        .onPreviewKeyEvent { event ->
            if (event.type != KeyEventType.KeyDown) {
                false
            } else {
                controls.show()
                val slot = actionSlot
                if (slot != null) {
                    when (event.key) {
                        Key.DirectionLeft -> {
                            barIndex = (barIndex - 1).coerceAtLeast(0); true
                        }
                        Key.DirectionRight -> {
                            barIndex = (barIndex + 1).coerceAtMost(4); true
                        }
                        Key.Enter, Key.DirectionCenter -> {
                            activateBar(slot, barIndex); true
                        }
                        else -> false
                    }
                } else if (topBarIndex != null) {
                    val i = topBarIndex!!
                    when (event.key) {
                        Key.DirectionLeft -> { topBarIndex = (i - 1).coerceAtLeast(0); true }
                        Key.DirectionRight -> { topBarIndex = (i + 1).coerceAtMost(2); true }
                        Key.Enter, Key.DirectionCenter -> { activateTopBar(i); true }
                        Key.DirectionDown -> { topBarIndex = null; true }
                        else -> false
                    }
                } else {
                    when (event.key) {
                        Key.DirectionLeft -> { moveTile(-1, 0); true }
                        Key.DirectionRight -> { moveTile(1, 0); true }
                        Key.DirectionUp -> {
                            // From the top row, Up reaches the top bar (Back / Grid / Refresh).
                            if (state.focusSlot < state.layout.columns) topBarIndex = 0 else moveTile(0, -1)
                            true
                        }
                        Key.DirectionDown -> { moveTile(0, 1); true }
                        Key.Enter, Key.DirectionCenter -> { selectTile(state.focusSlot); true }
                        // Ticket 10: ChannelUp/Down zap the focused tile's channel; the
                        // arrows stay grid navigation.
                        Key.ChannelUp -> { viewModel.zapTile(state.focusSlot, 1); true }
                        Key.ChannelDown -> { viewModel.zapTile(state.focusSlot, -1); true }
                        else -> false
                    }
                }
            }
        }
        .pointerInput(Unit) { detectTapGestures { controls.show() } }
        .then(swipe.modifier)

    // Keep something focused so the preview key handler above receives the keys.
    val tileFocus = remember { FocusRequester() }
    LaunchedEffect(isTv, state.focusSlot) {
        if (isTv) runCatching { tileFocus.requestFocus() }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .then(if (immersive) Modifier else Modifier.safeDrawingPadding())
            .then(interactions),
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            AnimatedVisibility(visible = controls.visible, enter = fadeIn(), exit = fadeOut()) {
                MultiviewTopBar(
                    state = state,
                    showFullscreen = !isTv,
                    showLayout = isTv,
                    immersive = immersive,
                    highlighted = topBarIndex,
                    onToggleFullscreen = { immersive = !immersive },
                    onCycleLayout = viewModel::cycleLayout,
                    onBack = onBack,
                    onRetry = viewModel::load,
                )
            }

            Box(modifier = Modifier.fillMaxWidth().weight(1f)) {
                when {
                    state.loading -> Centered {
                        CircularProgressIndicator()
                    }
                    state.lineupError != null -> Centered {
                        Label(state.lineupError.orEmpty(), MaterialTheme.colorScheme.onSurfaceVariant)
                        Button(onClick = viewModel::load) { Text("Retry") }
                    }
                    else -> MultiviewGrid(
                        state = state,
                        viewModel = viewModel,
                        isTv = isTv,
                        landscape = landscape,
                        controlsVisible = controls.visible,
                        onInteract = controls::show,
                        onSelectTile = { actionSlot = it },
                        tileFocus = tileFocus,
                    )
                }
            }
        }

        ZapSwipeHint(swipe.hint, modifier = Modifier.align(Alignment.Center))

        if (isTv) {
            actionSlot?.let { slot ->
                MultiviewActionBar(
                    slot = slot,
                    selected = barIndex,
                    isAudio = state.audioSlot == slot,
                    onPick = { viewModel.openPicker(slot); actionSlot = null },
                    onSwap = { viewModel.swap(slot); actionSlot = null },
                    onAudio = { viewModel.setAudio(slot); actionSlot = null },
                    onRemove = { viewModel.remove(slot); actionSlot = null },
                    onClose = { actionSlot = null },
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            }
        }
    }

    state.pickFor?.let { slot ->
        ChannelPickerOverlay(
            title = "Pick channel for Tile ${slot + 1}",
            blocks = state.blocks,
            channels = state.channels,
            groupMode = state.groupMode,
            onSelect = viewModel::pick,
            onDismiss = viewModel::dismissPicker,
        )
    }
}

@Composable
private fun MultiviewGrid(
    state: MultiviewUiState,
    viewModel: MultiviewViewModel,
    isTv: Boolean,
    landscape: Boolean,
    controlsVisible: Boolean,
    onInteract: () -> Unit,
    onSelectTile: (Int) -> Unit,
    tileFocus: FocusRequester?,
) {
    val gap = 8.dp
    when {
        isTv -> Column(
            modifier = Modifier.fillMaxSize().padding(gap),
            verticalArrangement = Arrangement.spacedBy(gap),
        ) {
            state.shownTiles.chunked(state.layout.columns).forEach { rowTiles ->
                Row(
                    modifier = Modifier.fillMaxWidth().weight(1f),
                    horizontalArrangement = Arrangement.spacedBy(gap),
                ) {
                    rowTiles.forEach { tile ->
                        TileCell(
                            tile = tile,
                            state = state,
                            viewModel = viewModel,
                            isTv = isTv,
                            controlsVisible = controlsVisible,
                            onInteract = onInteract,
                            onSelectTile = onSelectTile,
                            focusRequester = if (isTv && tile.slot == state.focusSlot) tileFocus else null,
                            modifier = Modifier.weight(1f).fillMaxHeight(),
                        )
                    }
                }
            }
        }

        landscape -> Row(
            modifier = Modifier.fillMaxSize().padding(gap),
            horizontalArrangement = Arrangement.spacedBy(gap),
        ) {
            state.tiles.take(2).forEach { tile ->
                TileCell(
                    tile = tile,
                    state = state,
                    viewModel = viewModel,
                    isTv = isTv,
                    controlsVisible = controlsVisible,
                    onInteract = onInteract,
                    onSelectTile = onSelectTile,
                    focusRequester = if (isTv && tile.slot == state.focusSlot) tileFocus else null,
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                )
            }
        }

        else -> Column(
            modifier = Modifier.fillMaxSize().padding(gap),
            verticalArrangement = Arrangement.spacedBy(gap),
        ) {
            state.tiles.take(2).forEach { tile ->
                TileCell(
                    tile = tile,
                    state = state,
                    viewModel = viewModel,
                    isTv = isTv,
                    controlsVisible = controlsVisible,
                    onInteract = onInteract,
                    onSelectTile = onSelectTile,
                    focusRequester = if (isTv && tile.slot == state.focusSlot) tileFocus else null,
                    modifier = Modifier.fillMaxWidth().weight(1f),
                )
            }
        }
    }
}

@Composable
private fun TileCell(
    tile: MultiviewTile,
    state: MultiviewUiState,
    viewModel: MultiviewViewModel,
    isTv: Boolean,
    controlsVisible: Boolean,
    onInteract: () -> Unit,
    onSelectTile: (Int) -> Unit,
    focusRequester: FocusRequester? = null,
    modifier: Modifier = Modifier,
) {
    key(tile.slot) {
        val status = tileStatus(tile, state.overBudget, state.errors[tile.slot])
        val isAudio = state.audioSlot == tile.slot
        val armed = state.swapFrom == tile.slot
        val accent = MaterialTheme.colorScheme.primary
        var focused by remember { mutableStateOf(false) }
        // TV: the D-pad-selected Tile (its focus requester is attached) is the highlighted one.
        val highlighted = focusRequester != null
        val ring = focused || highlighted
        val shape = RoundedCornerShape(10.dp)

        Box(
            modifier = modifier
                .clip(shape)
                .background(Color.Black)
                .border(
                    width = if (isAudio || ring) 3.dp else 1.dp,
                    color = when {
                        ring -> TvFocusColor
                        isAudio -> accent
                        else -> MaterialTheme.colorScheme.surfaceVariant
                    },
                    shape = shape,
                )
                .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
                // hasFocus: true while focus is anywhere in this Tile, including its chrome.
                .onFocusChanged { focused = it.hasFocus }
                .clickable {
                    onInteract()
                    when {
                        // Empty Tile: choose a channel.
                        tile.channel == null -> viewModel.openPicker(tile.slot)
                        // A swap is armed elsewhere: complete it.
                        state.swapFrom != null && state.swapFrom != tile.slot ->
                            viewModel.onTileClick(tile.slot)
                        // Otherwise focus the Tile, and (TV) open its action bar.
                        else -> {
                            viewModel.onTileClick(tile.slot)
                            onSelectTile(tile.slot)
                        }
                    }
                },
        ) {
            when (status) {
                TileStatus.Empty -> EmptyTile(onAdd = { viewModel.openPicker(tile.slot) })

                TileStatus.TunerBusy -> BusyTile(
                    used = state.tunersUsed,
                    budget = state.tunerCount,
                    onRetry = { viewModel.retry(tile.slot) },
                    onRemove = { viewModel.remove(tile.slot) },
                )

                is TileStatus.Failed -> FailedTile(
                    error = status.error,
                    onRetry = { viewModel.retry(tile.slot) },
                    onRemove = { viewModel.remove(tile.slot) },
                )

                TileStatus.Live -> TileVideo(
                    url = viewModel.streamUrlFor(tile),
                    prepareNonce = state.prepareNonces[tile.slot] ?: 0,
                    muted = !isAudio,
                    onError = { viewModel.onTileError(tile.slot, it) },
                )
            }

            tile.channel?.let { channel ->
                ChannelTag(channel = channel)
                if (isAudio) AudioBadge(Modifier.align(Alignment.BottomStart))
            }

            // Phone only: the per-Tile chrome (touch). TV uses the screen-level action bar.
            if (!isTv && (controlsVisible || focused) && tile.channel != null) {
                Box(modifier = Modifier.align(Alignment.BottomEnd)) {
                    TileChrome(
                        armed = armed,
                        isAudio = isAudio,
                        onPick = { viewModel.openPicker(tile.slot) },
                        onSwap = { viewModel.swap(tile.slot) },
                        onAudio = { viewModel.setAudio(tile.slot) },
                        onRemove = { viewModel.remove(tile.slot) },
                    )
                }
            }

            if (armed) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .border(3.dp, Color(0xFFFFD34D), shape)
                        .background(Color(0x33000000)),
                    contentAlignment = Alignment.TopCenter,
                ) {
                    Label(
                        "SWAP: tap another Tile",
                        Color(0xFFFFD34D),
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }
        }
    }
}

/** One Tile's ExoPlayer, released when the Tile leaves the grid or the screen. */
@Composable
private fun TileVideo(
    url: String?,
    prepareNonce: Int,
    muted: Boolean,
    onError: (PlaybackError) -> Unit,
) {
    val context = LocalContext.current
    val dataSourceFactory = LocalAppContainer.current.playerDataSourceFactory
    // Several players run at once here, so none of them takes audio focus (they
    // would pause each other); audio is per-tile volume instead.
    val player = remember {
        buildStreamPlayer(context, dataSourceFactory, handleAudioFocus = false)
    }

    DisposableEffect(player) {
        onDispose { player.release() }
    }
    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                onError(classifyPlaybackException(error))
            }
        }
        player.addListener(listener)
        onDispose { player.removeListener(listener) }
    }

    // A progressive-live stream can't resume mid-window; retry re-prepares.
    LaunchedEffect(url, prepareNonce) {
        if (url == null) return@LaunchedEffect
        player.setMediaItem(mediaItemFor(url))
        player.prepare()
        player.playWhenReady = true
    }
    LaunchedEffect(muted) {
        player.volume = if (muted) 0f else 1f
    }

    VideoSurface(player = player, modifier = Modifier.fillMaxSize(), useTextureView = true)
}

@Composable
private fun EmptyTile(onAdd: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .border(1.dp, MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(10.dp))
            .clickable(onClick = onAdd),
        contentAlignment = Alignment.Center,
    ) {
        Label("＋ Add channel", MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun BusyTile(used: Int, budget: Int, onRetry: () -> Unit, onRemove: () -> Unit) {
    StateTile(
        icon = "⏳",
        title = "All tuners busy",
        body = "No free tuner for this Tile ($used/$budget in use).",
        onRetry = onRetry,
        onRemove = onRemove,
    )
}

@Composable
private fun FailedTile(error: PlaybackError, onRetry: () -> Unit, onRemove: () -> Unit) {
    val (title, body) = when (error) {
        PlaybackError.AllTunersBusy ->
            "All tuners busy" to "No free tuner for this Tile right now."
        PlaybackError.Unreachable ->
            "Stream unreachable" to "Couldn't reach this channel on the proxy."
        is PlaybackError.RedirectingToPortal ->
            "Redirecting to portal" to (error.target ?: "The player can't follow this redirect.")
    }
    StateTile(icon = "⚠", title = title, body = body, onRetry = onRetry, onRemove = onRemove)
}

@Composable
private fun StateTile(
    icon: String,
    title: String,
    body: String,
    onRetry: () -> Unit,
    onRemove: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xF20A0E14))
            .clickable { },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Label(icon, MaterialTheme.colorScheme.onSurface, 22.sp)
            Label(title, MaterialTheme.colorScheme.onSurface, font = FontWeight.SemiBold)
            Label(body, MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 3)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onRetry) { Text("Retry") }
                OutlinedButton(onClick = onRemove) { Text("Remove") }
            }
        }
    }
}

@Composable
private fun ChannelTag(channel: Channel) {
    Row(
        modifier = Modifier
            .padding(8.dp)
            .fillMaxWidth(0.7f)
            .clip(RoundedCornerShape(20.dp))
            .background(Color(0xA8000000))
            .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(20.dp))
            .padding(horizontal = 8.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        channel.number?.let { Label("CH $it", Color.White, 10.sp) }
        Label(
            channel.name,
            Color.White,
            11.sp,
            modifier = Modifier.weight(1f),
            maxLines = 1,
        )
    }
}

@Composable
private fun AudioBadge(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .padding(8.dp)
            .clip(RoundedCornerShape(20.dp))
            .background(MaterialTheme.colorScheme.primary)
            .padding(horizontal = 9.dp, vertical = 2.dp),
    ) {
        Label("🔊 AUDIO", Color(0xFF04121F), 10.sp, font = FontWeight.Bold)
    }
}

@Composable
private fun TileChrome(
    armed: Boolean,
    isAudio: Boolean,
    onPick: () -> Unit,
    onSwap: () -> Unit,
    onAudio: () -> Unit,
    onRemove: () -> Unit,
    focusRequester: FocusRequester? = null,
) {
    Row(
        modifier = Modifier.padding(8.dp).focusGroup(),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        ChromeButton("Pick", onClick = onPick, focusRequester = focusRequester)
        ChromeButton(if (armed) "Swap ✓" else "Swap", active = armed, onClick = onSwap)
        ChromeButton("🔊", active = isAudio, onClick = onAudio)
        ChromeButton("✕", onClick = onRemove)
    }
}

@Composable
private fun ChromeButton(
    label: String,
    onClick: () -> Unit,
    active: Boolean = false,
    focusRequester: FocusRequester? = null,
) {
    var focused by remember { mutableStateOf(false) }
    val accent = MaterialTheme.colorScheme.primary
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(9.dp))
            .background(if (active) accent else Color(0xB8000000))
            .border(
                width = if (focused) 3.dp else 1.dp,
                color = if (focused) TvFocusColor else Color(0x22FFFFFF),
                shape = RoundedCornerShape(9.dp),
            )
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .onFocusChanged { focused = it.isFocused }
            .clickable(onClick = onClick)
            .padding(horizontal = 9.dp, vertical = 5.dp),
    ) {
        Label(
            label,
            if (active) Color(0xFF04121F) else Color.White,
            11.sp,
            font = if (active) FontWeight.Bold else null,
        )
    }
}

/**
 * TV: the controls for the selected Tile, as a screen-level bar (a remote can't D-pad
 * into the per-Tile chrome). Focus lands on it when it opens; Back closes it.
 */
@Composable
private fun MultiviewActionBar(
    slot: Int,
    selected: Int,
    isAudio: Boolean,
    onPick: () -> Unit,
    onSwap: () -> Unit,
    onAudio: () -> Unit,
    onRemove: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val actions = listOf("Pick", "Swap", if (isAudio) "🔊 Audio" else "Audio", "Remove", "Close")
    Surface(
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 6.dp,
        modifier = modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Label("Tile ${slot + 1}", MaterialTheme.colorScheme.onSurface, 14.sp, maxLines = 1)
            Spacer(Modifier.weight(1f))
            actions.forEachIndexed { i, label ->
                BarButton(
                    label,
                    selected = i == selected,
                    onClick = {
                        when (i) {
                            0 -> onPick()
                            1 -> onSwap()
                            2 -> onAudio()
                            3 -> onRemove()
                            else -> onClose()
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun BarButton(label: String, selected: Boolean, onClick: () -> Unit) {
    val accent = MaterialTheme.colorScheme.primary
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(if (selected) accent else MaterialTheme.colorScheme.surfaceVariant)
            // The bar's Row owns the keys; the buttons are visual only on TV.
            .focusProperties { canFocus = false }
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
    ) {
        Text(
            text = label,
            color = if (selected) MaterialTheme.colorScheme.onPrimary
            else MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
            softWrap = false,
        )
    }
}

@Composable
private fun MultiviewTopBar(
    state: MultiviewUiState,
    showFullscreen: Boolean,
    showLayout: Boolean,
    immersive: Boolean,
    highlighted: Int?,
    onToggleFullscreen: () -> Unit,
    onCycleLayout: () -> Unit,
    onBack: () -> Unit,
    onRetry: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TopBarButton(stringResource(R.string.back), highlighted == 0, onBack)
        if (showLayout) {
            TopBarButton("Grid ${state.layout.label}", highlighted == 1, onCycleLayout)
        }
        Spacer(Modifier.weight(1f))
        Label(
            "Tuners ${state.tunersUsed}/${state.tunerCount}" +
                if (state.tunerCountKnown) "" else "?",
            MaterialTheme.colorScheme.onSurfaceVariant,
            11.sp,
            maxLines = 1,
        )
        TopBarButton("Refresh", highlighted == 2, onRetry)
        if (showFullscreen) {
            TopBarButton(
                if (immersive) "Exit full" else "Full screen",
                highlighted == 3,
                onToggleFullscreen,
            )
        }
    }
}

/** A top-bar button; [highlighted] is the manual TV focus (Compose focus is bypassed). */
@Composable
private fun TopBarButton(label: String, highlighted: Boolean, onClick: () -> Unit) {
    val accent = MaterialTheme.colorScheme.primary
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(if (highlighted) accent.copy(alpha = 0.25f) else Color.Transparent)
            .border(
                width = if (highlighted) 3.dp else 0.dp,
                color = if (highlighted) TvFocusColor else Color.Transparent,
                shape = RoundedCornerShape(50),
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        Text(text = label, color = accent, maxLines = 1, softWrap = false)
    }
}

@Composable
private fun Centered(content: @Composable () -> Unit) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            content()
        }
    }
}

@Composable
private fun Label(
    text: String,
    color: Color,
    fontSize: androidx.compose.ui.unit.TextUnit = 13.sp,
    font: FontWeight? = null,
    modifier: Modifier = Modifier,
    maxLines: Int = Int.MAX_VALUE,
) {
    BasicText(
        text = text,
        modifier = modifier,
        style = TextStyle(color = color, fontSize = fontSize, fontWeight = font),
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
    )
}
