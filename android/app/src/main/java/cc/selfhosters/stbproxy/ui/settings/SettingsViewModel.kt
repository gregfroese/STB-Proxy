package cc.selfhosters.stbproxy.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.AccountStore
import cc.selfhosters.stbproxy.data.ConnectOutcome
import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.ViewerPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** State of the Settings screen: the URL, the accounts and an add/re-auth form (spec 2.4). */
data class SettingsUiState(
    val baseUrl: String = "",
    val accounts: List<String> = emptyList(),
    val activeUsername: String? = null,
    val addUsername: String = "",
    val addPassword: String = "",
    val groupMode: GroupMode = GroupMode.BLOCKS,
    val busy: Boolean = false,
    val message: String? = null,
    val error: String? = null,
)

/**
 * Edits the proxy URL and the account list. Adding an account re-runs the same
 * *Connect* probe as the login form (via [SessionController.connect]).
 */
class SettingsViewModel(
    private val session: SessionController,
    private val store: AccountStore,
    private val viewerPreferences: ViewerPreferences,
) : ViewModel() {

    private val _state = MutableStateFlow(
        SettingsUiState(
            baseUrl = store.state.value.baseUrl.orEmpty(),
            groupMode = viewerPreferences.groupMode.value,
        ),
    )
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            store.state.collect { accounts ->
                _state.update {
                    it.copy(
                        accounts = accounts.usernames,
                        activeUsername = accounts.activeUsername,
                    )
                }
            }
        }
        viewModelScope.launch {
            viewerPreferences.groupMode.collect { mode ->
                _state.update { it.copy(groupMode = mode) }
            }
        }
    }

    fun onBaseUrlChange(value: String) =
        _state.update { it.copy(baseUrl = value, error = null, message = null) }

    fun onAddUsernameChange(value: String) =
        _state.update { it.copy(addUsername = value, error = null, message = null) }

    fun onAddPasswordChange(value: String) =
        _state.update { it.copy(addPassword = value, error = null, message = null) }

    fun saveBaseUrl() {
        val current = _state.value
        if (current.baseUrl.isBlank()) {
            _state.update { it.copy(error = "Enter a proxy address") }
            return
        }
        try {
            store.setBaseUrl(current.baseUrl)
            _state.update {
                it.copy(
                    baseUrl = store.state.value.baseUrl.orEmpty(),
                    message = "Address saved",
                    error = null,
                )
            }
        } catch (e: IllegalArgumentException) {
            _state.update { it.copy(error = e.message ?: "Invalid address") }
        }
    }

    fun addAccount() {
        val current = _state.value
        if (current.baseUrl.isBlank()) {
            _state.update { it.copy(error = "Enter a proxy address") }
            return
        }
        if (current.addUsername.isBlank() || current.addPassword.isBlank()) {
            _state.update { it.copy(error = "Enter a username and password") }
            return
        }
        _state.update { it.copy(busy = true, error = null, message = null) }
        viewModelScope.launch {
            when (val outcome = session.connect(current.baseUrl, current.addUsername.trim(), current.addPassword)) {
                ConnectOutcome.Connected -> _state.update {
                    it.copy(
                        busy = false,
                        addUsername = "",
                        addPassword = "",
                        message = "Account added",
                    )
                }
                is ConnectOutcome.Failed ->
                    _state.update { it.copy(busy = false, error = outcome.message) }
            }
        }
    }

    fun switchTo(username: String) {
        if (username == _state.value.activeUsername) return
        _state.update { it.copy(busy = true, error = null, message = null) }
        viewModelScope.launch {
            when (val outcome = session.switchTo(username)) {
                ConnectOutcome.Connected ->
                    _state.update { it.copy(busy = false, message = "Switched to $username") }
                is ConnectOutcome.Failed ->
                    _state.update { it.copy(busy = false, error = outcome.message) }
            }
        }
    }

    fun remove(username: String) {
        store.removeAccount(username)
        _state.update { it.copy(message = "Removed $username") }
    }

    /** Persist the picker's grouping preference; screens pick the change up live. */
    fun setGroupMode(mode: GroupMode) = viewerPreferences.setGroupMode(mode)

    fun signOut() = session.signOut()

    companion object {
        fun factory(
            session: SessionController,
            store: AccountStore,
            viewerPreferences: ViewerPreferences,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer { SettingsViewModel(session, store, viewerPreferences) }
        }
    }
}
