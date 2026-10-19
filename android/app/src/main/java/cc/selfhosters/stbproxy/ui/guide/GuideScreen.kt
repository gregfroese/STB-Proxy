package cc.selfhosters.stbproxy.ui.guide

import android.content.res.Configuration
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text as M3Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.data.ZapScope
import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.model.GuideHit
import cc.selfhosters.stbproxy.data.model.GuideProgramme
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.picker.PhoneBlockChips
import cc.selfhosters.stbproxy.ui.picker.PickerPalette
import cc.selfhosters.stbproxy.ui.picker.SearchField
import cc.selfhosters.stbproxy.ui.picker.TvBlockRail
import cc.selfhosters.stbproxy.ui.picker.channelsInGroup
import cc.selfhosters.stbproxy.ui.picker.effectiveGroupMode
import cc.selfhosters.stbproxy.ui.picker.groupMatchCounts
import cc.selfhosters.stbproxy.ui.picker.groupRail
import cc.selfhosters.stbproxy.ui.picker.launchGroupFor
import cc.selfhosters.stbproxy.ui.picker.pickerPalette
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * The account-scoped Guide (tickets 04/05/09): a program-level search plus a
 * Block/Genre-grouped "on now" channel list with inline per-channel timelines.
 * Reuses the picker's rail/chips and search field (variant B), and hands the
 * launch scope to the player (ticket 07).
 */
@Composable
fun GuideScreen(
    onChannelClick: (Channel, ZapScope) -> Unit,
    onBack: () -> Unit,
    onOpenSettings: () -> Unit,
    viewModel: GuideViewModel = viewModel(
        factory = GuideViewModel.factory(
            apiClient = LocalAppContainer.current.apiClient,
            epgRepository = LocalAppContainer.current.epgRepository,
            session = LocalAppContainer.current.sessionController,
            viewerPreferences = LocalAppContainer.current.viewerPreferences,
        ),
    ),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val container = LocalAppContainer.current
    val configuration = LocalConfiguration.current
    val isTv = configuration.uiMode and Configuration.UI_MODE_TYPE_MASK ==
        Configuration.UI_MODE_TYPE_TELEVISION
    val palette = pickerPalette()
    val mode = effectiveGroupMode(state.groupMode, state.blocks)

    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(30_000)
            now = Instant.now()
        }
    }

    val browseChannels = remember(state.channels, state.channelFilter, state.onNow, state.nowNext, now) {
        var list = filterGuideChannels(state.channels, state.channelFilter)
        if (state.onNow) list = airingChannels(list, state.nowNext, now)
        list
    }
    val railSource = if (state.searching) state.channels else browseChannels
    val rail = remember(state.blocks, railSource, mode) { groupRail(mode, state.blocks, railSource) }
    val resultChannels = remember(state.results, state.channels) { hitChannels(state.results, state.channels) }
    val visibleChannels = remember(browseChannels, state.activeBlock, mode) {
        state.activeBlock?.let { channelsInGroup(mode, browseChannels, it) }.orEmpty()
    }
    val blockCounts = remember(resultChannels, rail, mode, state.searching) {
        if (state.searching) groupMatchCounts(mode, resultChannels, rail.map { it.name }, "") else emptyMap()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background),
    ) {
        GuideTopBar(
            accountLabel = state.accountLabel,
            palette = palette,
            onBack = onBack,
            onReload = viewModel::reload,
            onOpenSettings = onOpenSettings,
        )
        SearchField(
            query = state.query,
            onQueryChange = viewModel::onQueryChange,
            palette = palette,
            mode = mode,
            isTv = isTv,
        )
        GuideControls(
            state = state,
            palette = palette,
            onOnNow = viewModel::onOnNowChange,
            onGroupMode = {
                container.viewerPreferences.setGroupMode(
                    if (mode == GroupMode.BLOCKS) GroupMode.GENRES else GroupMode.BLOCKS,
                )
            },
            onChannelFilter = viewModel::onChannelFilterChange,
            onToggleAdvanced = viewModel::onToggleAdvanced,
            onMode = viewModel::onModeChange,
        )

        state.error?.let { message ->
            M3Text(
                text = message,
                color = MaterialTheme.colorScheme.error,
                fontSize = 13.sp,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }
        state.notice?.let { notice ->
            M3Text(
                text = notice,
                color = palette.muted,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }

        if (state.loading) {
            Centered { CircularProgressIndicator() }
        } else if (isTv) {
            Row(modifier = Modifier.fillMaxSize()) {
                TvBlockRail(
                    rail = rail,
                    activeBlock = state.activeBlock,
                    searching = state.searching,
                    resultCount = resultChannels.size,
                    blockCounts = blockCounts,
                    palette = palette,
                    onSelect = viewModel::onBlockSelected,
                )
                GuideList(
                    state = state,
                    isTv = true,
                    mode = mode,
                    now = now,
                    resultChannels = resultChannels,
                    visibleChannels = visibleChannels,
                    palette = palette,
                    onPlayHit = { hit -> playHit(state, hit, resultChannels, onChannelClick) },
                    onPlayChannel = { channel -> playBrowse(state, channel, visibleChannels, mode, onChannelClick) },
                    onToggleTimeline = viewModel::toggleTimeline,
                    onLoadMore = viewModel::onLoadMore,
                    modifier = Modifier.weight(1f),
                )
            }
        } else {
            Column(modifier = Modifier.fillMaxSize()) {
                PhoneBlockChips(
                    rail = rail,
                    activeBlock = state.activeBlock,
                    searching = state.searching,
                    resultCount = resultChannels.size,
                    blockCounts = blockCounts,
                    palette = palette,
                    onSelect = viewModel::onBlockSelected,
                )
                GuideList(
                    state = state,
                    isTv = false,
                    mode = mode,
                    now = now,
                    resultChannels = resultChannels,
                    visibleChannels = visibleChannels,
                    palette = palette,
                    onPlayHit = { hit -> playHit(state, hit, resultChannels, onChannelClick) },
                    onPlayChannel = { channel -> playBrowse(state, channel, visibleChannels, mode, onChannelClick) },
                    onToggleTimeline = viewModel::toggleTimeline,
                    onLoadMore = viewModel::onLoadMore,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

private fun playHit(
    state: GuideUiState,
    hit: GuideHit,
    resultChannels: List<Channel>,
    onChannelClick: (Channel, ZapScope) -> Unit,
) {
    val channel = resultChannels.firstOrNull {
        it.portal == hit.portal && it.channelId == hit.channelId
    } ?: return
    val label = if (state.query.isNotBlank()) "Search: “${state.query.trim()}”" else "Results (${resultChannels.size})"
    onChannelClick(channel, ZapScope.Channels(resultChannels.map { channelKey(it) }, label))
}

private fun playBrowse(
    state: GuideUiState,
    channel: Channel,
    visibleChannels: List<Channel>,
    mode: GroupMode,
    onChannelClick: (Channel, ZapScope) -> Unit,
) {
    val scope = if (state.onNow) {
        ZapScope.Channels(visibleChannels.map { channelKey(it) }, "On now")
    } else {
        launchGroupFor(mode, channel, state.activeBlock).let { ZapScope.Group(it, it) }
    }
    onChannelClick(channel, scope)
}

@Composable
private fun GuideTopBar(
    accountLabel: String?,
    palette: PickerPalette,
    onBack: () -> Unit,
    onReload: () -> Unit,
    onOpenSettings: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = onBack, modifier = Modifier.focusRing()) {
                M3Text("‹ Channels")
            }
            Spacer(Modifier.width(10.dp))
            M3Text(
                text = "Guide",
                style = MaterialTheme.typography.headlineSmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            OutlinedButton(onClick = onReload, modifier = Modifier.focusRing()) { M3Text("Reload") }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(onClick = onOpenSettings, modifier = Modifier.focusRing()) { M3Text("Settings") }
        }
        accountLabel?.let {
            M3Text(
                text = it,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun GuideControls(
    state: GuideUiState,
    palette: PickerPalette,
    onOnNow: (Boolean) -> Unit,
    onGroupMode: () -> Unit,
    onChannelFilter: (String) -> Unit,
    onToggleAdvanced: () -> Unit,
    onMode: (GuideMode) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ToggleChip("All", !state.onNow, palette) { onOnNow(false) }
        ToggleChip("On now", state.onNow, palette) { onOnNow(true) }
        ToggleChip(
            if (effectiveGroupMode(state.groupMode, state.blocks) == GroupMode.BLOCKS) "Blocks" else "Genres",
            false,
            palette,
            onClick = onGroupMode,
        )
        ToggleChip("Match", state.advanced, palette, onClick = onToggleAdvanced)
    }
    if (state.advanced) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            GuideMode.entries.forEach { option ->
                ToggleChip(option.wire, option == state.mode, palette) { onMode(option) }
            }
        }
    }
    ChannelSubFilter(
        value = state.channelFilter,
        onValueChange = onChannelFilter,
        palette = palette,
    )
}

@Composable
private fun ToggleChip(
    label: String,
    selected: Boolean,
    palette: PickerPalette,
    onClick: () -> Unit,
) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(if (selected) palette.accent else palette.surfaceVariant)
            .focusRing(RoundedCornerShape(20.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        M3Text(
            text = label,
            color = if (selected) palette.background else palette.onSurface,
            fontSize = 12.sp,
            maxLines = 1,
        )
    }
}

@Composable
private fun ChannelSubFilter(
    value: String,
    onValueChange: (String) -> Unit,
    palette: PickerPalette,
) {
    SearchField(
        query = value,
        onQueryChange = onValueChange,
        palette = palette,
        isTv = false,
    )
}

@Composable
private fun GuideList(
    state: GuideUiState,
    isTv: Boolean,
    mode: GroupMode,
    now: Instant,
    resultChannels: List<Channel>,
    visibleChannels: List<Channel>,
    palette: PickerPalette,
    onPlayHit: (GuideHit) -> Unit,
    onPlayChannel: (Channel) -> Unit,
    onToggleTimeline: (Channel) -> Unit,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val firstFocus = remember { FocusRequester() }
    if (isTv) {
        LaunchedEffect(Unit) { runCatching { firstFocus.requestFocus() } }
    }
    val channels = if (state.searching) emptyList() else visibleChannels
    LazyColumn(
        modifier = modifier.focusGroup(),
        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (state.searching) {
            item(key = "__count__") {
                M3Text(
                    text = resultCountLabel(state.results.size, state.total),
                    color = palette.muted,
                    fontSize = 12.sp,
                )
            }
            if (state.searchLoading && state.results.isEmpty()) {
                item(key = "__loading__") { Centered { CircularProgressIndicator() } }
            } else if (state.searchError != null) {
                item(key = "__error__") {
                    M3Text(state.searchError, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
                }
            } else if (state.results.isEmpty()) {
                item(key = "__empty__") {
                    M3Text("No programmes match.", color = palette.muted, fontSize = 13.sp)
                }
            }
            itemsIndexed(
                state.results,
                key = { _, hit -> "${hit.portal}:${hit.channelId}:${hit.start}:${hit.title}" },
            ) { index, hit ->
                val channel = resultChannels.firstOrNull {
                    it.portal == hit.portal && it.channelId == hit.channelId
                }
                GuideResultRow(
                    hit = hit,
                    now = now,
                    channel = channel,
                    open = channel != null && state.openKey == channelKey(channel),
                    timeline = channel?.let { state.timelines[channelKey(it)] },
                    timelineLoading = channel?.let { state.timelineLoading[channelKey(it)] } == true,
                    palette = palette,
                    focusRequester = if (isTv && index == 0) firstFocus else null,
                    onPlay = { onPlayHit(hit) },
                    onToggle = { channel?.let(onToggleTimeline) },
                )
                channel?.let {
                    val programmes = state.timelines[channelKey(it)]
                    if (state.openKey == channelKey(it) && programmes != null) {
                        GuideTimeline(programmes, now, palette)
                    }
                }
            }
            if (state.total > state.results.size && state.limit < GUIDE_LIMIT_MAX) {
                item(key = "__more__") {
                    Button(onClick = onLoadMore, modifier = Modifier.focusRing()) { M3Text("Load more") }
                }
            }
        } else {
            if (channels.isEmpty()) {
                item(key = "__empty__") {
                    M3Text(
                        if (state.onNow) "Nothing is on now." else "No channels here.",
                        color = palette.muted,
                        fontSize = 13.sp,
                    )
                }
            }
            itemsIndexed(
                channels,
                key = { _, channel -> "${channel.portal}/${channel.channelId}" },
            ) { index, channel ->
                GuideChannelRow(
                    channel = channel,
                    nowNext = channel.epgId?.let { state.nowNext[it] },
                    open = state.openKey == channelKey(channel),
                    palette = palette,
                    focusRequester = if (isTv && index == 0) firstFocus else null,
                    onPlay = { onPlayChannel(channel) },
                    onToggle = { onToggleTimeline(channel) },
                )
                val programmes = state.timelines[channelKey(channel)]
                if (state.openKey == channelKey(channel)) {
                    if (state.timelineLoading[channelKey(channel)] == true) {
                        Centered { CircularProgressIndicator() }
                    } else {
                        GuideTimeline(programmes.orEmpty(), now, palette)
                    }
                }
            }
        }
    }
}

@Composable
private fun GuideChannelRow(
    channel: Channel,
    nowNext: NowNext?,
    open: Boolean,
    palette: PickerPalette,
    focusRequester: FocusRequester?,
    onPlay: () -> Unit,
    onToggle: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(palette.surface)
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .focusRing(RoundedCornerShape(12.dp))
            .clickable(onClick = onPlay)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            M3Text(channel.name, color = palette.onSurface, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val now = nowNext?.now
            M3Text(
                text = buildString {
                    channel.number?.let { append("CH $it · ") }
                    if (now != null) append("${now.title} ${now.timeRange(ZoneId.systemDefault())}") else append("No guide data")
                },
                color = palette.muted,
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Box(
            modifier = Modifier
                .focusRing(RoundedCornerShape(8.dp))
                .clickable(onClick = onToggle)
                .padding(horizontal = 10.dp, vertical = 6.dp),
        ) {
            M3Text(if (open) "▲" else "▼", color = palette.accent, fontSize = 13.sp)
        }
    }
}

@Composable
private fun GuideResultRow(
    hit: GuideHit,
    now: Instant,
    channel: Channel?,
    open: Boolean,
    timeline: List<GuideProgramme>?,
    timelineLoading: Boolean,
    palette: PickerPalette,
    focusRequester: FocusRequester?,
    onPlay: () -> Unit,
    onToggle: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(11.dp))
            .background(palette.surface)
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .focusRing(RoundedCornerShape(11.dp))
            .clickable(onClick = onPlay)
            .padding(horizontal = 11.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        Column(modifier = Modifier.width(52.dp)) {
            M3Text(hhmm(hit.start), color = palette.onSurface, fontSize = 13.sp)
            M3Text(hhmm(hit.stop), color = palette.muted, fontSize = 11.sp)
        }
        Column(modifier = Modifier.weight(1f)) {
            M3Text(hit.title, color = palette.onSurface, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            M3Text(
                text = buildString {
                    hit.channelNumber?.let { append("CH $it · ") }
                    append(hit.channelName)
                    if (programmeAiring(hit.start, hit.stop, now.epochSecond)) append("  ● ON NOW")
                },
                color = palette.muted,
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (channel != null) {
            Box(
                modifier = Modifier
                    .focusRing(RoundedCornerShape(8.dp))
                    .clickable(onClick = onToggle)
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            ) {
                M3Text(if (open) "▲" else "▼", color = palette.accent, fontSize = 13.sp)
            }
        }
        if (timelineLoading && open && timeline == null) {
            CircularProgressIndicator(modifier = Modifier.width(16.dp).height(16.dp))
        }
    }
}

@Composable
private fun GuideTimeline(
    programmes: List<GuideProgramme>,
    now: Instant,
    palette: PickerPalette,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(palette.surfaceVariant)
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        if (programmes.isEmpty()) {
            M3Text("No guide data.", color = palette.muted, fontSize = 12.sp)
        }
        programmes.forEach { programme ->
            val airing = programmeAiring(programme.start, programme.stop, now.epochSecond)
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                M3Text(hhmm(programme.start), color = palette.muted, fontSize = 11.sp, modifier = Modifier.width(46.dp))
                M3Text(
                    text = programme.title,
                    color = palette.onSurface,
                    fontSize = 13.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                if (airing) {
                    M3Text("● ON NOW", color = MaterialTheme.colorScheme.error, fontSize = 10.sp)
                }
            }
        }
    }
}

@Composable
private fun Centered(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(modifier = modifier.fillMaxWidth().padding(20.dp), contentAlignment = Alignment.Center) { content() }
}

private val GUIDE_TIME_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

private fun hhmm(epochSeconds: Long): String =
    GUIDE_TIME_FORMAT.format(Instant.ofEpochSecond(epochSeconds).atZone(ZoneId.systemDefault()))
