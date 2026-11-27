package cc.selfhosters.stbproxy.ui.ondemand

import cc.selfhosters.stbproxy.data.OnDemandChanges
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandDownload
import cc.selfhosters.stbproxy.data.model.OnDemandEpisode
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandKey
import cc.selfhosters.stbproxy.data.model.OnDemandPlayback
import cc.selfhosters.stbproxy.data.model.OnDemandProgress
import cc.selfhosters.stbproxy.data.model.OnDemandSeason
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * A started On Demand session, handed to the player (ticket 15): what was chosen
 * ([choice]: the item key, the start position and titles) and the session `/play`
 * minted ([playback]: `session`, `absoluteUrl`, `durationSec`).
 */
data class OnDemandPlayStart(val choice: PlayChoice, val playback: OnDemandPlayback)

/** One title as the TV preview pane or the phone detail page shows it. */
data class TitleDetailState(
    /** The title (the TV row at once; the phone's once its detail loads). */
    val item: OnDemandItem? = null,
    val detail: OnDemandDetail? = null,
    /** The detail failed to load (the phone page shows it with Try again). */
    val loadError: String? = null,
    /** The Season the chips show. */
    val seasonId: String? = null,
    /** Episodes per Season id, as loaded. */
    val episodes: Map<String, List<OnDemandEpisode>> = emptyMap(),
    val episodesError: String? = null,
    /** A Play or Mark watched is in flight. */
    val busy: Boolean = false,
    /** The inline error under Play (with Try again). */
    val actionError: String? = null,
    /** A download request or cancel is in flight. */
    val downloadBusy: Boolean = false,
    /** The server's text after a refused download request or cancel. */
    val downloadError: String? = null,
) {
    val key: String? get() = item?.let(::itemKey)

    val season: OnDemandSeason? get() = detail?.seasons?.firstOrNull { it.id == seasonId }

    val buttons: PlayButtons?
        get() = item?.let { playButtons(it, detail, detail?.seasons?.firstOrNull()?.let { s -> episodes[s.id] }) }

    /** The chosen Season's Episode rows; null while they load. */
    val episodeRows: List<EpisodeRow>?
        get() {
            val item = item ?: return null
            val season = season ?: return null
            val list = episodes[season.id] ?: return null
            return episodeRows(item, season, list, detail?.upNext)
        }
}

/**
 * Drives one title's detail (ticket 14): loading it (after a settle on TV), its
 * Seasons and Episodes, Play (which mints the session so 503/404/502 show inline
 * under the button), Mark watched and Try again, and the server downloads of a Movie
 * or a whole Season (with [watchDownloads] following them). Shared by the TV preview pane
 * ([OnDemandViewModel]) and the phone detail page ([OnDemandDetailViewModel]).
 *
 * Calls are expected on the main thread.
 */
class TitleDetailController(
    private val api: ApiClient,
    private val scope: CoroutineScope,
    private val changes: OnDemandChanges,
    private val onUnauthorized: () -> Unit,
) {
    private val _state = MutableStateFlow(TitleDetailState())
    val state: StateFlow<TitleDetailState> = _state.asStateFlow()

    private val _starts = Channel<OnDemandPlayStart>(Channel.BUFFERED)

    /** Sessions Play has started, each delivered once: open the player with it. */
    val playStarts: Flow<OnDemandPlayStart> = _starts.receiveAsFlow()

    private var loadJob: Job? = null
    private var seasonJob: Job? = null
    private var retryAction: (() -> Unit)? = null
    private val details = LinkedHashMap<String, OnDemandDetail>()

    /** Shows [item] at once and its detail after [settleMs] (the TV pane follows focus). */
    fun show(item: OnDemandItem, settleMs: Long = 0) {
        val key = itemKey(item)
        if (_state.value.key == key) return
        cancelLoads()
        retryAction = null
        val cached = details[key]
        _state.value = TitleDetailState(item = item, detail = cached, seasonId = cached?.let(::openingSeason))
        if (cached != null) {
            loadSeason(cached.seasonId())
            return
        }
        loadJob = scope.launch {
            delay(settleMs)
            fetchDetail(item.portal, item.id)
        }
    }

    /** The phone detail page: loads a title known only by its key. */
    fun load(portal: String, id: String) {
        cancelLoads()
        _state.update { it.copy(loadError = null) }
        loadJob = scope.launch { fetchDetail(portal, id) }
    }

    /** Refetches the shown title (and its open Season) if it is "portal/id" [key]. */
    fun refresh(key: String) {
        details.remove(key)
        val state = _state.value
        val item = state.item ?: return
        if (state.key != key) return
        cancelLoads()
        loadJob = scope.launch {
            fetchDetail(item.portal, item.id, reloadSeason = true)
        }
    }

    fun selectSeason(id: String) {
        if (_state.value.seasonId == id) return
        _state.update { it.copy(seasonId = id, episodesError = null) }
        loadSeason(id)
    }

    /** Starts [choice]: mints the session, then hands it to [playStarts]. */
    fun play(choice: PlayChoice?) {
        if (choice == null || _state.value.busy) return
        retryAction = { play(choice) }
        val key = _state.value.key
        _state.update { it.copy(busy = true, actionError = null) }
        scope.launch {
            try {
                val playback = api.playOnDemand(choice.key)
                _state.update { it.copy(busy = false) }
                retryAction = null
                _starts.send(OnDemandPlayStart(choice, playback))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (e is ApiException && e.code == 401) onUnauthorized()
                // Focus may have moved on to another title meanwhile: the error is this one's.
                _state.update { if (it.key != key) it else it.copy(busy = false, actionError = playErrorText(e)) }
            }
        }
    }

    /** A Movie's Mark watched / ✓ Watched toggle (07's manual mark). */
    fun toggleWatched() {
        val state = _state.value
        val item = state.item ?: return
        if (item.isSeries || state.busy) return
        val progress = if (state.detail != null) state.detail.progress else item.progress
        val watched = !(progress?.watched ?: false)
        retryAction = { toggleWatched() }
        _state.update { it.copy(busy = true, actionError = null) }
        scope.launch {
            try {
                api.markOnDemandWatched(OnDemandKey.Movie(item.portal, item.id), watched)
                // Flip the toggle now; the refetch [changes] triggers brings the server's state.
                val marked = if (watched) (progress ?: OnDemandProgress()).copy(watched = true) else null
                _state.update {
                    if (it.key != itemKey(item)) it
                    else it.copy(
                        busy = false,
                        item = it.item?.copy(progress = marked),
                        detail = it.detail?.copy(progress = marked),
                    )
                }
                retryAction = null
                changes.changed(item.portal, item.id)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (e is ApiException && e.code == 401) onUnauthorized()
                _state.update {
                    if (it.key != itemKey(item)) it else it.copy(busy = false, actionError = markErrorText(e))
                }
            }
        }
    }

    /** Asks the server to download the shown Movie (again, after a failure). */
    fun downloadMovie() {
        val state = _state.value
        val item = state.item ?: return
        if (state.movieDownload?.canStart != true) return
        requestDownload(item) { api.requestOnDemandDownload(OnDemandKey.Movie(item.portal, item.id)) }
    }

    /** Asks the server to download every Episode of the shown Season. */
    fun downloadSeason() {
        val state = _state.value
        val item = state.item ?: return
        val seasonId = state.seasonId ?: return
        if (state.seasonDownload?.canStart != true) return
        requestDownload(item) { api.requestOnDemandSeasonDownload(item.portal, item.id, seasonId) }
    }

    /** Cancels the viewer's own unfinished download of the shown Movie. */
    fun cancelMovieDownload() {
        val state = _state.value
        val item = state.item ?: return
        val brief = state.detail?.download ?: return
        if (!state.canCancelMovieDownload || state.downloadBusy) return
        downloadCall(item) {
            api.cancelOnDemandDownload(brief.id)
            _state.update {
                if (it.key != itemKey(item)) it
                else it.copy(detail = it.detail?.let { d -> if (d.download?.id == brief.id) d.copy(download = null) else d })
                    .also(::cacheDetail)
            }
        }
    }

    /**
     * While the screen shows: every [intervalMs], if a download the detail shows is queued
     * or running, re-reads the downloads list. Runs until cancelled.
     */
    suspend fun watchDownloads(intervalMs: Long = DOWNLOAD_POLL_MS) {
        while (true) {
            delay(intervalMs)
            if (_state.value.hasActiveDownload) refreshDownloads()
        }
    }

    /** Re-reads the downloads list and puts the shown title's statuses in step with it. */
    suspend fun refreshDownloads() {
        val key = _state.value.key ?: return
        try {
            val downloads = api.fetchOnDemandDownloads()
            val briefs = briefsByKey(downloads.items)
            _state.update {
                if (it.key != key) it
                else it.withDownloads(briefs, complete = true)
                    .let { s -> s.copy(detail = s.detail?.copy(canDownload = downloads.canDownload)) }
                    .also(::cacheDetail)
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // A missed look is fine: the next one (or a refetch) catches up.
            if (e is ApiException && e.code == 401) onUnauthorized()
        }
    }

    private fun requestDownload(item: OnDemandItem, request: suspend () -> List<OnDemandDownload>) {
        if (_state.value.downloadBusy) return
        downloadCall(item) {
            val briefs = briefsByKey(request())
            _state.update {
                if (it.key != itemKey(item)) it else it.withDownloads(briefs, complete = false).also(::cacheDetail)
            }
        }
    }

    /** Runs a download request or cancel for [item], with its busy flag and inline error. */
    private fun downloadCall(item: OnDemandItem, call: suspend () -> Unit) {
        val key = itemKey(item)
        _state.update { it.copy(downloadBusy = true, downloadError = null) }
        scope.launch {
            try {
                call()
                _state.update { if (it.key != key) it else it.copy(downloadBusy = false) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (e is ApiException && e.code == 401) onUnauthorized()
                _state.update {
                    if (it.key != key) it else it.copy(downloadBusy = false, downloadError = downloadErrorText(e))
                }
            }
        }
    }

    /** Keeps the cached detail's download in step (the TV pane shows the cache on return). */
    private fun cacheDetail(state: TitleDetailState) {
        val detail = state.detail ?: return
        val key = "${detail.portal}/${detail.id}"
        if (key in details) details[key] = detail
    }

    /** Try again: the failed Play / Mark watched, else the detail or the Season. */
    fun retry() {
        val state = _state.value
        retryAction?.let {
            it()
            return
        }
        val item = state.item
        when {
            state.detail == null && item != null -> {
                cancelLoads()
                loadJob = scope.launch { fetchDetail(item.portal, item.id) }
            }
            state.episodesError != null -> state.seasonId?.let(::loadSeason)
        }
    }

    private suspend fun fetchDetail(portal: String, id: String, reloadSeason: Boolean = false) {
        try {
            val detail = api.fetchOnDemandItem(portal, id)
            val key = "$portal/$id"
            details[key] = detail
            if (details.size > DETAIL_CACHE) details.remove(details.keys.first())
            val current = _state.value
            if (current.item != null && current.key != key) return
            val seasonId = current.seasonId?.takeIf { s -> detail.seasons.any { it.id == s } }
                ?: openingSeason(detail)
            _state.update {
                it.copy(
                    item = detail.asItem(),
                    detail = detail,
                    loadError = null,
                    seasonId = seasonId,
                    episodes = if (reloadSeason) emptyMap() else it.episodes,
                )
            }
            loadSeason(detail.seasonId(seasonId))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (e is ApiException && e.code == 401) onUnauthorized()
            _state.update { it.copy(loadError = loadErrorText(e)) }
        }
    }

    /**
     * Loads [seasonId]'s Episodes, and for a Series with no Up next the first Season's
     * too (the ▶ Play S1 E1 button needs its first Episode).
     */
    private fun loadSeason(seasonId: String?) {
        val state = _state.value
        val item = state.item ?: return
        val detail = state.detail ?: return
        if (!detail.isSeries) return
        val wanted = listOfNotNull(
            seasonId,
            detail.seasons.firstOrNull()?.id?.takeIf { detail.upNext == null },
        ).distinct().filter { it !in state.episodes }
        if (wanted.isEmpty()) return
        seasonJob?.cancel()
        seasonJob = scope.launch {
            for (id in wanted) {
                try {
                    val episodes = api.fetchOnDemandSeason(item.portal, item.id, id)
                    _state.update {
                        if (it.key != itemKey(item)) it
                        else it.copy(episodes = it.episodes + (id to episodes), episodesError = null)
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    if (e is ApiException && e.code == 401) onUnauthorized()
                    _state.update { if (it.key != itemKey(item)) it else it.copy(episodesError = loadErrorText(e)) }
                }
            }
        }
    }

    private fun OnDemandDetail.seasonId(preferred: String? = null): String? =
        preferred ?: openingSeason(this)

    private fun cancelLoads() {
        loadJob?.cancel()
        seasonJob?.cancel()
    }

    private companion object {
        const val DETAIL_CACHE = 50
    }
}
