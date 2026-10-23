package cc.selfhosters.stbproxy.ui.ondemand

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.LocalNavRail
import cc.selfhosters.stbproxy.ui.common.HeaderAction
import cc.selfhosters.stbproxy.ui.common.ScreenGutter
import cc.selfhosters.stbproxy.ui.common.ScreenHeader
import cc.selfhosters.stbproxy.ui.common.isTvDevice
import cc.selfhosters.stbproxy.ui.picker.PickerPalette
import cc.selfhosters.stbproxy.ui.picker.SearchField
import cc.selfhosters.stbproxy.ui.picker.pickerPalette
import kotlinx.coroutines.flow.distinctUntilChanged

/**
 * The On Demand destination (ticket 13, variant C). TV: three panes (categories with
 * Continue watching, a title list, a preview pane that follows focus). Phone: the top
 * screen of a drill-down (search, pills, Continue watching strip, category list);
 * [onOpenCategory] and [onOpenItem] push the category and detail screens. [onPlay]
 * opens the player with a session the TV pane's Play started (ticket 14 → 15).
 */
@Composable
fun OnDemandScreen(
    onOpenCategory: (id: String, name: String) -> Unit,
    onOpenItem: (item: OnDemandItem, backLabel: String) -> Unit,
    onPlay: (OnDemandPlayStart) -> Unit,
    viewModel: OnDemandViewModel = viewModel(
        factory = OnDemandViewModel.factory(
            LocalAppContainer.current.apiClient,
            LocalAppContainer.current.sessionController,
            LocalAppContainer.current.onDemandChanges,
            overview = true,
        ),
    ),
) {
    if (isTvDevice()) {
        val play by rememberUpdatedState(onPlay)
        LaunchedEffect(viewModel) { viewModel.detail.playStarts.collect { play(it) } }
        TvOnDemand(viewModel)
    } else {
        PhoneOnDemand(viewModel, onOpenCategory, onOpenItem)
    }
}

/** Up and Down never leave a pane (ticket 10's D-pad rules); Left and Right do. */
private fun Modifier.pane(): Modifier = this
    .focusProperties {
        onExit = {
            if (requestedFocusDirection == FocusDirection.Up || requestedFocusDirection == FocusDirection.Down) {
                cancelFocusChange()
            }
        }
    }
    .focusGroup()

@Composable
private fun TvOnDemand(viewModel: OnDemandViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val list by viewModel.list.collectAsStateWithLifecycle()
    val preview by viewModel.preview.collectAsStateWithLifecycle()
    val palette = pickerPalette()
    val rail = LocalNavRail.current

    // The row focus returns to (Back from the pane, coming back to the screen).
    var focusKey by rememberSaveable { mutableStateOf<String?>(null) }
    var seeded by remember { mutableStateOf(false) }
    var searchEditing by remember { mutableStateOf(false) }
    var paneFocused by remember { mutableStateOf(false) }
    var categoriesFocused by remember { mutableStateOf(false) }
    var listFocused by remember { mutableStateOf(false) }
    val rowFocus = remember { FocusRequester() }
    val paneFocus = remember { FocusRequester() }
    val categoryFocus = remember { FocusRequester() }

    // Back: from the pane to its row; from the categories or the list to the nav rail.
    BackHandler(enabled = paneFocused) { runCatching { rowFocus.requestFocus() } }
    BackHandler(enabled = (categoriesFocused || listFocused) && rail != null) {
        runCatching { rail?.requestFocus() }
    }

    val items = if (state.inContinue) state.continueItems.orEmpty() else list.items
    val focusTarget = items.firstOrNull { itemKey(it) == focusKey }?.let(::itemKey)
        ?: items.firstOrNull()?.let(::itemKey)
    val shown = preview.item?.takeIf { p -> items.any { itemKey(it) == itemKey(p) } } ?: items.firstOrNull()
    LaunchedEffect(shown?.let(::itemKey)) { shown?.let(viewModel::onPreviewFocus) }
    // Compose for TV does not auto-focus: seed focus on the list once it has rows.
    LaunchedEffect(items.isNotEmpty()) {
        if (!seeded && items.isNotEmpty() && !searchEditing) {
            seeded = runCatching { rowFocus.requestFocus() }.isSuccess
        }
    }

    Row(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background),
    ) {
        // ---- categories pane ----
        Column(
            modifier = Modifier
                .width(200.dp)
                .fillMaxHeight()
                .onFocusChanged { categoriesFocused = it.hasFocus }
                .padding(top = 14.dp),
        ) {
            Label(
                "On Demand",
                palette.onSurface,
                20.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.padding(start = 20.dp, bottom = 8.dp),
            )
            val entries = categoryEntries(state.categories, state.continueItems?.size, state.allCount)
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .focusProperties { onEnter = { runCatching { categoryFocus.requestFocus() } } }
                    .pane(),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                items(entries, key = { it.id }) { entry ->
                    CategoryRow(
                        entry = entry,
                        selected = entry.id == state.selected,
                        palette = palette,
                        onClick = { viewModel.onSelect(entry.id) },
                        modifier = if (entry.id == state.selected) Modifier.focusRequester(categoryFocus) else Modifier,
                    )
                }
            }
        }

        // ---- title list pane ----
        Column(
            modifier = Modifier
                .width(300.dp)
                .fillMaxHeight()
                .onFocusChanged { listFocused = it.hasFocus }
                .pane()
                .padding(top = 12.dp),
        ) {
            if (!state.inContinue) {
                SearchField(
                    query = state.search,
                    onQueryChange = viewModel::onSearchChange,
                    palette = palette,
                    placeholder = "Search titles…",
                    onEditingChange = { searchEditing = it },
                )
                SortChips(
                    shown = state.query.shownSort,
                    onSort = viewModel::onSortChange,
                    palette = palette,
                    contentPadding = PaddingValues(horizontal = ScreenGutter, vertical = 4.dp),
                )
            }
            StatusPills(state.portals, palette)
            searchHint(state.query, state.categoryName())?.let {
                Label(it, palette.muted, 11.sp, modifier = Modifier.padding(horizontal = ScreenGutter, vertical = 2.dp))
            }
            Box(modifier = Modifier.weight(1f)) {
                when {
                    state.inContinue && state.continueItems == null -> Centered { CircularProgressIndicator() }
                    state.inContinue && items.isEmpty() -> Centered { Label("Nothing in progress", palette.muted, 14.sp) }
                    !state.inContinue && list.total == null && list.error == null -> Centered { CircularProgressIndicator() }
                    !state.inContinue && list.total == 0 ->
                        Centered { Label(emptyListText(state.query, state.categoryName()), palette.muted, 14.sp) }
                    else -> LazyColumn(
                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        itemsIndexed(items, key = { _, item -> itemKey(item) }) { index, item ->
                            val key = itemKey(item)
                            TitleRow(
                                item = item,
                                palette = palette,
                                continueRow = state.inContinue,
                                selected = shown?.let(::itemKey) == key,
                                // OK (or Right) moves into the pane, onto Play.
                                onClick = { runCatching { paneFocus.requestFocus() } },
                                focusRequester = if (key == focusTarget) rowFocus else null,
                                onFocused = {
                                    focusKey = key
                                    viewModel.onPreviewFocus(item)
                                    if (!state.inContinue) viewModel.onRowFocus(index)
                                },
                                modifier = Modifier.onPreviewKeyEvent { event ->
                                    if (event.type == KeyEventType.KeyDown && event.key == Key.DirectionRight) {
                                        runCatching { paneFocus.requestFocus() }.isSuccess
                                    } else {
                                        false
                                    }
                                },
                            )
                        }
                        if (!state.inContinue) {
                            item(key = "__footer__") { ListFooter(list, palette, viewModel::retryList) }
                        }
                    }
                }
            }
        }

        // ---- preview pane ----
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxHeight()
                .onFocusChanged { paneFocused = it.hasFocus }
                .pane(),
        ) {
            if (state.error != null) {
                Centered {
                    Label(state.error.orEmpty(), MaterialTheme.colorScheme.error, 14.sp)
                    Button(onClick = viewModel::refresh) { Text("Try again") }
                }
            } else if (shown != null) {
                PreviewPane(
                    item = shown,
                    preview = preview,
                    palette = palette,
                    entry = paneFocus,
                    actions = remember(viewModel) {
                        TitleDetailActions(
                            onPlay = viewModel.detail::play,
                            onToggleWatched = viewModel.detail::toggleWatched,
                            onRetry = viewModel.detail::retry,
                            onSeason = viewModel.detail::selectSeason,
                        )
                    },
                )
            }
        }
    }
}

/**
 * The TV preview pane's body: the title's detail with Play (the [entry] focus target:
 * OK/→ on a row lands there), Season chips and Episodes. Up/Down stay in the pane.
 */
@Composable
private fun PreviewPane(
    item: OnDemandItem,
    preview: TitleDetailState,
    palette: PickerPalette,
    entry: FocusRequester,
    actions: TitleDetailActions,
) {
    // A new title starts at the top.
    val scroll = remember(itemKey(item)) { ScrollState(0) }
    TitleDetailBody(
        item = item,
        state = preview,
        palette = palette,
        actions = actions,
        tv = true,
        entry = entry,
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(horizontal = 22.dp, vertical = 16.dp),
    )
}

@Composable
private fun CategoryRow(
    entry: CategoryEntry,
    selected: Boolean,
    palette: PickerPalette,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(10.dp)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(shape)
            .background(
                when {
                    selected -> palette.accent.copy(alpha = 0.18f)
                    focused -> palette.surfaceVariant
                    else -> Color.Transparent
                },
            )
            .border(1.dp, if (focused) palette.focus else Color.Transparent, shape)
            .onFocusChanged { focused = it.isFocused }
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Label(entry.name, palette.onSurface, 14.sp, maxLines = 1, modifier = Modifier.weight(1f))
        entry.count?.let { Label(it.toString(), palette.muted, 12.sp) }
    }
}

// ---- phone ----

@Composable
private fun PhoneOnDemand(
    viewModel: OnDemandViewModel,
    onOpenCategory: (id: String, name: String) -> Unit,
    onOpenItem: (item: OnDemandItem, backLabel: String) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val list by viewModel.list.collectAsStateWithLifecycle()
    val palette = pickerPalette()
    val searching = state.query.q != null

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background)
            .safeDrawingPadding(),
    ) {
        ScreenHeader(title = "On Demand", subtitle = state.accountLabel) {
            HeaderAction(Icons.Filled.Refresh, "Refresh", viewModel::refresh)
        }
        SearchField(
            query = state.search,
            onQueryChange = viewModel::onSearchChange,
            palette = palette,
            placeholder = "Search all titles…",
        )
        StatusPills(state.portals, palette)
        searchHint(state.query, state.categoryName())?.let {
            Label(it, palette.muted, 11.sp, modifier = Modifier.padding(horizontal = ScreenGutter, vertical = 2.dp))
        }
        Box(modifier = Modifier.weight(1f)) {
            when {
                searching -> PhoneTitleList(
                    list = list,
                    emptyText = emptyListText(state.query, state.categoryName()),
                    palette = palette,
                    onRowVisible = viewModel::onRowFocus,
                    onRetry = viewModel::retryList,
                    onOpen = { onOpenItem(it, "results") },
                )
                state.loading -> Centered { CircularProgressIndicator() }
                state.error != null -> Centered {
                    Label(state.error.orEmpty(), MaterialTheme.colorScheme.error, 14.sp)
                    Button(onClick = viewModel::refresh) { Text("Try again") }
                }
                else -> LazyColumn(contentPadding = PaddingValues(bottom = 12.dp)) {
                    val continueItems = state.continueItems.orEmpty()
                    if (continueItems.isNotEmpty()) {
                        item(key = "__continue__") {
                            ContinueStrip(continueItems, palette) { onOpenItem(it, "On Demand") }
                        }
                    }
                    val entries = categoryEntries(state.categories, null, state.allCount).drop(1)
                    items(entries, key = { it.id }) { entry ->
                        PhoneCategoryRow(entry, palette) { onOpenCategory(entry.id, entry.name) }
                    }
                }
            }
        }
    }
}

/** Continue watching as a strip of wide cards with progress; hidden when empty. */
@Composable
private fun ContinueStrip(items: List<OnDemandItem>, palette: PickerPalette, onOpen: (OnDemandItem) -> Unit) {
    Column(modifier = Modifier.padding(vertical = 6.dp)) {
        Label(
            "Continue watching",
            palette.onSurface,
            15.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = ScreenGutter, vertical = 4.dp),
        )
        LazyRow(
            contentPadding = PaddingValues(horizontal = ScreenGutter),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(items, key = ::itemKey) { item ->
                TitleRow(
                    item = item,
                    palette = palette,
                    continueRow = true,
                    selected = false,
                    onClick = { onOpen(item) },
                    modifier = Modifier.width(250.dp),
                )
            }
        }
    }
}

@Composable
private fun PhoneCategoryRow(entry: CategoryEntry, palette: PickerPalette, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = ScreenGutter, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Label(entry.name, palette.onSurface, 15.sp, maxLines = 1, modifier = Modifier.weight(1f))
        entry.count?.let { Label(it.toString(), palette.muted, 12.sp) }
        Label("›", palette.muted, 18.sp, modifier = Modifier.padding(start = 10.dp))
    }
}

/** A phone title list with infinite scroll: the next page loads as the end comes into view. */
@Composable
internal fun PhoneTitleList(
    list: TitleListState,
    emptyText: String,
    palette: PickerPalette,
    onRowVisible: (Int) -> Unit,
    onRetry: () -> Unit,
    onOpen: (OnDemandItem) -> Unit,
) {
    when {
        list.total == null && list.error == null -> Centered { CircularProgressIndicator() }
        list.total == 0 -> Centered { Label(emptyText, palette.muted, 14.sp) }
        else -> {
            val listState = rememberLazyListState()
            LaunchedEffect(listState) {
                snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
                    .distinctUntilChanged()
                    .collect(onRowVisible)
            }
            LazyColumn(
                state = listState,
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                items(list.items, key = ::itemKey) { item ->
                    TitleRow(
                        item = item,
                        palette = palette,
                        continueRow = false,
                        selected = false,
                        onClick = { onOpen(item) },
                    )
                }
                item(key = "__footer__") { ListFooter(list, palette, onRetry) }
            }
        }
    }
}
