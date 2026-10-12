package cc.selfhosters.stbproxy.ui.picker

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import cc.selfhosters.stbproxy.data.network.OPERATOR_LABEL
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Loading / loaded / error state for the channel list. [accountLabel] is the
 * session label from the lineup (`account`, or the operator wording) and
 * [credentialsUnverified] flags a security-off session.
 */
data class PickerUiState(
    val loading: Boolean = false,
    val blocks: List<String> = emptyList(),
    val channels: List<Channel> = emptyList(),
    val error: String? = null,
    val accountLabel: String? = null,
    val credentialsUnverified: Boolean = false,
)

/**
 * Drives `GET /api/lineup` through the manual-DI [ApiClient] and exposes the
 * result as a [StateFlow] (spec 2.2/2.3). A mid-session 401 is reported to the
 * [SessionController], which drops the app back to Login.
 */
class PickerViewModel(
    private val apiClient: ApiClient,
    private val session: SessionController,
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
                        accountLabel = lineup.account ?: OPERATOR_LABEL,
                        credentialsUnverified = lineup.account == null && session.hasCredentials(),
                    )
                }
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

    companion object {
        fun factory(apiClient: ApiClient, session: SessionController): ViewModelProvider.Factory =
            viewModelFactory {
                initializer { PickerViewModel(apiClient, session) }
            }
    }
}
