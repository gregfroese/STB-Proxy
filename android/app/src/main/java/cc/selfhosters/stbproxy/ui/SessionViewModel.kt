package cc.selfhosters.stbproxy.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import cc.selfhosters.stbproxy.data.SessionController
import kotlinx.coroutines.launch

/**
 * Kicks off auto-login exactly once when the app root is first composed
 * (spec 2.4). Session state itself lives in [SessionController].
 */
class SessionViewModel(session: SessionController) : ViewModel() {

    init {
        viewModelScope.launch { session.autoLogin() }
    }

    companion object {
        fun factory(session: SessionController): ViewModelProvider.Factory = viewModelFactory {
            initializer { SessionViewModel(session) }
        }
    }
}
