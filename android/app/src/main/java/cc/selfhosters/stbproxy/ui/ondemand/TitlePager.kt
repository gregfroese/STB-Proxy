package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandPage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/**
 * One title list as loaded so far. [total] is null until the first page answers;
 * [fetched] is the server-side offset reached (rows asked for, duplicates included).
 */
data class TitleListState(
    val items: List<OnDemandItem> = emptyList(),
    val total: Int? = null,
    val fetched: Int = 0,
    val loading: Boolean = false,
    val error: Exception? = null,
) {
    val complete: Boolean get() = total != null && fetched >= total

    /** The list's last row: "Loading more… (n of total)", then "n titles". */
    val footer: String? get() = total?.let { footerText(items.size, if (complete) items.size else it) }
}

/**
 * Pages one title list (`offset`/`limit` [pageSize]) for one query. Rows are only
 * ever appended, keyed by [itemKey] (a title already listed is skipped), so a row
 * keeps its index and TV focus stays on it as pages arrive.
 *
 * Calls are expected on one thread (the main dispatcher): the loading flag is set
 * before the fetch suspends, so overlapping calls fetch once.
 */
class TitlePager(
    private val fetch: suspend (offset: Int, limit: Int) -> OnDemandPage,
    private val pageSize: Int = PAGE_SIZE,
) {
    private val _state = MutableStateFlow(TitleListState())
    val state: StateFlow<TitleListState> = _state.asStateFlow()

    /** Fetches the next page, unless one is loading or the list is complete. */
    suspend fun loadMore() {
        val current = _state.value
        if (current.loading || current.complete) return
        _state.value = current.copy(loading = true, error = null)
        try {
            val page = fetch(current.fetched, pageSize)
            _state.update { state ->
                val seen = state.items.mapTo(HashSet(), ::itemKey)
                val items = state.items + page.items.filter { seen.add(itemKey(it)) }
                val fetched = state.fetched + page.items.size
                // An empty page ends the list whatever the total said (the catalogue shrank).
                val total = if (page.items.isEmpty()) fetched else maxOf(page.total, fetched)
                state.copy(items = items, total = total, fetched = fetched, loading = false)
            }
        } catch (e: CancellationException) {
            _state.update { it.copy(loading = false) }
            throw e
        } catch (e: Exception) {
            _state.update { it.copy(loading = false, error = e) }
        }
    }

    /** Focus (or the last visible row) is at [index]: fetch on when near the end. */
    suspend fun onFocus(index: Int) {
        val state = _state.value
        if (state.error != null || state.complete) return
        if (shouldLoadMore(index, state.items.size, state.total, state.loading)) loadMore()
    }

    /** Tries again after a failure. */
    suspend fun retry() {
        _state.update { it.copy(error = null) }
        loadMore()
    }

    /** The row a focus key names, else the first. */
    fun indexOf(key: String?): Int =
        _state.value.items.indexOfFirst { itemKey(it) == key }.coerceAtLeast(0)
}
