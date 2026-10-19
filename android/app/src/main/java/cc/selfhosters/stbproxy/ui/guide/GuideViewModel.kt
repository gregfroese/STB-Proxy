package cc.selfhosters.stbproxy.ui.guide

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.ViewerPreferences
import cc.selfhosters.stbproxy.data.epg.EpgRepository
import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.model.GuideHit
import cc.selfhosters.stbproxy.data.model.GuideProgramme
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import cc.selfhosters.stbproxy.data.network.OPERATOR_LABEL
import cc.selfhosters.stbproxy.ui.picker.effectiveGroupMode
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Everything the Guide screen renders (tickets 04/05/09): the account's lineup and
 * now/next teaser, the search box / filters, the server search results, and the
 * inline per-channel timelines.
 */
data class GuideUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val blocks: List<String> = emptyList(),
    val channels: List<Channel> = emptyList(),
    val nowNext: Map<String, NowNext> = emptyMap(),
    val groupMode: GroupMode = GroupMode.BLOCKS,
    val query: String = "",
    val mode: GuideMode = GuideMode.PREFIX,
    val advanced: Boolean = false,
    val onNow: Boolean = false,
    val channelFilter: String = "",
    val activeBlock: String? = null,
    val limit: Int = GUIDE_LIMIT_DEFAULT,
    val searchLoading: Boolean = false,
    val results: List<GuideHit> = emptyList(),
    val total: Int = 0,
    val searchError: String? = null,
    val notice: String? = null,
    val accountLabel: String? = null,
    val openKey: String? = null,
    val timelines: Map<String, List<GuideProgramme>> = emptyMap(),
    val timelineLoading: Map<String, Boolean> = emptyMap(),
) {
    val searching: Boolean get() = query.isNotBlank()
}

/**
 * Drives the account-scoped Guide (ADR 0002): loads the lineup, debounces Guide
 * search, and loads one channel's timeline on demand. A mid-session 401 drops the
 * app back to Login via the [SessionController].
 */
class GuideViewModel(
    private val apiClient: ApiClient,
    private val epgRepository: EpgRepository,
    private val session: SessionController,
    private val viewerPreferences: ViewerPreferences,
) : ViewModel() {

    private val _state = MutableStateFlow(GuideUiState(groupMode = viewerPreferences.groupMode.value))
    val state: StateFlow<GuideUiState> = _state.asStateFlow()

    private var searchJob: Job? = null

    init {
        refresh()
        viewModelScope.launch {
            viewerPreferences.groupMode.collect { mode -> _state.update { it.copy(groupMode = mode) } }
        }
    }

    fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            try {
                val lineup = apiClient.fetchLineup()
                val mode = effectiveGroupMode(viewerPreferences.groupMode.value, lineup.blocks)
                _state.update {
                    it.copy(
                        loading = false,
                        error = null,
                        blocks = lineup.blocks,
                        channels = lineup.channels,
                        groupMode = mode,
                        accountLabel = lineup.account ?: OPERATOR_LABEL,
                    )
                }
                refreshEpg()
            } catch (e: ApiException) {
                if (e.code == 401) session.reportUnauthorized()
                _state.update { it.copy(loading = false, error = "Failed to load channels (HTTP ${e.code})") }
            } catch (e: Exception) {
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load channels") }
            }
        }
    }

    /** Best-effort now/next refresh; failures keep the previous teaser. */
    fun refreshEpg() {
        viewModelScope.launch {
            val map = epgRepository.fetch()
            if (map.isNotEmpty()) _state.update { it.copy(nowNext = map) }
        }
    }

    fun onQueryChange(query: String) {
        _state.update { it.copy(query = query) }
        scheduleSearch()
    }

    fun onModeChange(mode: GuideMode) {
        _state.update { it.copy(mode = mode) }
        scheduleSearch()
    }

    fun onToggleAdvanced() {
        _state.update { it.copy(advanced = !it.advanced) }
    }

    fun onOnNowChange(onNow: Boolean) {
        _state.update { it.copy(onNow = onNow) }
        scheduleSearch()
    }

    fun onChannelFilterChange(text: String) {
        _state.update { it.copy(channelFilter = text) }
        scheduleSearch()
    }

    /** Block navigation is suspended while searching (spec 2.5). */
    fun onBlockSelected(block: String) {
        _state.update { if (it.query.isBlank()) it.copy(activeBlock = block) else it }
    }

    fun onLoadMore() {
        _state.update { it.copy(limit = nextGuideLimit(it.limit)) }
        scheduleSearch(immediate = true)
    }

    /** Re-run the search (or refresh the browse teaser); clears open timelines. */
    fun reload() {
        _state.update { it.copy(openKey = null, timelines = emptyMap()) }
        if (_state.value.searching) scheduleSearch(immediate = true) else refreshEpg()
    }

    private fun scheduleSearch(immediate: Boolean = false) {
        searchJob?.cancel()
        if (!_state.value.searching) {
            _state.update { it.copy(results = emptyList(), total = 0, searchError = null, searchLoading = false) }
            return
        }
        searchJob = viewModelScope.launch {
            if (!immediate) delay(GUIDE_DEBOUNCE_MS)
            performSearch()
        }
    }

    private fun performSearch() {
        val s = _state.value
        _state.update { it.copy(searchLoading = true, searchError = null) }
        viewModelScope.launch {
            try {
                val result = apiClient.fetchGuideSearch(
                    query = s.query.trim(),
                    mode = s.mode.wire,
                    onNow = s.onNow,
                    channel = s.channelFilter.trim(),
                    limit = s.limit,
                )
                _state.update {
                    it.copy(
                        searchLoading = false,
                        searchError = null,
                        results = result.results,
                        total = result.total,
                        notice = guideNotice(result.failed, result.partial),
                    )
                }
            } catch (e: ApiException) {
                if (e.code == 401) session.reportUnauthorized()
                _state.update { it.copy(searchLoading = false, searchError = searchErrorMessage(e.code)) }
            } catch (e: Exception) {
                _state.update { it.copy(searchLoading = false, searchError = e.message ?: "Search failed") }
            }
        }
    }

    /** Expands [channel]'s inline timeline, loading it once. */
    fun toggleTimeline(channel: Channel) {
        val key = channelKey(channel)
        if (_state.value.openKey == key) {
            _state.update { it.copy(openKey = null) }
            return
        }
        _state.update { it.copy(openKey = key) }
        if (_state.value.timelines.containsKey(key)) return
        _state.update { it.copy(timelineLoading = it.timelineLoading + (key to true)) }
        viewModelScope.launch {
            val programmes = try {
                apiClient.fetchGuideChannel(channel.portal, channel.channelId).programmes
            } catch (e: Exception) {
                emptyList()
            }
            _state.update {
                it.copy(
                    timelines = it.timelines + (key to programmes),
                    timelineLoading = it.timelineLoading - key,
                )
            }
        }
    }

    companion object {
        fun searchErrorMessage(code: Int): String = when (code) {
            400 -> "That search pattern isn't valid."
            404 -> "That channel isn't in your lineup."
            else -> "Search failed (HTTP $code)"
        }

        fun factory(
            apiClient: ApiClient,
            epgRepository: EpgRepository,
            session: SessionController,
            viewerPreferences: ViewerPreferences,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer { GuideViewModel(apiClient, epgRepository, session, viewerPreferences) }
        }
    }
}
