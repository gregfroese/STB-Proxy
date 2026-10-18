package cc.selfhosters.stbproxy.ui.player

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.data.SessionController
import cc.selfhosters.stbproxy.data.ViewerPreferences
import cc.selfhosters.stbproxy.data.epg.EpgRepository
import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.network.ApiException
import cc.selfhosters.stbproxy.ui.picker.effectiveGroupMode
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.Instant

/**
 * Everything the split player screen renders (spec 2.6): the current channel
 * and its launch-Block zap list, the in-memory now/next map, the stream URL and
 * the surfaced playback error.
 */
data class PlayerUiState(
    val loading: Boolean = true,
    val lineupError: String? = null,
    val channel: Channel? = null,
    val launchBlock: String = "",
    val groupMode: GroupMode = GroupMode.BLOCKS,
    val zapList: List<Channel> = emptyList(),
    val currentIndex: Int = 0,
    val streamUrl: String? = null,
    val playbackError: PlaybackError? = null,
    val waitingForTuner: Boolean = false,
    val prepareNonce: Int = 0,
    val nowNext: Map<String, NowNext> = emptyMap(),
    val now: Instant = Instant.now(),
)

/**
 * Drives the player (spec 2.6). Re-fetches `/api/lineup` for the channel and its
 * launch-Block zap list, resolves the stream URL, and holds one in-memory
 * now/next map. The map is recomputed against a fresh clock every minute and
 * re-fetched on foreground and when the current programme's `stop` passes.
 */
class PlayerViewModel(
    private val apiClient: ApiClient,
    private val epgRepository: EpgRepository,
    private val session: SessionController,
    private val viewerPreferences: ViewerPreferences,
    private val portal: String,
    private val channelId: String,
    launchBlock: String,
    private val clock: () -> Instant = Instant::now,
) : ViewModel() {

    private val _state = MutableStateFlow(PlayerUiState(launchBlock = launchBlock))
    val state: StateFlow<PlayerUiState> = _state.asStateFlow()

    private var lastComputedAt: Instant = clock()
    private var tickerJob: Job? = null

    init {
        load()
    }

    private fun load() {
        _state.update { it.copy(loading = true, lineupError = null) }
        viewModelScope.launch {
            try {
                val lineup = apiClient.fetchLineup()
                val group = _state.value.launchBlock
                val mode = effectiveGroupMode(viewerPreferences.groupMode.value, lineup.blocks)
                val list = zapList(lineup.channels, group, mode)
                val channel = lineup.channels.firstOrNull {
                    it.portal == portal && it.channelId == channelId
                } ?: list.firstOrNull()
                val index = channel?.let { c ->
                    list.indexOfFirst { it.portal == c.portal && it.channelId == c.channelId }
                } ?: -1
                _state.update {
                    it.copy(
                        loading = false,
                        zapList = list,
                        groupMode = mode,
                        channel = channel,
                        currentIndex = if (index < 0) 0 else index,
                        streamUrl = channel?.let { c -> apiClient.playUrl(c) },
                        lineupError = if (channel == null) CHANNEL_NOT_FOUND else null,
                    )
                }
                if (channel != null) {
                    refreshEpg()
                    startTicker()
                }
            } catch (e: ApiException) {
                if (e.code == 401) session.reportUnauthorized()
                _state.update {
                    it.copy(
                        loading = false,
                        lineupError = "Failed to load channels (HTTP ${e.code})",
                    )
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        loading = false,
                        lineupError = e.message ?: "Failed to load channels",
                    )
                }
            }
        }
    }

    /** Best-effort `/xmltv` re-fetch; a failed fetch keeps the previous map. */
    fun refreshEpg() {
        viewModelScope.launch {
            val map = epgRepository.fetch()
            val now = clock()
            lastComputedAt = now
            _state.update { it.copy(nowNext = if (map.isEmpty()) it.nowNext else map, now = now) }
        }
    }

    /** Re-fetch the guide whenever the app comes back to the foreground. */
    fun onForeground() {
        if (!_state.value.loading) refreshEpg()
    }

    /** Steps the current channel [delta] places through the launch Block. */
    fun zap(delta: Int) {
        val current = _state.value.channel ?: return
        val target = zapTarget(
            _state.value.zapList,
            _state.value.launchBlock,
            current,
            delta,
            _state.value.groupMode,
        ) ?: return
        select(target)
    }

    /** Zaps to the [index]-th row of the launch-Block list. */
    fun selectChannel(index: Int) {
        val target = _state.value.zapList.getOrNull(index) ?: return
        select(target)
    }

    private fun select(target: Channel) {
        val list = _state.value.zapList
        val index = list.indexOfFirst { it.portal == target.portal && it.channelId == target.channelId }
        _state.update {
            it.copy(
                channel = target,
                currentIndex = if (index < 0) 0 else index,
                streamUrl = apiClient.playUrl(target),
                playbackError = null,
                waitingForTuner = false,
                prepareNonce = it.prepareNonce + 1,
            )
        }
    }

    /** A surfaced stream failure; the sidebar stays live so the user can hop. */
    fun onPlayerError(error: PlaybackError) {
        _state.update { it.copy(playbackError = error) }
    }

    /** Retry re-`prepare()`s from scratch (a progressive-live stream can't resume). */
    fun retry() {
        if (_state.value.lineupError != null) {
            load()
            return
        }
        _state.update {
            it.copy(
                playbackError = null,
                waitingForTuner = false,
                prepareNonce = it.prepareNonce + 1,
            )
        }
    }

    /** Polls for a free tuner by re-preparing after a short wait. */
    fun waitForTuner() {
        if (_state.value.waitingForTuner) return
        _state.update { it.copy(waitingForTuner = true, playbackError = null) }
        viewModelScope.launch {
            delay(WAIT_FOR_TUNER_MS)
            _state.update {
                it.copy(waitingForTuner = false, prepareNonce = it.prepareNonce + 1)
            }
        }
    }

    private fun startTicker() {
        tickerJob?.cancel()
        tickerJob = viewModelScope.launch {
            while (isActive) {
                delay(EPG_TICK_MS)
                onTick()
            }
        }
    }

    private fun onTick() {
        val now = clock()
        when (epgRefreshAction(now, lastComputedAt, currentStop(now))) {
            EpgRefreshAction.REFETCH -> refreshEpg()
            EpgRefreshAction.RECOMPUTE -> {
                lastComputedAt = now
                _state.update { it.copy(now = now) }
            }
            EpgRefreshAction.NONE -> Unit
        }
    }

    private fun currentStop(now: Instant): Instant? {
        val epgId = _state.value.channel?.epgId ?: return null
        return resolveNowNext(_state.value.nowNext[epgId], now)?.now?.stop
    }

    override fun onCleared() {
        tickerJob?.cancel()
        super.onCleared()
    }

    companion object {
        const val EPG_TICK_MS = 60_000L
        const val WAIT_FOR_TUNER_MS = 5_000L
        const val CHANNEL_NOT_FOUND = "This channel is no longer in the lineup."

        fun factory(
            apiClient: ApiClient,
            epgRepository: EpgRepository,
            session: SessionController,
            viewerPreferences: ViewerPreferences,
            portal: String,
            channelId: String,
            launchBlock: String,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                PlayerViewModel(
                    apiClient,
                    epgRepository,
                    session,
                    viewerPreferences,
                    portal,
                    channelId,
                    launchBlock,
                )
            }
        }
    }
}
