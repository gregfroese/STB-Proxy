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

data class PickerUiState(
    val loading: Boolean = false,
    val blocks: List<String> = listOf("Other"),
    val channels: List<Channel> = emptyList(),
    val error: String? = null,
)

/**
 * ViewModel scaffolding: state is exposed as a [StateFlow] to Compose. The real
 * `/api/lineup` fetch arrives with the picker ticket; the manual-DI factory is
 * wired now so the seam exists.
 */
class PickerViewModel(
    private val apiClient: ApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow(PickerUiState())
    val state: StateFlow<PickerUiState> = _state.asStateFlow()

    fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            // Placeholder: fetchLineup() is wired in a later ticket.
            _state.update { it.copy(loading = false) }
        }
    }

    companion object {
        fun factory(apiClient: ApiClient): ViewModelProvider.Factory = viewModelFactory {
            initializer { PickerViewModel(apiClient) }
        }
    }
}
