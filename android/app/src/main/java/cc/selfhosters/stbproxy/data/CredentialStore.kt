package cc.selfhosters.stbproxy.data

/**
 * Skeleton credential storage.
 *
 * Passwords move to EncryptedSharedPreferences (androidx.security:security-crypto)
 * with `android:allowBackup="false"` in a later ticket; for now this holds the
 * active account in memory so the manual-DI wiring is exercised.
 */
class CredentialStore {

    var baseUrl: String? = null

    private val accounts = linkedMapOf<String, String>()

    var activeUsername: String? = null
        private set

    val activeCredentials: Pair<String, String>?
        get() = activeUsername?.let { user ->
            accounts[user]?.let { pass -> user to pass }
        }

    fun upsert(username: String, password: String) {
        accounts[username] = password
        activeUsername = username
    }
}
