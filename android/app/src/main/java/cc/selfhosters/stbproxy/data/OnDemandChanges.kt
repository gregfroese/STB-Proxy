package cc.selfhosters.stbproxy.data

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/**
 * App-wide word that a title's viewer state (Resume point, Watched, Up next; ADR 0006)
 * has changed: after leaving the player and after Mark watched. On Demand's screens
 * listen and refetch that title, so its row, the preview pane / detail page and
 * Continue watching show the server's new state.
 *
 * A title is named "portal/id" (an Episode's title is its Series).
 */
class OnDemandChanges {

    private val _changes = MutableSharedFlow<String>(extraBufferCapacity = 16)
    val changes: SharedFlow<String> = _changes.asSharedFlow()

    fun changed(portal: String, id: String) {
        _changes.tryEmit("$portal/$id")
    }
}
