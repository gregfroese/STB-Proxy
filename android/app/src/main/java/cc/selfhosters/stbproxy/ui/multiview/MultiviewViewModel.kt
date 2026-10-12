package cc.selfhosters.stbproxy.ui.multiview

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.ui.player.PlaybackError
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Everything the Multiview grid renders (spec 2.7): the fixed set of Tiles, the
 * resolved stream URL per Tile, the tuner budget (discovered or defaulted), the
 * single audio-source slot, the armed swap slot, and the Tile awaiting a channel
 * from the picker overlay.
 */
data class MultiviewUiState(
    val loading: Boolean = true,
    val lineupError: String? = null,
    val channels: List<Channel> = emptyList(),
    val tiles: List<MultiviewTile> = emptyTiles(),
    val tunerCount: Int = DEFAULT_TUNER_COUNT,
    val tunerCountKnown: Boolean = false,
    val audioRequested: Int? = 0,
    val swapFrom: Int? = null,
    val pickFor: Int? = null,
    val focusSlot: Int = 0,
    val errors: Map<Int, PlaybackError> = emptyMap(),
    val prepareNonces: Map<Int, Int> = emptyMap(),
) {
    /** The slots that may open a stream with the current budget (spec 2.7). */
    val playableSlots: Set<Int> get() = withinTunerBudget(tiles, tunerCount)

    /** Slots with a channel but no tuner for it. */
    val overBudget: Set<Int> get() = overBudgetSlots(tiles, tunerCount)

    /** The one Tile that is unmuted (spec 2.7), or null when the grid is empty. */
    val audioSlot: Int? get() = effectiveAudioSlot(tiles, audioRequested, playableSlots)

    /** Distinct channels currently requested — the tuner-demand figure. */
    val tunersUsed: Int get() = distinctChannelCount(tiles)
}

/**
 * Drives the Multiview grid (spec 2.7): loads the lineup, discovers the tuner
 * budget best-effort, and applies the pure grid operations (pick / swap / remove
 * / audio / retry) to a [StateFlow].
 */
class MultiviewViewModel(
    private val apiClient: ApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow(MultiviewUiState())
    val state: StateFlow<MultiviewUiState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        _state.update { it.copy(loading = true, lineupError = null) }
        viewModelScope.launch {
            try {
                val lineup = apiClient.fetchLineup()
                val discovered = runCatching { apiClient.fetchTunerCount() }.getOrNull()
                _state.update { state ->
                    val tiles = seedTiles(state.tiles, lineup.channels)
                    state.copy(
                        loading = false,
                        lineupError = null,
                        channels = lineup.channels,
                        tiles = tiles,
                        tunerCount = discovered ?: DEFAULT_TUNER_COUNT,
                        tunerCountKnown = discovered != null,
                    )
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(loading = false, lineupError = e.message ?: "Failed to load channels")
                }
            }
        }
    }

    /** The absolute `/play` URL a Tile should open, or null when it holds none. */
    fun streamUrlFor(tile: MultiviewTile): String? =
        tile.channel?.let { apiClient.playUrl(it) }

    fun setFocus(slot: Int) {
        _state.update { it.copy(focusSlot = slot) }
    }

    /** Opens the picker overlay to choose [slot]'s channel (spec 2.7 Pick). */
    fun openPicker(slot: Int) {
        _state.update { it.copy(pickFor = slot, focusSlot = slot) }
    }

    fun dismissPicker() {
        _state.update { it.copy(pickFor = null) }
    }

    /** Applies the overlay's chosen channel to the Tile awaiting it. */
    fun pick(channel: Channel) {
        _state.update { state ->
            val slot = state.pickFor ?: return@update state
            state.copy(
                tiles = assignChannel(state.tiles, slot, channel),
                pickFor = null,
                errors = state.errors - slot,
                focusSlot = slot,
            )
        }
    }

    /** Arms [slot] for swap, or completes the exchange when one is armed. */
    fun swap(slot: Int) {
        _state.update { state ->
            val from = state.swapFrom
            when {
                from == null -> state.copy(swapFrom = slot)
                from == slot -> state.copy(swapFrom = null)
                else -> state.copy(
                    tiles = swapTiles(state.tiles, from, slot),
                    swapFrom = null,
                    errors = state.errors - from - slot,
                    focusSlot = slot,
                )
            }
        }
    }

    /**
     * Tapping a Tile body: completes an armed swap when another Tile is tapped,
     * otherwise just moves focus (spec 2.7 Swap).
     */
    fun onTileClick(slot: Int) {
        _state.update { state ->
            val from = state.swapFrom
            when {
                from != null && from != slot -> state.copy(
                    tiles = swapTiles(state.tiles, from, slot),
                    swapFrom = null,
                    errors = state.errors - from - slot,
                    focusSlot = slot,
                )
                from == slot -> state.copy(swapFrom = null)
                else -> state.copy(focusSlot = slot)
            }
        }
    }

    fun remove(slot: Int) {
        _state.update {
            it.copy(tiles = removeTile(it.tiles, slot), errors = it.errors - slot)
        }
    }

    /** Moves the single audio source to [slot] (spec 2.7). */
    fun setAudio(slot: Int) {
        _state.update { it.copy(audioRequested = slot) }
    }

    /** Per-Tile retry: clears this Tile's error and re-prepares only it. */
    fun retry(slot: Int) {
        _state.update {
            it.copy(
                errors = it.errors - slot,
                prepareNonces = it.prepareNonces + (slot to (it.prepareNonces[slot] ?: 0) + 1),
            )
        }
    }

    fun onTileError(slot: Int, error: PlaybackError) {
        _state.update { it.copy(errors = it.errors + (slot to error)) }
    }

    /**
     * Fills empty Tiles with the first lineup channels so the grid isn't blank on
     * entry. Once the user has touched the grid (any Tile filled) it's left alone.
     */
    private fun seedTiles(tiles: List<MultiviewTile>, channels: List<Channel>): List<MultiviewTile> {
        if (tiles.any { it.channel != null }) return tiles
        return tiles.mapIndexed { index, tile ->
            channels.getOrNull(index)?.let { tile.copy(channel = it) } ?: tile
        }
    }

    companion object {
        fun factory(apiClient: ApiClient): ViewModelProvider.Factory = viewModelFactory {
            initializer { MultiviewViewModel(apiClient) }
        }
    }
}
