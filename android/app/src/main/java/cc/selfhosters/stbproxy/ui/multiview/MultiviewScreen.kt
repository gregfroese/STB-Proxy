package cc.selfhosters.stbproxy.ui.multiview

import android.content.res.Configuration
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
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
import androidx.media3.ui.compose.PlayerSurface
import cc.selfhosters.stbproxy.R
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.picker.ChannelPickerOverlay
import cc.selfhosters.stbproxy.ui.player.PlaybackError
import cc.selfhosters.stbproxy.ui.player.buildStreamPlayer
import cc.selfhosters.stbproxy.ui.player.classifyPlaybackException
import cc.selfhosters.stbproxy.ui.player.mediaItemFor
import androidx.compose.ui.res.stringResource

/**
 * The Multiview grid (spec 2.7). One Compose surface with three densities: TV a
 * 2x2, phone landscape a 1x2, phone portrait the focused Tile full-bleed. Each
 * Tile is its own ExoPlayer fed `/play/<portal>/<channelId>`, bounded by the
 * proxy's tuner budget.
 */
@Composable
fun MultiviewScreen(
    onBack: () -> Unit,
    viewModel: MultiviewViewModel = viewModel(
        factory = MultiviewViewModel.factory(LocalAppContainer.current.apiClient),
    ),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val configuration = LocalConfiguration.current
    val isTv = configuration.uiMode and Configuration.UI_MODE_TYPE_MASK ==
        Configuration.UI_MODE_TYPE_TELEVISION
    val landscape = configuration.orientation == Configuration.ORIENTATION_LANDSCAPE

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        MultiviewTopBar(state = state, onBack = onBack, onRetry = viewModel::load)

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
                )
            }
        }

        if (!isTv && !landscape) {
            SlotStrip(state = state, onFocus = viewModel::setFocus)
        }
    }

    state.pickFor?.let { slot ->
        ChannelPickerOverlay(
            title = "Pick channel for Tile ${slot + 1}",
            channels = state.channels,
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
) {
    val gap = 8.dp
    when {
        isTv -> Column(
            modifier = Modifier.fillMaxSize().padding(gap),
            verticalArrangement = Arrangement.spacedBy(gap),
        ) {
            state.tiles.chunked(2).forEach { rowTiles ->
                Row(
                    modifier = Modifier.fillMaxWidth().weight(1f),
                    horizontalArrangement = Arrangement.spacedBy(gap),
                ) {
                    rowTiles.forEach { tile ->
                        TileCell(
                            tile = tile,
                            state = state,
                            viewModel = viewModel,
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
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                )
            }
        }

        else -> {
            val focused = state.tiles.firstOrNull { it.slot == state.focusSlot }
                ?: state.tiles.firstOrNull()
            if (focused != null) {
                TileCell(
                    tile = focused,
                    state = state,
                    viewModel = viewModel,
                    modifier = Modifier.fillMaxSize().padding(gap),
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
    modifier: Modifier = Modifier,
) {
    key(tile.slot) {
        val status = tileStatus(tile, state.overBudget, state.errors[tile.slot])
        val isAudio = state.audioSlot == tile.slot
        val armed = state.swapFrom == tile.slot
        val accent = MaterialTheme.colorScheme.primary
        var focused by remember { mutableStateOf(false) }
        val shape = RoundedCornerShape(10.dp)

        Box(
            modifier = modifier
                .clip(shape)
                .background(Color.Black)
                .border(
                    width = if (isAudio) 3.dp else 1.dp,
                    color = when {
                        isAudio -> accent
                        focused -> Color(0xFFFFD34D)
                        else -> MaterialTheme.colorScheme.surfaceVariant
                    },
                    shape = shape,
                )
                .onFocusChanged { focused = it.isFocused }
                .clickable { viewModel.onTileClick(tile.slot) },
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
                TileChrome(
                    armed = armed,
                    isAudio = isAudio,
                    onPick = { viewModel.openPicker(tile.slot) },
                    onSwap = { viewModel.swap(tile.slot) },
                    onAudio = { viewModel.setAudio(tile.slot) },
                    onRemove = { viewModel.remove(tile.slot) },
                    modifier = Modifier.align(Alignment.BottomEnd),
                )
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
    val player = remember { buildStreamPlayer(context, dataSourceFactory) }

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

    PlayerSurface(player = player, modifier = Modifier.fillMaxSize())
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
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.padding(8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        ChromeButton("Pick", onClick = onPick)
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
) {
    var focused by remember { mutableStateOf(false) }
    val accent = MaterialTheme.colorScheme.primary
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(9.dp))
            .background(if (active) accent else Color(0xB8000000))
            .border(
                width = 1.dp,
                color = if (focused) Color(0xFFFFD34D) else Color(0x22FFFFFF),
                shape = RoundedCornerShape(9.dp),
            )
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

@Composable
private fun MultiviewTopBar(
    state: MultiviewUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBack) { Text(stringResource(R.string.back)) }
        Text(
            text = stringResource(R.string.multiview_title),
            style = MaterialTheme.typography.titleMedium,
        )
        Spacer(Modifier.weight(1f))
        Label(
            "Tuners ${state.tunersUsed}/${state.tunerCount}" +
                if (state.tunerCountKnown) "" else " (assumed)",
            MaterialTheme.colorScheme.onSurfaceVariant,
            11.sp,
        )
        TextButton(onClick = onRetry) { Text("Refresh") }
    }
}

/** Portrait only: pick which Tile is full-bleed on a phone (spec 2.7). */
@Composable
private fun SlotStrip(state: MultiviewUiState, onFocus: (Int) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        state.tiles.forEach { tile ->
            val selected = tile.slot == state.focusSlot
            val isAudio = state.audioSlot == tile.slot
            Box(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(9.dp))
                    .background(
                        if (selected) MaterialTheme.colorScheme.surfaceVariant else Color.Transparent,
                    )
                    .border(
                        width = if (isAudio) 2.dp else 1.dp,
                        color = if (isAudio) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.surfaceVariant,
                        shape = RoundedCornerShape(9.dp),
                    )
                    .clickable { onFocus(tile.slot) }
                    .padding(vertical = 8.dp),
                contentAlignment = Alignment.Center,
            ) {
                Label(
                    tile.channel?.let { "Tile ${tile.slot + 1} · CH ${it.number ?: "—"}" }
                        ?: "Tile ${tile.slot + 1} · empty",
                    MaterialTheme.colorScheme.onSurface,
                    11.sp,
                    maxLines = 1,
                )
            }
        }
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
