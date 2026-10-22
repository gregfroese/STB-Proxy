package cc.selfhosters.stbproxy.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * The Android-only persistence behind [AccountStore] (spec 2.4).
 *
 * Non-secret state (base URL, usernames, the active-account pointer) lives in
 * ordinary `SharedPreferences`; passwords live in [EncryptedSharedPreferences].
 * Abstracting it lets the account-selection logic be exercised with a fake on
 * the JVM (no Android framework).
 */
interface AccountStorage {
    fun readBaseUrl(): String?
    fun writeBaseUrl(url: String?)

    fun readUsernames(): List<String>
    fun writeUsernames(usernames: List<String>)

    fun readActiveUsername(): String?
    fun writeActiveUsername(username: String?)

    fun readPassword(username: String): String?
    fun writePassword(username: String, password: String)
    fun removePassword(username: String)

    fun readGroupMode(): String?
    fun writeGroupMode(mode: String?)

    /** Per-channel aspect overrides, as [encodeAspectModes] writes them. */
    fun readAspectModes(): String?
    fun writeAspectModes(encoded: String?)
}

/**
 * Real store backed by ordinary prefs + [EncryptedSharedPreferences]. The
 * device-bound keystore means the encrypted file must never be backed up, hence
 * `android:allowBackup="false"` on the application (spec 2.4).
 */
class AndroidAccountStorage(context: Context) : AccountStorage {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    // Built lazily: instances that only touch non-secret prefs (e.g. the
    // grouping preference) never create the encrypted store.
    private val secure: SharedPreferences by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            SECURE_PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    override fun readBaseUrl(): String? = prefs.getString(KEY_BASE_URL, null)

    override fun writeBaseUrl(url: String?) {
        prefs.edit().apply {
            if (url == null) remove(KEY_BASE_URL) else putString(KEY_BASE_URL, url)
        }.apply()
    }

    override fun readUsernames(): List<String> =
        prefs.getString(KEY_USERNAMES, null)
            ?.split(USERNAME_SEPARATOR)
            ?.filter { it.isNotBlank() }
            .orEmpty()

    override fun writeUsernames(usernames: List<String>) {
        prefs.edit()
            .putString(KEY_USERNAMES, usernames.joinToString(USERNAME_SEPARATOR))
            .apply()
    }

    override fun readActiveUsername(): String? = prefs.getString(KEY_ACTIVE_USERNAME, null)

    override fun writeActiveUsername(username: String?) {
        prefs.edit().apply {
            if (username == null) remove(KEY_ACTIVE_USERNAME) else putString(KEY_ACTIVE_USERNAME, username)
        }.apply()
    }

    override fun readPassword(username: String): String? = secure.getString(passwordKey(username), null)

    override fun writePassword(username: String, password: String) {
        secure.edit().putString(passwordKey(username), password).apply()
    }

    override fun removePassword(username: String) {
        secure.edit().remove(passwordKey(username)).apply()
    }

    override fun readGroupMode(): String? = prefs.getString(KEY_GROUP_MODE, null)

    override fun writeGroupMode(mode: String?) {
        prefs.edit().apply {
            if (mode == null) remove(KEY_GROUP_MODE) else putString(KEY_GROUP_MODE, mode)
        }.apply()
    }

    override fun readAspectModes(): String? = prefs.getString(KEY_ASPECT_MODES, null)

    override fun writeAspectModes(encoded: String?) {
        prefs.edit().apply {
            if (encoded.isNullOrEmpty()) remove(KEY_ASPECT_MODES) else putString(KEY_ASPECT_MODES, encoded)
        }.apply()
    }

    private fun passwordKey(username: String): String = "password:$username"

    private companion object {
        const val PREFS_NAME = "stb_proxy_prefs"
        const val SECURE_PREFS_NAME = "stb_proxy_secure_prefs"
        const val KEY_BASE_URL = "base_url"
        const val KEY_USERNAMES = "usernames"
        const val KEY_ACTIVE_USERNAME = "active_username"
        const val KEY_GROUP_MODE = "group_mode"
        const val KEY_ASPECT_MODES = "aspect_modes"
        const val USERNAME_SEPARATOR = "\n"
    }
}
