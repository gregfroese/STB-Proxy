package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandCategory
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandPortalStatus
import cc.selfhosters.stbproxy.data.model.OnDemandProgress
import cc.selfhosters.stbproxy.data.network.ApiException
import kotlin.math.roundToInt

/*
 * Pure logic behind On Demand browse (ticket 13, the Android UX decision, variant C):
 * the list query, paging, row text, the categories pane and the portal status pills.
 */

/** Items asked for per page (`limit`). */
const val PAGE_SIZE = 60

/** The next page is fetched once focus (or the last visible row) is this close to the end. */
const val PREFETCH_ROWS = 16

/** The TV preview pane waits this long for focus to settle before asking for details. */
const val PREVIEW_SETTLE_MS = 300L

/** A search applies from this many characters (the server's minimum). */
const val MIN_SEARCH_LENGTH = 2

/** The categories pane's Continue watching entry. */
const val CONTINUE_ID = "\u0000continue"

/** The categories pane's All entry: no `category=`. */
const val ALL_ID = ""

/** The four sorts, as the server names them and as the chips read. */
enum class OnDemandSort(val param: String, val label: String) {
    ADDED("added", "Recently added"),
    NAME("name", "A–Z"),
    YEAR("year", "Year"),
    RATING("rating", "Rating"),
}

/** What one title list asks `/items` for. */
data class ListQuery(
    val category: String?,
    val q: String?,
    val sort: OnDemandSort?,
) {
    /** The chip shown selected: Recently added while browsing, none for best match. */
    val shownSort: OnDemandSort? get() = sort ?: if (q == null) OnDemandSort.ADDED else null
}

/** The query for a category, the search box's text and the chosen sort (null = default). */
fun listQuery(category: String?, search: String, sort: OnDemandSort?): ListQuery = ListQuery(
    category = category?.takeIf { it != ALL_ID && it != CONTINUE_ID },
    q = search.trim().takeIf { it.length >= MIN_SEARCH_LENGTH },
    sort = sort,
)

/** "Best match first · in Drama" while searching, else null. */
fun searchHint(query: ListQuery, categoryName: String): String? =
    query.q?.let { "${query.sort?.label ?: "Best match first"} · in $categoryName" }

fun emptyListText(query: ListQuery, categoryName: String): String =
    query.q?.let { "No titles match “$it” in $categoryName" } ?: "Nothing here yet"

/** A title row's identity: list key and focus-restore key. */
fun itemKey(item: OnDemandItem): String = "${item.portal}/${item.id}"

/** True when the row at [focusIndex] is close enough to the loaded end to fetch the next page. */
fun shouldLoadMore(focusIndex: Int, loaded: Int, total: Int?, loading: Boolean): Boolean =
    !loading && total != null && loaded < total && focusIndex >= loaded - PREFETCH_ROWS

/** The list's last row: "Loading more… (60 of 200)", then "200 titles". */
fun footerText(loaded: Int, total: Int): String = when {
    loaded < total -> "Loading more… ($loaded of $total)"
    total == 1 -> "1 title"
    else -> "$total titles"
}

/** "1995 · ★ 8.3 · Main". */
fun factsLine(item: OnDemandItem): String = listOfNotNull(
    item.year?.toString(),
    item.rating?.let { "★ ${ratingText(it)}" },
    item.portalName.takeIf { it.isNotBlank() },
).joinToString(" · ")

/** 8.3 stays 8.3; 7.0 reads 7. */
fun ratingText(rating: Double): String =
    if (rating % 1.0 == 0.0) rating.toLong().toString() else "%.1f".format(java.util.Locale.ROOT, rating)

/** How far through an unwatched Resume point is, for the thin line; null for none. */
fun progressFraction(progress: OnDemandProgress?): Float? {
    if (progress == null || progress.watched) return null
    val position = progress.positionSec ?: return null
    val duration = progress.durationSec?.takeIf { it > 0 } ?: return null
    return (position.toFloat() / duration).coerceIn(0f, 1f)
}

/** A row's thin line: a Movie's Resume point, or its Series' Up next Episode's. */
fun rowProgress(item: OnDemandItem): Float? =
    progressFraction(item.progress)
        ?: item.upNext?.let { progressFraction(OnDemandProgress(it.positionSec, it.durationSec)) }

/** The preview's facts: "1995 · 170 min · R · ★ 8.3", or "2 Seasons" for a Series. */
fun detailFacts(item: OnDemandItem, detail: OnDemandDetail?): String = listOfNotNull(
    item.year?.toString(),
    detail?.durationMin?.takeIf { it > 0 }?.let { "$it min" },
    detail?.takeIf { it.isSeries && it.seasons.isNotEmpty() }?.seasons?.size
        ?.let { if (it == 1) "1 Season" else "$it Seasons" },
    detail?.ageRating,
    item.rating?.let { "★ ${ratingText(it)}" },
).joinToString(" · ")

/** Director, Cast (the first [CAST_SHOWN], "+n more") and Country, where known. */
fun credits(detail: OnDemandDetail): List<Pair<String, String>> {
    val cast = detail.actors.orEmpty().split(',').map { it.trim() }.filter { it.isNotEmpty() }
    return listOfNotNull(
        detail.director?.let { "Director" to it },
        cast.takeIf { it.isNotEmpty() }?.let {
            val more = it.size - CAST_SHOWN
            "Cast" to it.take(CAST_SHOWN).joinToString(", ") + if (more > 0) " +$more more" else ""
        },
        detail.country?.let { "Country" to it },
    )
}

private const val CAST_SHOWN = 5

/** Continue watching's second line: "80 min left", or "S2 · E4 · Name · Up next". */
fun continueSubtitle(item: OnDemandItem): String {
    item.upNext?.let { next ->
        return listOfNotNull(
            next.seasonNumber?.let { "S$it" },
            next.episodeNumber?.let { "E$it" },
            next.name?.takeIf { it.isNotBlank() },
            "Up next",
        ).joinToString(" · ")
    }
    val progress = item.progress ?: return ""
    val position = progress.positionSec ?: 0
    val duration = progress.durationSec
    return if (duration != null && duration > 0) {
        "${maxOf(1, ((duration - position) / 60.0).roundToInt())} min left"
    } else {
        "${clock(position)} in"
    }
}

/** Seconds as m:ss, or h:mm:ss. */
fun clock(seconds: Int): String {
    val h = seconds / 3600
    val m = (seconds % 3600) / 60
    val s = seconds % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
}

/** The web's wording for the On Demand error codes a viewer can meet (ticket 10). */
val ON_DEMAND_ERROR_TEXT: Map<String, String> = mapOf(
    ApiException.BUSY to "Someone else on this login is already watching — On Demand uses the same " +
        "stream as live TV. Stop the other stream and try again.",
    ApiException.NOT_FOUND to "This title isn't available any more.",
    ApiException.PORTAL_ERROR to "The provider didn't answer. Try again in a moment.",
)

/** What a failed load says: the code's wording, the server's text, the status, or unreachable. */
fun loadErrorText(error: Exception): String = when (error) {
    is ApiException -> error.errorCode?.let(ON_DEMAND_ERROR_TEXT::get)
        ?: error.serverMessage
        ?: "Couldn't load On Demand (HTTP ${error.code})"
    else -> "Couldn't reach the server"
}

/** One entry of the categories pane (or the phone's category list). */
data class CategoryEntry(val id: String, val name: String, val count: Int?)

/** Continue watching first, then All, then every category with its count. */
fun categoryEntries(
    categories: List<OnDemandCategory>,
    continueCount: Int?,
    allCount: Int?,
): List<CategoryEntry> =
    listOf(
        CategoryEntry(CONTINUE_ID, "Continue watching", continueCount),
        CategoryEntry(ALL_ID, "All", allCount),
    ) + categories.map { CategoryEntry(it.id, it.name, it.count) }

/** The pill for a portal whose index isn't ready ("Main: Partly indexed"), else null. */
fun statusPill(status: OnDemandPortalStatus, nowEpochSec: Long): String? {
    val text = when (status.status) {
        "indexing" -> status.progress
            ?.let { "Still indexing ($it%) — newest first" }
            ?: "Still indexing — newest first"
        "stale" -> "Not refreshed for ${since(status.lastRefresh, nowEpochSec)}"
        "partial" -> "Partly indexed"
        "failed" -> "Couldn't load — showing nothing from it"
        else -> return null
    }
    return "${status.name}: $text"
}

private fun since(lastRefresh: Long?, now: Long): String {
    if (lastRefresh == null) return "a while"
    val hours = (now - lastRefresh) / 3_600
    val days = hours / 24
    return when {
        days >= 2 -> "$days days"
        days == 1L -> "a day"
        hours >= 2 -> "$hours hours"
        else -> "an hour"
    }
}
