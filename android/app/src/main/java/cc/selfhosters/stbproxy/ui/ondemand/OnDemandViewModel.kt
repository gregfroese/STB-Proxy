package cc.selfhosters.stbproxy.ui.ondemand

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.OnDemandChanges
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.SessionState
import cc.selfhosters.stbproxy.data.model.OnDemandCategory
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandPortalStatus
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The browse screen's state, apart from the title list (see [OnDemandViewModel.list]). */
data class OnDemandUiState(
    val loading: Boolean = true,
    val error: String? = null,
    val categories: List<OnDemandCategory> = emptyList(),
    val portals: List<OnDemandPortalStatus> = emptyList(),
    /** Continue watching; null until loaded. */
    val continueItems: List<OnDemandItem>? = null,
    /** All's count, learnt from the first unsearched All page. */
    val allCount: Int? = null,
    /** The categories pane's selection: [CONTINUE_ID], [ALL_ID] or a category id. */
    val selected: String = ALL_ID,
    val search: String = "",
    val sort: OnDemandSort? = null,
    val accountLabel: String? = null,
) {
    val inContinue: Boolean get() = selected == CONTINUE_ID
    val query: ListQuery get() = listQuery(selected, search, sort)

    fun categoryName(id: String = selected): String = when (id) {
        ALL_ID -> "All"
        CONTINUE_ID -> "Continue watching"
        else -> categories.firstOrNull { it.id == id }?.name ?: id
    }
}

/**
 * On Demand browse (ticket 13). One instance drives the TV three panes or the phone's
 * top screen ([overview] = true: categories, status and Continue watching), and one per
 * phone category screen ([overview] = false, fixed [category]).
 *
 * Errors: a 401 drops to Login; a 404 `on_demand_off` has already switched On Demand
 * off app-wide (in [ApiClient]), and the shell leaves these screens.
 *
 * When a title's viewer state changes ([OnDemandChanges]: back from the player, Mark
 * watched), its row, the preview pane and Continue watching are refetched.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OnDemandViewModel(
    private val api: ApiClient,
    private val session: SessionController,
    changes: OnDemandChanges,
    private val overview: Boolean,
    category: String = ALL_ID,
) : ViewModel() {

    private val _state = MutableStateFlow(
        OnDemandUiState(
            selected = category,
            accountLabel = (session.state.value as? SessionState.LoggedIn)?.accountLabel,
            loading = overview,
        ),
    )
    val state: StateFlow<OnDemandUiState> = _state.asStateFlow()

    private val pager = MutableStateFlow(newPager(_state.value.query))
    private var pagerJob: Job? = null

    /** The current query's title list. */
    val list: StateFlow<TitleListState> = pager
        .flatMapLatest { it.state }
        .stateIn(viewModelScope, SharingStarted.Eagerly, TitleListState())

    /** The TV preview pane: Play, Seasons and Episodes of the focused title. */
    val detail = TitleDetailController(api, viewModelScope, changes, session::reportUnauthorized)
    val preview: StateFlow<TitleDetailState> get() = detail.state

    init {
        if (overview) refreshOverview()
        loadPage()
        viewModelScope.launch { changes.changes.collect(::onTitleChanged) }
    }

    /** [key]'s viewer state changed: refetch its row, the pane (if showing it) and Continue watching. */
    private fun onTitleChanged(key: String) {
        refreshContinue()
        detail.refresh(key)
        val listed = pager.value.state.value.items.firstOrNull { itemKey(it) == key } ?: return
        viewModelScope.launch {
            guarded(onError = {}) {
                pager.value.replace(api.fetchOnDemandItem(listed.portal, listed.id).asItem())
            }
        }
    }

    /** Categories, portal status and Continue watching (the overview), then the list. */
    fun refresh() {
        if (overview) refreshOverview()
        restartList()
    }

    private fun refreshOverview() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            guarded(onError = { message -> _state.update { it.copy(loading = false, error = message) } }) {
                val result = api.fetchOnDemandCategories()
                _state.update {
                    it.copy(
                        loading = false,
                        categories = result.categories,
                        portals = result.portals,
                        // A selected category that has gone falls back to All.
                        selected = it.selected.takeIf { id ->
                            id == ALL_ID || id == CONTINUE_ID || result.categories.any { c -> c.id == id }
                        } ?: ALL_ID,
                    )
                }
            }
        }
        refreshContinue()
    }

    /** Continue watching again (after playback, say). */
    fun refreshContinue() {
        if (!overview) return
        viewModelScope.launch {
            guarded(onError = {}) {
                val items = api.fetchOnDemandContinue()
                _state.update { it.copy(continueItems = items) }
            }
        }
    }

    fun onSelect(id: String) {
        if (id == _state.value.selected) return
        _state.update { it.copy(selected = id, sort = null) }
        restartList()
    }

    fun onSearchChange(text: String) {
        val before = _state.value.query
        _state.update { it.copy(search = text) }
        if (_state.value.query != before) restartList()
    }

    fun onSortChange(sort: OnDemandSort) {
        _state.update { it.copy(sort = sort) }
        restartList()
    }

    /** A title row (or the last visible row) at [index] has focus: page on when near the end. */
    fun onRowFocus(index: Int) {
        viewModelScope.launch { pager.value.onFocus(index) }
    }

    fun retryList() {
        viewModelScope.launch { guardedPager { pager.value.retry() } }
    }

    fun focusIndexOf(key: String?): Int = pager.value.indexOf(key)

    /**
     * The TV preview pane follows focus: the row shows at once, and its details (for a
     * Series, its Seasons, then Episodes) are asked for only once focus has stayed
     * [PREVIEW_SETTLE_MS], so walking the list doesn't fire a request per row.
     */
    fun onPreviewFocus(item: OnDemandItem) = detail.show(item, PREVIEW_SETTLE_MS)

    private fun restartList() {
        pagerJob?.cancel()
        pager.value = newPager(_state.value.query)
        loadPage()
    }

    private fun loadPage() {
        if (_state.value.inContinue) return
        pagerJob = viewModelScope.launch { guardedPager { pager.value.loadMore() } }
    }

    private fun newPager(query: ListQuery): TitlePager = TitlePager({ offset, limit ->
        api.fetchOnDemandItems(query.category, query.q, query.sort?.param, offset, limit).also { page ->
            if (offset == 0 && query.category == null && query.q == null) {
                _state.update { it.copy(allCount = page.total) }
            }
        }
    })

    /** The pager keeps its own error; a 401 still drops to Login. */
    private suspend fun guardedPager(block: suspend () -> Unit) {
        block()
        (pager.value.state.value.error as? ApiException)?.let { if (it.code == 401) session.reportUnauthorized() }
    }

    private suspend fun guarded(onError: (String) -> Unit, block: suspend () -> Unit) {
        try {
            block()
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: ApiException) {
            if (e.code == 401) session.reportUnauthorized()
            onError(loadErrorText(e))
        } catch (e: Exception) {
            onError(loadErrorText(e))
        }
    }

    companion object {
        fun factory(
            api: ApiClient,
            session: SessionController,
            changes: OnDemandChanges,
            overview: Boolean,
            category: String = ALL_ID,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer { OnDemandViewModel(api, session, changes, overview, category) }
        }
    }
}
