package cc.selfhosters.stbproxy.data

/**
 * The player's zap scope (ticket 07): which Channels up/down steps through. A
 * [Group] keeps the shipped "walk the launch Block/Genre" behaviour; a
 * [Channels] list carries an explicit ordered set, walked directly.
 */
sealed interface ZapScope {
    data class Group(val block: String, val label: String) : ZapScope

    data class Channels(val keys: List<String>, val label: String) : ZapScope
}

/**
 * Holds list scopes the route carries by token instead of inlining (ticket 07).
 * In-memory only: it survives navigation, and is lost on process death, where the
 * player falls back to the launch Channel's group.
 */
class ZapScopeStore {
    private val scopes = linkedMapOf<String, ZapScope.Channels>()
    private var counter = 0

    fun put(scope: ZapScope.Channels): String {
        counter += 1
        val token = "s$counter"
        scopes[token] = scope
        return token
    }

    fun get(token: String?): ZapScope.Channels? = token?.let { scopes[it] }
}
