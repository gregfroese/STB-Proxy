package cc.selfhosters.stbproxy.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Per-device viewer preferences that aren't account credentials. For now just
 * the picker's [GroupMode], persisted through [AccountStorage] and exposed as a
 * [StateFlow] so screens react to a change made in Settings.
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

    private fun readGroupMode(): GroupMode =
        storage.readGroupMode()
            ?.let { stored -> GroupMode.entries.firstOrNull { it.name == stored } }
            ?: GroupMode.BLOCKS
}
