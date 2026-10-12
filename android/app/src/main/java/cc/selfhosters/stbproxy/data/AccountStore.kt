package cc.selfhosters.stbproxy.data

import cc.selfhosters.stbproxy.data.network.normaliseBaseUrl
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Persisted proxy configuration: one normalised base URL plus a set of accounts
 * (usernames) sharing it, and which of them is active (spec 2.4).
 */
data class AccountsState(
    val baseUrl: String? = null,
    val usernames: List<String> = emptyList(),
    val activeUsername: String? = null,
)

/**
 * Account/credential logic on top of [AccountStorage]. Passwords are only ever
 * handed to the storage layer; the base URL is normalised on write via
 * [normaliseBaseUrl]. Exposes the current configuration as a [StateFlow] so the
 * UI reacts to switches and removals.
 */
class AccountStore(
    private val storage: AccountStorage,
) {

    private val _state = MutableStateFlow(load())
    val state: StateFlow<AccountsState> = _state.asStateFlow()

    /** Stores the normalised base URL, replacing any previous host. */
    fun setBaseUrl(raw: String) {
        storage.writeBaseUrl(normaliseBaseUrl(raw))
        publish()
    }

    /**
     * Adds (or updates) an account against the current base URL and makes it
     * active. The selector is keyed by username.
     */
    fun addAccount(username: String, password: String) {
        val names = storage.readUsernames().toMutableList()
        if (username !in names) names += username
        storage.writeUsernames(names)
        storage.writePassword(username, password)
        storage.writeActiveUsername(username)
        publish()
    }

    /** Removes an account and its password; promotes another if it was active. */
    fun removeAccount(username: String) {
        val names = storage.readUsernames().filterNot { it == username }
        storage.writeUsernames(names)
        storage.removePassword(username)
        if (storage.readActiveUsername() == username) {
            storage.writeActiveUsername(names.firstOrNull())
        }
        publish()
    }

    fun setActive(username: String) {
        if (username in storage.readUsernames()) {
            storage.writeActiveUsername(username)
            publish()
        }
    }

    /** Ends the session but keeps the saved accounts for a quick re-login. */
    fun signOut() {
        storage.writeActiveUsername(null)
        publish()
    }

    /** The Basic credentials of the active account, or null if none/disabled. */
    fun activeCredentials(): Pair<String, String>? {
        val username = storage.readActiveUsername() ?: return null
        val password = storage.readPassword(username) ?: return null
        return username to password
    }

    private fun load(): AccountsState = AccountsState(
        baseUrl = storage.readBaseUrl(),
        usernames = storage.readUsernames(),
        activeUsername = storage.readActiveUsername(),
    )

    private fun publish() {
        _state.value = load()
    }
}
