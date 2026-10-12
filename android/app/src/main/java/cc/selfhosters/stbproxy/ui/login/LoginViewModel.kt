package cc.selfhosters.stbproxy.ui.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.AccountStore
import cc.selfhosters.stbproxy.data.ConnectOutcome
import cc.selfhosters.stbproxy.data.SessionController
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Fields + status of the Login / Connect form (spec 2.4). */
data class LoginUiState(
    val baseUrl: String = "",
    val username: String = "",
    val password: String = "",
    val connecting: Boolean = false,
    val error: String? = null,
)

/**
 * Drives the first-run and re-auth form. On success [SessionController] flips to
 * LoggedIn and the app leaves this screen; on failure the spec wording is shown
 * inline and the user stays put.
 */
class LoginViewModel(
    private val session: SessionController,
    store: AccountStore,
) : ViewModel() {

    private val _state = MutableStateFlow(
        LoginUiState(
            baseUrl = store.state.value.baseUrl.orEmpty(),
            username = store.state.value.activeUsername.orEmpty(),
        ),
    )
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun onBaseUrlChange(value: String) = _state.update { it.copy(baseUrl = value, error = null) }

    fun onUsernameChange(value: String) = _state.update { it.copy(username = value, error = null) }

    fun onPasswordChange(value: String) = _state.update { it.copy(password = value, error = null) }

    fun connect() {
        val current = _state.value
        if (current.connecting) return
        if (current.baseUrl.isBlank()) {
            _state.update { it.copy(error = "Enter a proxy address") }
            return
        }
        if (current.username.isBlank() || current.password.isBlank()) {
            _state.update { it.copy(error = "Enter a username and password") }
            return
        }
        _state.update { it.copy(connecting = true, error = null) }
        viewModelScope.launch {
            when (val outcome = session.connect(current.baseUrl, current.username.trim(), current.password)) {
                ConnectOutcome.Connected -> _state.update { it.copy(connecting = false, password = "") }
                is ConnectOutcome.Failed ->
                    _state.update { it.copy(connecting = false, error = outcome.message) }
            }
        }
    }

    companion object {
        fun factory(session: SessionController, store: AccountStore): ViewModelProvider.Factory =
            viewModelFactory {
                initializer { LoginViewModel(session, store) }
            }
    }
}
