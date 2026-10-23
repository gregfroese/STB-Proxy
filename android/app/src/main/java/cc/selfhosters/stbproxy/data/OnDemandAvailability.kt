package cc.selfhosters.stbproxy.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Shown when a request finds On Demand switched off for this login (404 `on_demand_off`). */
const val ON_DEMAND_OFF_NOTICE = "On Demand isn't available on this login any more."

/**
 * Whether this login gets On Demand: the app-wide source for the nav entry (ADR 0004).
 *
 * Every lineup fetch sets it from `onDemand`, silently. Any On Demand request answered
 * 404 `on_demand_off` switches it off and raises [notice], which the shell shows once
 * (after returning to Channels) and then [consumeNotice]s.
 */
class OnDemandAvailability {

    private val _enabled = MutableStateFlow(false)
    val enabled: StateFlow<Boolean> = _enabled.asStateFlow()

    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    /** The lineup's `onDemand` flag. */
    fun onLineup(onDemand: Boolean) {
        _enabled.value = onDemand
    }

    /** A 404 `on_demand_off` from any On Demand request. */
    fun switchedOff() {
        if (_enabled.value) _notice.value = ON_DEMAND_OFF_NOTICE
        _enabled.value = false
    }

    fun consumeNotice() {
        _notice.value = null
    }
}
