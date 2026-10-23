package cc.selfhosters.stbproxy.ui.ondemand

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.OnDemandChanges
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.ScreenGutter
import cc.selfhosters.stbproxy.ui.picker.PickerPalette
import cc.selfhosters.stbproxy.ui.picker.SearchField
import cc.selfhosters.stbproxy.ui.picker.pickerPalette
import kotlinx.coroutines.launch

/**
 * Phone: one category's titles, below the On Demand screen. "‹ On Demand", the
 * category's name, a search scoped to it, the sort chips and an infinite list. The
 * bottom nav is hidden here (it isn't a top-level destination).
 */
@Composable
fun OnDemandCategoryScreen(
    category: String,
    name: String,
    onBack: () -> Unit,
    onOpenItem: (item: OnDemandItem, backLabel: String) -> Unit,
) {
    val container = LocalAppContainer.current
    val viewModel: OnDemandViewModel = viewModel(
        key = "ondemand-category:$category",
        factory = OnDemandViewModel.factory(
            container.apiClient,
            container.sessionController,
            container.onDemandChanges,
            overview = false,
            category = category,
        ),
    )
    val state by viewModel.state.collectAsStateWithLifecycle()
    val list by viewModel.list.collectAsStateWithLifecycle()
    val palette = pickerPalette()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background)
            .safeDrawingPadding(),
    ) {
        BackLink("‹ On Demand", palette, onBack)
        Label(
            name,
            palette.onSurface,
            22.sp,
            fontWeight = FontWeight.Medium,
            maxLines = 1,
            modifier = Modifier.padding(horizontal = ScreenGutter, vertical = 4.dp),
        )
        SearchField(
            query = state.search,
            onQueryChange = viewModel::onSearchChange,
            palette = palette,
            placeholder = "Search $name…",
        )
        SortChips(shown = state.query.shownSort, onSort = viewModel::onSortChange, palette = palette)
        searchHint(state.query, name)?.let {
            Label(it, palette.muted, 11.sp, modifier = Modifier.padding(horizontal = ScreenGutter, vertical = 2.dp))
        }
        Box(modifier = Modifier.weight(1f)) {
            PhoneTitleList(
                list = list,
                emptyText = emptyListText(state.query, name),
                palette = palette,
                onRowVisible = viewModel::onRowFocus,
                onRetry = viewModel::retryList,
                onOpen = { onOpenItem(it, name) },
            )
        }
    }
}

/**
 * The phone detail page's state: one title's [TitleDetailController], refetched when
 * its viewer state changes (back from the player, Mark watched).
 */
class OnDemandDetailViewModel(
    api: ApiClient,
    session: SessionController,
    changes: OnDemandChanges,
    private val portal: String,
    private val id: String,
) : ViewModel() {

    val detail = TitleDetailController(api, viewModelScope, changes, session::reportUnauthorized)

    init {
        detail.load(portal, id)
        viewModelScope.launch { changes.changes.collect(detail::refresh) }
    }

    /** Try again after the page failed to load. */
    fun reload() = detail.load(portal, id)

    companion object {
        fun factory(
            api: ApiClient,
            session: SessionController,
            changes: OnDemandChanges,
            portal: String,
            id: String,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer { OnDemandDetailViewModel(api, session, changes, portal, id) }
        }
    }
}

/**
 * Phone: a title's full-screen detail page, "‹ Back to <category|results>": the
 * poster, title and facts, a full-width Play/Resume with Start over and Mark watched,
 * inline errors, a Series' Season chips and Episodes, then the description, genre
 * tags, credits and "From <portal>". [onPlay] opens the player with the started
 * session (ticket 15).
 */
@Composable
fun OnDemandItemScreen(
    portal: String,
    id: String,
    backLabel: String,
    onBack: () -> Unit,
    onPlay: (OnDemandPlayStart) -> Unit,
) {
    val container = LocalAppContainer.current
    val viewModel: OnDemandDetailViewModel = viewModel(
        key = "ondemand-item:$portal/$id",
        factory = OnDemandDetailViewModel.factory(
            container.apiClient,
            container.sessionController,
            container.onDemandChanges,
            portal,
            id,
        ),
    )
    val state by viewModel.detail.state.collectAsStateWithLifecycle()
    val play by rememberUpdatedState(onPlay)
    LaunchedEffect(viewModel) { viewModel.detail.playStarts.collect { play(it) } }
    val palette = pickerPalette()
    val actions = remember(viewModel) {
        TitleDetailActions(
            onPlay = viewModel.detail::play,
            onToggleWatched = viewModel.detail::toggleWatched,
            onRetry = viewModel.detail::retry,
            onSeason = viewModel.detail::selectSeason,
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background)
            .safeDrawingPadding(),
    ) {
        BackLink("‹ Back to $backLabel", palette, onBack)
        val item = state.item
        when {
            item != null -> TitleDetailBody(
                item = item,
                state = state,
                palette = palette,
                actions = actions,
                tv = false,
                posterWidth = 110.dp,
                modifier = Modifier
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = ScreenGutter, vertical = 8.dp),
            )
            state.loadError != null -> Centered {
                Label(state.loadError.orEmpty(), MaterialTheme.colorScheme.error, 14.sp)
                Button(onClick = viewModel::reload) { Text("Try again") }
            }
            else -> Centered { CircularProgressIndicator() }
        }
    }
}

@Composable
private fun BackLink(text: String, palette: PickerPalette, onBack: () -> Unit) {
    Label(
        text,
        palette.accent,
        14.sp,
        maxLines = 1,
        modifier = Modifier
            .clickable(onClick = onBack)
            .padding(horizontal = ScreenGutter, vertical = 12.dp),
    )
}

/** A detail as the list item it extends. */
internal fun OnDemandDetail.asItem(): OnDemandItem = OnDemandItem(
    portal = portal,
    id = id,
    kind = kind,
    name = name,
    portalName = portalName,
    year = year,
    rating = rating,
    added = added,
    poster = poster,
    progress = progress,
    upNext = upNext,
)
