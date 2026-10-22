package cc.selfhosters.stbproxy.ui.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.BuildConfig
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.AppTextField
import cc.selfhosters.stbproxy.ui.common.focusRing

/**
 * First-run Login and re-auth screen (spec 2.4). Nothing else in the app is
 * reachable until *Connect* succeeds. [reason] carries any message the session
 * attached to a forced sign-out (auto-login failure / mid-session 401).
 */
@Composable
fun LoginScreen(reason: String? = null) {
    val container = LocalAppContainer.current
    val viewModel: LoginViewModel = viewModel(
        factory = LoginViewModel.factory(container.sessionController, container.accountStore),
    )
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .safeDrawingPadding()
            .padding(24.dp)
            // Keep the form a readable width on a TV or tablet.
            .wrapContentWidth()
            .widthIn(max = 560.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(text = "STB Proxy", style = MaterialTheme.typography.headlineMedium)
        Text(
            text = "Sign in to your proxy",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        AppTextField(
            value = state.baseUrl,
            onValueChange = viewModel::onBaseUrlChange,
            label = "Proxy address",
            placeholder = "192.168.1.10 or https://host:8000",
            keyboardType = KeyboardType.Uri,
        )
        AppTextField(
            value = state.username,
            onValueChange = viewModel::onUsernameChange,
            label = "Username",
        )
        AppTextField(
            value = state.password,
            onValueChange = viewModel::onPasswordChange,
            label = "Password",
            password = true,
            imeAction = ImeAction.Done,
        )

        val message = state.error ?: reason
        if (message != null) {
            Text(
                text = message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
        }

        Button(
            onClick = viewModel::connect,
            enabled = !state.connecting,
            modifier = Modifier.fillMaxWidth().focusRing(),
        ) {
            if (state.connecting) {
                CircularProgressIndicator(
                    modifier = Modifier.padding(end = 8.dp),
                    strokeWidth = 2.dp,
                )
            }
            Text(if (state.connecting) "Connecting…" else "Connect")
        }

        Text(
            text = "STB Proxy ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
}
