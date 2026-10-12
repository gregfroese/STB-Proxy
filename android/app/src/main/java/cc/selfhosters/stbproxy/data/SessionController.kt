package cc.selfhosters.stbproxy.data

import cc.selfhosters.stbproxy.data.network.ConnectionProbe
import cc.selfhosters.stbproxy.data.network.OPERATOR_LABEL
import cc.selfhosters.stbproxy.data.network.ProbeResult
import cc.selfhosters.stbproxy.data.network.REAUTH_MESSAGE
import cc.selfhosters.stbproxy.data.network.normaliseBaseUrl
import cc.selfhosters.stbproxy.data.network.probeMessage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** App-level authentication state gating the whole UI (spec 2.4). */
sealed interface SessionState {
    /** Auto-login in flight; nothing else is reachable yet. */
    data object Checking : SessionState

    /** Not signed in. [message] explains why (auto-login failure / mid-session 401). */
    data class LoggedOut(val message: String? = null) : SessionState

    /** Signed in. [accountLabel] is the account name or the operator label. */
    data class LoggedIn(
        val accountLabel: String,
        val credentialsUnverified: Boolean,
    ) : SessionState
}

/** Result of a user-initiated *Connect* attempt, for the login form. */
sealed interface ConnectOutcome {
    data object Connected : ConnectOutcome
    data class Failed(val message: String) : ConnectOutcome
}

/**
 * Owns login, the connection probe and the app-wide [SessionState]. The picker
 * reports a mid-session 401 here via [reportUnauthorized].
 */
class SessionController(
    private val store: AccountStore,
    private val probe: ConnectionProbe,
) {

    private val _state = MutableStateFlow<SessionState>(SessionState.Checking)
    val state: StateFlow<SessionState> = _state.asStateFlow()

    /** Whether any account credentials are saved (used to label security-off sessions). */
    fun hasCredentials(): Boolean = store.activeCredentials() != null

    /** On launch: probe with the stored active account, else fall back to Login. */
    suspend fun autoLogin() {
        val baseUrl = store.state.value.baseUrl
        val credentials = store.activeCredentials()
        if (baseUrl == null || credentials == null) {
            _state.value = SessionState.LoggedOut(null)
            return
        }
        _state.value = when (val result = probe.probe(baseUrl, credentials.first, credentials.second)) {
            is ProbeResult.Connected -> result.toLoggedIn(credentialsEntered = true)
            ProbeResult.WrongCredentials -> SessionState.LoggedOut(REAUTH_MESSAGE)
            else -> SessionState.LoggedOut(probeMessage(result))
        }
    }

    /** The first-run / settings *Connect*: probe, then persist on success. */
    suspend fun connect(baseUrlInput: String, username: String, password: String): ConnectOutcome {
        val normalised = try {
            normaliseBaseUrl(baseUrlInput)
        } catch (e: IllegalArgumentException) {
            return ConnectOutcome.Failed(e.message ?: "Enter a proxy address")
        }
        return when (val result = probe.probe(normalised, username, password)) {
            is ProbeResult.Connected -> {
                store.setBaseUrl(normalised)
                store.addAccount(username, password)
                _state.value = result.toLoggedIn(credentialsEntered = username.isNotBlank())
                ConnectOutcome.Connected
            }
            else -> ConnectOutcome.Failed(probeMessage(result))
        }
    }

    /** Switches to a saved account by re-probing it; falls back on failure. */
    suspend fun switchTo(username: String): ConnectOutcome {
        store.setActive(username)
        val baseUrl = store.state.value.baseUrl
        val credentials = store.activeCredentials()
        if (baseUrl == null || credentials == null) {
            _state.value = SessionState.LoggedOut(REAUTH_MESSAGE)
            return ConnectOutcome.Failed(REAUTH_MESSAGE)
        }
        return when (val result = probe.probe(baseUrl, credentials.first, credentials.second)) {
            is ProbeResult.Connected -> {
                _state.value = result.toLoggedIn(credentialsEntered = true)
                ConnectOutcome.Connected
            }
            ProbeResult.WrongCredentials -> {
                _state.value = SessionState.LoggedOut(REAUTH_MESSAGE)
                ConnectOutcome.Failed(REAUTH_MESSAGE)
            }
            else -> {
                val message = probeMessage(result)
                _state.value = SessionState.LoggedOut(message)
                ConnectOutcome.Failed(message)
            }
        }
    }

    /** A mid-session 401: drop to Login explaining the session is no longer valid. */
    fun reportUnauthorized() {
        _state.value = SessionState.LoggedOut(REAUTH_MESSAGE)
    }

    /** Ends the session but keeps saved accounts. */
    fun signOut() {
        store.signOut()
        _state.value = SessionState.LoggedOut(null)
    }

    private fun ProbeResult.Connected.toLoggedIn(credentialsEntered: Boolean): SessionState.LoggedIn =
        SessionState.LoggedIn(
            accountLabel = lineup.account ?: OPERATOR_LABEL,
            credentialsUnverified = lineup.account == null && credentialsEntered,
        )
}
