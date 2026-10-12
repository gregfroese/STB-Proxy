package cc.selfhosters.stbproxy.ui.picker

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.SessionState
import cc.selfhosters.stbproxy.data.epg.EpgRepository
import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import cc.selfhosters.stbproxy.data.network.OPERATOR_LABEL
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Loading / loaded / error state for the Block-grouped picker. [query] and
 * [activeBlock] are the user's search text and selected rail entry; [nowNext]
 * is the best-effort EPG teaser map keyed by `epgId`.
 */
data class PickerUiState(
    val loading: Boolean = false,
    val blocks: List<String> = emptyList(),
    val channels: List<Channel> = emptyList(),
    val nowNext: Map<String, NowNext> = emptyMap(),
    val query: String = "",
    val activeBlock: String? = null,
    val filter: ChannelFilter = ChannelFilter.ALL,
    val error: String? = null,
    val accountLabel: String? = null,
    val credentialsUnverified: Boolean = false,
)

/**
 * Drives `GET /api/lineup` and `GET /xmltv` through the manual-DI clients and
 * exposes the result as a [StateFlow] (spec 2.2/2.3). A mid-session 401 is
 * reported to the [SessionController], which drops the app back to Login.
 */
class PickerViewModel(
    private val apiClient: ApiClient,
    private val epgRepository: EpgRepository,
    private val session: SessionController,
) : ViewModel() {

    private val _state = MutableStateFlow(PickerUiState())
    val state: StateFlow<PickerUiState> = _state.asStateFlow()

    init {
        refresh()
        // Switching accounts changes the lineup: reload whenever the active account changes.
        viewModelScope.launch {
            session.state
                .map { (it as? SessionState.LoggedIn)?.accountLabel }
                .distinctUntilChanged()
                .drop(1)
                .collect { refresh() }
        }
    }

    fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            try {
                val lineup = apiClient.fetchLineup()
                val rail = blockRail(lineup.blocks, lineup.channels)
                _state.update {
                    it.copy(
                        loading = false,
                        blocks = lineup.blocks,
                        channels = lineup.channels,
                        error = null,
                        accountLabel = lineup.account ?: OPERATOR_LABEL,
                        credentialsUnverified = lineup.account == null && session.hasCredentials(),
                        activeBlock = it.activeBlock
                            ?.takeIf { block -> rail.any { entry -> entry.name == block } }
                            ?: rail.firstOrNull()?.name,
                    )
                }
                refreshEpg()
            } catch (e: ApiException) {
                if (e.code == 401) session.reportUnauthorized()
                _state.update {
                    it.copy(loading = false, error = "Failed to load channels (HTTP ${e.code})")
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(loading = false, error = e.message ?: "Failed to load channels")
                }
            }
        }
    }

    /** Best-effort now/next refresh; failures leave the teaser empty. */
    fun refreshEpg() {
        viewModelScope.launch {
            val nowNext = epgRepository.fetch()
            _state.update { it.copy(nowNext = nowNext) }
        }
    }

    fun onQueryChange(query: String) {
        _state.update { it.copy(query = query) }
    }

    /** Block navigation is suspended while searching (spec 2.5). */
    fun onBlockSelected(block: String) {
        _state.update { if (it.query.isBlank()) it.copy(activeBlock = block) else it }
    }

    /** Show all channels, only overall favourites, or only block favourites. */
    fun onFilterChange(filter: ChannelFilter) {
        _state.update { it.copy(filter = filter) }
    }

    companion object {
        fun factory(
            apiClient: ApiClient,
            epgRepository: EpgRepository,
            session: SessionController,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer { PickerViewModel(apiClient, epgRepository, session) }
        }
    }
}
