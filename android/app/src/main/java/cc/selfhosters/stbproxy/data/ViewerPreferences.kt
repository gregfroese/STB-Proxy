package cc.selfhosters.stbproxy.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Per-device viewer preferences that aren't account credentials: the picker's
 * [GroupMode] and per-channel [AspectMode] overrides, persisted through
 * [AccountStorage] and exposed as [StateFlow]s so screens react to changes.
 */
class ViewerPreferences(
    private val storage: AccountStorage,
) {

    private val _groupMode = MutableStateFlow(readGroupMode())
    val groupMode: StateFlow<GroupMode> = _groupMode.asStateFlow()

    fun setGroupMode(mode: GroupMode) {
        storage.writeGroupMode(mode.name)
        _groupMode.value = mode
    }

    private val _aspectModes = MutableStateFlow(decodeAspectModes(storage.readAspectModes()))

    /** Channels (by `portal/channelId`) whose picture fit isn't [AspectMode.AUTO]. */
    val aspectModes: StateFlow<Map<String, AspectMode>> = _aspectModes.asStateFlow()

    fun setAspectMode(channelKey: String, mode: AspectMode) {
        val updated = if (mode == AspectMode.AUTO) {
            _aspectModes.value - channelKey
        } else {
            _aspectModes.value + (channelKey to mode)
        }
        storage.writeAspectModes(encodeAspectModes(updated))
        _aspectModes.value = updated
    }

    private fun readGroupMode(): GroupMode =
        storage.readGroupMode()
            ?.let { stored -> GroupMode.entries.firstOrNull { it.name == stored } }
            ?: GroupMode.BLOCKS
}
