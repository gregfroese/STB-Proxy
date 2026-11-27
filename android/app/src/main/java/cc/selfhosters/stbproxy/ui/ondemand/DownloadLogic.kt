package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.model.OnDemandDownload
import cc.selfhosters.stbproxy.data.model.OnDemandDownloadBrief
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandSeason
import cc.selfhosters.stbproxy.data.network.ApiException

/*
 * Pure logic behind On Demand downloads on a title's detail: STB-Proxy saves a Movie or
 * Episode into its downloads folder (for Plex and Jellyfin), queued until nobody watches
 * from the portal. Nothing is stored on the device. The wording matches the web viewer.
 */

/** How often the detail looks again while a download it shows is queued or running. */
const val DOWNLOAD_POLL_MS = 15_000L

const val CANCEL_DOWNLOAD = "Cancel download"

/** The Download button: its [label], and whether pressing it asks for the download. */
data class DownloadButton(val label: String, val canStart: Boolean)

/** Download / Queued / Paused at N% / Downloading N% / Downloaded / Download failed – try again. */
fun downloadButton(brief: OnDemandDownloadBrief?): DownloadButton = when (brief?.status) {
    null -> DownloadButton("Download", canStart = true)
    OnDemandDownloadBrief.DONE -> DownloadButton("Downloaded", canStart = false)
    OnDemandDownloadBrief.DOWNLOADING -> DownloadButton("Downloading ${brief.progress}%", canStart = false)
    OnDemandDownloadBrief.FAILED -> DownloadButton("Download failed – try again", canStart = true)
    else -> DownloadButton(
        if (brief.progress > 0) "Paused at ${brief.progress}%" else "Queued",
        canStart = false,
    )
}

/** An Episode row's download status, or null when it was never asked for. */
fun episodeDownloadText(brief: OnDemandDownloadBrief?): String? = when {
    brief == null -> null
    brief.status == OnDemandDownloadBrief.FAILED -> "Download failed"
    else -> downloadButton(brief).label
}

/** Whether the viewer may cancel it: their own, not finished. */
fun canCancelDownload(brief: OnDemandDownloadBrief?): Boolean =
    brief != null && brief.mine && brief.status != OnDemandDownloadBrief.DONE

/** Queued (or paused) or running: worth looking at again. */
fun isDownloadActive(brief: OnDemandDownloadBrief?): Boolean =
    brief?.status == OnDemandDownloadBrief.QUEUED || brief?.status == OnDemandDownloadBrief.DOWNLOADING

/** The Series' button by the Season chips: "Download Season 2". */
fun seasonDownloadLabel(season: OnDemandSeason, index: Int): String =
    "Download Season ${season.number ?: (index + 1)}"

/** The inline error after a failed download request or cancel: the server's own text. */
fun downloadErrorText(error: Exception): String = when (error) {
    is ApiException -> error.serverMessage ?: "Couldn't ask for the download (HTTP ${error.code})"
    else -> "Couldn't reach the server"
}

/** A stable key for a Movie or an Episode, to match downloads to what the detail shows. */
fun downloadKey(key: OnDemandKey): String = when (key) {
    is OnDemandKey.Movie -> "movie\u0000${key.portal}\u0000${key.id}"
    is OnDemandKey.Episode -> "episode\u0000${key.portal}\u0000${key.seriesId}\u0000${key.seasonId}\u0000${key.episodeId}"
}

/** [downloads] as briefs by [downloadKey]. */
fun briefsByKey(downloads: List<OnDemandDownload>): Map<String, OnDemandDownloadBrief> =
    downloads.mapNotNull { d -> d.item.key?.let { downloadKey(it) to d.brief } }.toMap()

// ---- the detail state ----

/** A Movie's Download button; null unless the server allows downloads (and for a Series). */
val TitleDetailState.movieDownload: DownloadButton?
    get() = detail?.takeIf { it.canDownload && !it.isSeries }?.let { downloadButton(it.download) }

/** A Movie's Cancel download: the viewer's own unfinished download. */
val TitleDetailState.canCancelMovieDownload: Boolean
    get() = detail?.takeIf { it.canDownload && !it.isSeries }?.download.let(::canCancelDownload)

/** A Series' "Download Season N" for the shown Season; null unless allowed. */
val TitleDetailState.seasonDownload: String?
    get() {
        val detail = detail?.takeIf { it.canDownload && it.isSeries } ?: return null
        val season = season ?: return null
        return seasonDownloadLabel(season, detail.seasons.indexOf(season))
    }

/** A download the detail shows is queued or running (so it is polled). */
val TitleDetailState.hasActiveDownload: Boolean
    get() = isDownloadActive(detail?.download) ||
        episodes.values.any { list -> list.any { isDownloadActive(it.download) } }

/**
 * [briefs] (by [downloadKey]) put onto the Movie and the loaded Episodes. With
 * [complete] (the full downloads list) what isn't in it has no download any more;
 * otherwise (a POST's answer) only what it names changes.
 */
fun TitleDetailState.withDownloads(briefs: Map<String, OnDemandDownloadBrief>, complete: Boolean): TitleDetailState {
    val item = item ?: return this
    fun pick(key: OnDemandKey, old: OnDemandDownloadBrief?): OnDemandDownloadBrief? =
        briefs[downloadKey(key)] ?: old.takeUnless { complete }
    val detail = detail?.let {
        if (it.isSeries) it else it.copy(download = pick(OnDemandKey.Movie(item.portal, item.id), it.download))
    }
    val episodes = if (item.isSeries) {
        episodes.mapValues { (seasonId, list) ->
            list.map { episode ->
                val key = OnDemandKey.Episode(item.portal, item.id, seasonId, episode.id)
                episode.copy(download = pick(key, episode.download))
            }
        }
    } else {
        episodes
    }
    return copy(detail = detail, episodes = episodes)
}
