package cc.selfhosters.stbproxy.data

/** In-memory [AccountStorage] for JVM tests — no Android framework. */
class FakeAccountStorage(
    private var baseUrl: String? = null,
    private var usernames: List<String> = emptyList(),
    private var activeUsername: String? = null,
) : AccountStorage {

    private val passwords = mutableMapOf<String, String>()

    override fun readBaseUrl(): String? = baseUrl
    override fun writeBaseUrl(url: String?) { baseUrl = url }

    override fun readUsernames(): List<String> = usernames
    override fun writeUsernames(usernames: List<String>) { this.usernames = usernames }

    override fun readActiveUsername(): String? = activeUsername
    override fun writeActiveUsername(username: String?) { activeUsername = username }

    override fun readPassword(username: String): String? = passwords[username]
    override fun writePassword(username: String, password: String) { passwords[username] = password }
    override fun removePassword(username: String) { passwords.remove(username) }

    fun passwordCount(): Int = passwords.size
}
