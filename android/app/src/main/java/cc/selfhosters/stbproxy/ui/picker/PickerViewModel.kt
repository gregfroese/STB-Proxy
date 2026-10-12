package cc.selfhosters.stbproxy.ui.picker

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.network.ApiClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Loading / loaded / error state for the channel list. While [loading] is true the
 * fetch is in flight; once it settles exactly one of [error] (message) or the
 * loaded [channels] / [blocks] applies.
 */
data class PickerUiState(
    val loading: Boolean = false,
    val blocks: List<String> = emptyList(),
    val channels: List<Channel> = emptyList(),
    val error: String? = null,
)

/**
 * Drives `GET /api/lineup` through the manual-DI [ApiClient] and exposes the
 * result as a [StateFlow] (spec 2.2/2.3). The full Block-grouped picker UX lands
 * in a later ticket; this is the walking skeleton that proves the data layer.
 */
class PickerViewModel(
    private val apiClient: ApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow(PickerUiState())
    val state: StateFlow<PickerUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            try {
                val lineup = apiClient.fetchLineup()
                _state.update {
                    it.copy(
                        loading = false,
                        blocks = lineup.blocks,
                        channels = lineup.channels,
                        error = null,
                    )
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(loading = false, error = e.message ?: "Failed to load channels")
                }
            }
        }
    }

    companion object {
        fun factory(apiClient: ApiClient): ViewModelProvider.Factory = viewModelFactory {
            initializer { PickerViewModel(apiClient) }
        }
    }
}
