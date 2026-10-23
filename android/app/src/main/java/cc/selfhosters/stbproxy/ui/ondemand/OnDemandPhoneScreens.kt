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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.network.ApiException
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.ScreenGutter
import cc.selfhosters.stbproxy.ui.picker.PickerPalette
import cc.selfhosters.stbproxy.ui.picker.SearchField
import cc.selfhosters.stbproxy.ui.picker.pickerPalette
import kotlinx.coroutines.CancellationException

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
 * Phone: a title's full-screen detail page, "‹ Back to <category|results>". Ticket 14
 * adds Play / Resume / Start over / Mark watched, inline errors and Seasons/Episodes.
 */
@Composable
fun OnDemandItemScreen(
    portal: String,
    id: String,
    backLabel: String,
    onBack: () -> Unit,
) {
    val container = LocalAppContainer.current
    var attempt by remember { mutableIntStateOf(0) }
    val result by produceState<Result<OnDemandDetail>?>(null, portal, id, attempt) {
        value = try {
            Result.success(container.apiClient.fetchOnDemandItem(portal, id))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (e is ApiException && e.code == 401) container.sessionController.reportUnauthorized()
            Result.failure(e)
        }
    }
    val palette = pickerPalette()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background)
            .safeDrawingPadding(),
    ) {
        BackLink("‹ Back to $backLabel", palette, onBack)
        val loaded = result
        when {
            loaded == null -> Centered { CircularProgressIndicator() }
            loaded.isFailure -> Centered {
                Label(
                    loadErrorText(loaded.exceptionOrNull() as? Exception ?: Exception()),
                    MaterialTheme.colorScheme.error,
                    14.sp,
                )
                Button(onClick = { attempt++ }) { Text("Try again") }
            }
            else -> {
                val detail = loaded.getOrThrow()
                TitleSummary(
                    item = detail.asItem(),
                    detail = detail,
                    palette = palette,
                    modifier = Modifier
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = ScreenGutter, vertical = 8.dp),
                    posterWidth = 110.dp,
                )
            }
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
