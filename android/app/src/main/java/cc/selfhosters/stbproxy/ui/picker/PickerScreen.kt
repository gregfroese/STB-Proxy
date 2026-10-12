package cc.selfhosters.stbproxy.ui.picker

import android.content.res.Configuration
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text as M3Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusDirection
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.R
import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.network.NO_CHANNELS_NOTICE
import cc.selfhosters.stbproxy.data.network.SECURITY_OFF_NOTICE
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.focusRing
import coil.compose.AsyncImage

/** Focus ring colour for D-pad navigation (spec 2.10). */
internal val PickerFocusRing = Color(0xFFFFD34D)

/** Colours the picker draws with, lifted from the app's Material theme. */
internal data class PickerPalette(
    val background: Color,
    val surface: Color,
    val surfaceVariant: Color,
    val accent: Color,
    val onSurface: Color,
    val muted: Color,
    val focus: Color,
)

/**
 * The Block-grouped channel picker (spec 2.5). TV renders a vertical Block rail
 * beside a wide grid; phone renders a horizontal Block chip strip above a narrow
 * grid. Search spans all Blocks and suspends Block navigation.
 */
@Composable
fun PickerScreen(
    onChannelClick: (Channel, launchBlock: String) -> Unit,
    onOpenSettings: () -> Unit,
    onOpenMultiview: () -> Unit,
    viewModel: PickerViewModel = viewModel(
        factory = PickerViewModel.factory(
            LocalAppContainer.current.apiClient,
            LocalAppContainer.current.epgRepository,
            LocalAppContainer.current.sessionController,
        ),
    ),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val configuration = LocalConfiguration.current
    val isTv = configuration.uiMode and Configuration.UI_MODE_TYPE_MASK ==
        Configuration.UI_MODE_TYPE_TELEVISION

    val rail = remember(state.blocks, state.channels) {
        blockRail(state.blocks, state.channels)
    }
    val searching = state.query.isNotBlank()
    val visibleChannels = remember(state.channels, state.activeBlock, state.query, searching, state.filter) {
        val base = if (searching) {
            searchChannels(state.channels, state.query)
        } else {
            state.activeBlock?.let { channelsInBlock(state.channels, it) }.orEmpty()
        }
        sortChannels(applyChannelFilter(base, state.filter))
    }
    val blockCounts = remember(state.channels, rail, state.query, searching) {
        if (searching) blockMatchCounts(state.channels, rail.map { it.name }, state.query)
        else emptyMap()
    }

    val palette = pickerPalette()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background)
            .safeDrawingPadding(),
    ) {
        PickerTopBar(
            state = state,
            onOpenSettings = onOpenSettings,
            onOpenMultiview = onOpenMultiview,
        )
        SearchField(
            query = state.query,
            onQueryChange = viewModel::onQueryChange,
            palette = palette,
            isTv = isTv,
        )
        FilterRow(
            filter = state.filter,
            onFilter = viewModel::onFilterChange,
            palette = palette,
        )
        if (state.credentialsUnverified) {
            BasicLabel(
                text = SECURITY_OFF_NOTICE,
                color = palette.muted,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }
        Box(modifier = Modifier.fillMaxSize()) {
            when {
                state.loading -> Centered { CircularProgressIndicator() }

                state.error != null -> Centered {
                    BasicLabel(state.error.orEmpty(), MaterialTheme.colorScheme.error, 14.sp)
                    Button(onClick = viewModel::refresh) { M3Text("Retry") }
                }

                state.channels.isEmpty() -> Centered {
                    BasicLabel(NO_CHANNELS_NOTICE, palette.muted, 14.sp)
                }

                else -> PickerBody(
                    isTv = isTv,
                    rail = rail,
                    activeBlock = state.activeBlock,
                    searching = searching,
                    query = state.query,
                    visibleChannels = visibleChannels,
                    blockCounts = blockCounts,
                    nowNext = state.nowNext,
                    palette = palette,
                    onBlockSelected = viewModel::onBlockSelected,
                    onChannelClick = { channel ->
                        onChannelClick(channel, launchBlockFor(channel, state.activeBlock))
                    },
                )
            }
        }
    }
}

@Composable
private fun PickerBody(
    isTv: Boolean,
    rail: List<BlockEntry>,
    activeBlock: String?,
    searching: Boolean,
    query: String,
    visibleChannels: List<Channel>,
    blockCounts: Map<String, Int>,
    nowNext: Map<String, NowNext>,
    palette: PickerPalette,
    onBlockSelected: (String) -> Unit,
    onChannelClick: (Channel) -> Unit,
) {
    if (isTv) {
        Row(modifier = Modifier.fillMaxSize()) {
            TvBlockRail(
                rail = rail,
                activeBlock = activeBlock,
                searching = searching,
                resultCount = visibleChannels.size,
                blockCounts = blockCounts,
                palette = palette,
                onSelect = onBlockSelected,
            )
            PickerList(
                channels = visibleChannels,
                nowNext = nowNext,
                activeBlock = activeBlock,
                searching = searching,
                isTv = true,
                query = query,
                palette = palette,
                onChannelClick = onChannelClick,
                modifier = Modifier.weight(1f),
            )
        }
    } else {
        Column(modifier = Modifier.fillMaxSize()) {
            PhoneBlockChips(
                rail = rail,
                activeBlock = activeBlock,
                searching = searching,
                resultCount = visibleChannels.size,
                blockCounts = blockCounts,
                palette = palette,
                onSelect = onBlockSelected,
            )
            PickerList(
                channels = visibleChannels,
                nowNext = nowNext,
                activeBlock = activeBlock,
                searching = searching,
                isTv = false,
                query = query,
                palette = palette,
                onChannelClick = onChannelClick,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
internal fun PickerList(
    channels: List<Channel>,
    nowNext: Map<String, NowNext>,
    activeBlock: String?,
    searching: Boolean,
    isTv: Boolean,
    query: String,
    palette: PickerPalette,
    onChannelClick: (Channel) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (channels.isEmpty()) {
        val message = if (searching) "No channels match \"$query\"" else "No channels"
        Centered(modifier) { BasicLabel(message, palette.muted, 14.sp) }
        return
    }
    // Compose for TV does not auto-focus; seed focus on the first row (spec 2.10).
    val firstItemFocus = remember { FocusRequester() }
    if (isTv) {
        LaunchedEffect(Unit) { runCatching { firstItemFocus.requestFocus() } }
    }
    LazyColumn(
        modifier = modifier.focusGroup(),
        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        itemsIndexed(channels, key = { _, channel -> "${channel.portal}/${channel.channelId}" }) { index, channel ->
            ChannelRow(
                channel = channel,
                nowNext = channel.epgId?.let { nowNext[it] },
                activeBlock = activeBlock,
                searching = searching,
                palette = palette,
                onClick = { onChannelClick(channel) },
                focusRequester = if (isTv && index == 0) firstItemFocus else null,
            )
        }
    }
}

/**
 * One channel as a single row — logo, name (full width, so long names show),
 * number, a now/next teaser and its Block tags — rather than a grid box.
 */
@Composable
internal fun ChannelRow(
    channel: Channel,
    nowNext: NowNext?,
    activeBlock: String?,
    searching: Boolean,
    palette: PickerPalette,
    onClick: () -> Unit,
    focusRequester: FocusRequester? = null,
) {
    var focused by remember { mutableStateOf(false) }
    val extra = extraBlockCount(channel, activeBlock, searching)
    val shape = RoundedCornerShape(12.dp)

    Row(
        modifier = Modifier
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .fillMaxWidth()
            .clip(shape)
            .background(palette.surface)
            .border(
                width = if (focused) 2.dp else 1.dp,
                color = if (focused) palette.focus else palette.surfaceVariant,
                shape = shape,
            )
            .onFocusChanged { focused = it.isFocused }
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ChannelLogo(channel = channel, palette = palette)
        Spacer(modifier = Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                BasicLabel(
                    channel.name,
                    palette.onSurface,
                    15.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    modifier = Modifier.weight(1f, fill = false),
                )
                channel.number?.let {
                    Spacer(modifier = Modifier.width(8.dp))
                    BasicLabel("CH $it", palette.muted, 12.sp, maxLines = 1)
                }
            }
            val tags = channel.blocks.joinToString(" · ")
            val teaser = nowNext?.now?.title?.let { "Now: $it" } ?: "No guide data"
            BasicLabel(
                listOfNotNull(teaser, tags.ifBlank { null }).joinToString("   •   "),
                palette.muted,
                11.sp,
                maxLines = 1,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
        if (extra > 0) {
            Spacer(modifier = Modifier.width(8.dp))
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(palette.accent)
                    .padding(horizontal = 8.dp, vertical = 2.dp),
            ) {
                BasicLabel("+$extra", palette.background, 11.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun BlockTag(text: String, color: Color, palette: PickerPalette) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(palette.surfaceVariant)
            .padding(horizontal = 6.dp, vertical = 1.dp),
    ) {
        BasicLabel(text, color, 10.sp)
    }
}

@Composable
private fun ChannelLogo(channel: Channel, palette: PickerPalette) {
    val shape = RoundedCornerShape(9.dp)
    Box(
        modifier = Modifier
            .size(40.dp)
            .clip(shape)
            .background(palette.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        BasicLabel(initials(channel.name), palette.muted, 13.sp, fontWeight = FontWeight.Bold)
        if (!channel.logo.isNullOrBlank()) {
            AsyncImage(
                model = channel.logo,
                contentDescription = null,
                contentScale = ContentScale.Fit,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

@Composable
private fun SearchField(
    query: String,
    onQueryChange: (String) -> Unit,
    palette: PickerPalette,
    isTv: Boolean = false,
) {
    val shape = RoundedCornerShape(11.dp)
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 6.dp)
            .clip(shape)
            .background(palette.surfaceVariant)
            .border(1.dp, palette.surfaceVariant, shape)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        if (query.isEmpty()) {
            BasicLabel("Search all Blocks…", palette.muted, 14.sp)
        }
        BasicTextField(
            value = query,
            onValueChange = onQueryChange,
            singleLine = true,
            textStyle = TextStyle(color = palette.onSurface, fontSize = 14.sp),
            cursorBrush = SolidColor(palette.accent),
            // A text field traps the D-pad (it eats Up/Down). On TV it isn't focusable,
            // so the remote walks straight between the top bar and the channel list.
            modifier = Modifier
                .fillMaxWidth()
                .then(if (isTv) Modifier.focusProperties { canFocus = false } else Modifier),
        )
    }
}

/** All / Favourites / Block favourites filter chips. */
@Composable
private fun FilterRow(
    filter: ChannelFilter,
    onFilter: (ChannelFilter) -> Unit,
    palette: PickerPalette,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ChannelFilter.entries.forEach { option ->
            val selected = option == filter
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(if (selected) palette.accent else palette.surfaceVariant)
                    .focusRing(RoundedCornerShape(20.dp))
                    .clickable { onFilter(option) }
                    .padding(horizontal = 12.dp, vertical = 6.dp),
            ) {
                BasicLabel(
                    option.label,
                    if (selected) palette.background else palette.onSurface,
                    12.sp,
                )
            }
        }
    }
}

@Composable
private fun PickerTopBar(
    state: PickerUiState,
    onOpenSettings: () -> Unit,
    onOpenMultiview: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            M3Text(
                text = stringResource(R.string.picker_title),
                style = MaterialTheme.typography.headlineSmall,
            )
            state.accountLabel?.let { label ->
                M3Text(
                    text = label,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilledTonalButton(onClick = onOpenMultiview, modifier = Modifier.focusRing()) {
                M3Text(stringResource(R.string.nav_multiview))
            }
            OutlinedButton(onClick = onOpenSettings, modifier = Modifier.focusRing()) {
                M3Text(stringResource(R.string.nav_settings))
            }
        }
    }
}

@Composable
private fun Centered(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            content()
        }
    }
}

@Composable
private fun BasicLabel(
    text: String,
    color: Color,
    fontSize: TextUnit,
    modifier: Modifier = Modifier,
    fontWeight: FontWeight? = null,
    maxLines: Int = Int.MAX_VALUE,
) {
    BasicText(
        text = text,
        modifier = modifier,
        style = TextStyle(color = color, fontSize = fontSize, fontWeight = fontWeight),
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
private fun pickerPalette(): PickerPalette {
    val scheme = MaterialTheme.colorScheme
    return PickerPalette(
        background = scheme.background,
        surface = scheme.surface,
        surfaceVariant = scheme.surfaceVariant,
        accent = scheme.primary,
        onSurface = scheme.onSurface,
        muted = scheme.onSurfaceVariant,
        focus = PickerFocusRing,
    )
}

private fun initials(name: String): String =
    name.split(' ')
        .filter { it.isNotBlank() }
        .map { it.first().uppercaseChar() }
        .joinToString("")
        .take(2)

/**
 * The 2.5 picker re-presented as an overlay, so Multiview can choose one Tile's
 * channel without leaving the grid (spec 2.7 Pick). Reuses the picker's Block
 * rail (TV vertical rail / phone chip strip) and "Other" grouping, its search
 * and its tiles; selecting a channel hands it back and closes.
 */
@Composable
fun ChannelPickerOverlay(
    title: String,
    blocks: List<String>,
    channels: List<Channel>,
    onSelect: (Channel) -> Unit,
    onDismiss: () -> Unit,
) {
    val palette = pickerPalette()
    val isTv = LocalConfiguration.current.uiMode and Configuration.UI_MODE_TYPE_MASK ==
        Configuration.UI_MODE_TYPE_TELEVISION
    var query by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf(ChannelFilter.ALL) }
    val rail = remember(blocks, channels) { blockRail(blocks, channels) }
    var activeBlock by remember(rail) { mutableStateOf(rail.firstOrNull()?.name) }
    val searching = query.isNotBlank()
    val visible = remember(channels, activeBlock, query, searching, filter) {
        val base = if (searching) searchChannels(channels, query)
        else activeBlock?.let { channelsInBlock(channels, it) }.orEmpty()
        sortChannels(applyChannelFilter(base, filter))
    }
    val blockCounts = remember(channels, rail, query, searching) {
        if (searching) blockMatchCounts(channels, rail.map { it.name }, query) else emptyMap()
    }

    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(palette.background)
                .border(1.dp, palette.surfaceVariant, RoundedCornerShape(16.dp)),
        ) {
            M3Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
            )
            SearchField(query = query, onQueryChange = { query = it }, palette = palette, isTv = isTv)
            FilterRow(filter = filter, onFilter = { filter = it }, palette = palette)
            Box(modifier = Modifier.fillMaxWidth().height(420.dp)) {
                if (isTv) {
                    Row(modifier = Modifier.fillMaxSize()) {
                        TvBlockRail(
                            rail = rail,
                            activeBlock = activeBlock,
                            searching = searching,
                            resultCount = visible.size,
                            blockCounts = blockCounts,
                            palette = palette,
                            onSelect = { activeBlock = it },
                        )
                        PickerList(
                            channels = visible,
                            nowNext = emptyMap(),
                            activeBlock = activeBlock,
                            searching = searching,
                            isTv = true,
                            query = query,
                            palette = palette,
                            onChannelClick = onSelect,
                            modifier = Modifier.weight(1f),
                        )
                    }
                } else {
                    Column(modifier = Modifier.fillMaxSize()) {
                        PhoneBlockChips(
                            rail = rail,
                            activeBlock = activeBlock,
                            searching = searching,
                            resultCount = visible.size,
                            blockCounts = blockCounts,
                            palette = palette,
                            onSelect = { activeBlock = it },
                        )
                        PickerList(
                            channels = visible,
                            nowNext = emptyMap(),
                            activeBlock = activeBlock,
                            searching = searching,
                            isTv = false,
                            query = query,
                            palette = palette,
                            onChannelClick = onSelect,
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = onDismiss) { M3Text(stringResource(R.string.cancel)) }
            }
        }
    }
}
