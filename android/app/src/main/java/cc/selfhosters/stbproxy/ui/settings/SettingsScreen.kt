package cc.selfhosters.stbproxy.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.BuildConfig
import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.AppTextField
import cc.selfhosters.stbproxy.ui.common.ScreenGutter
import cc.selfhosters.stbproxy.ui.common.ScreenHeader
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.common.isTvDevice

/**
 * Settings (spec 2.4): edit the proxy URL, add/switch/remove accounts, sign out.
 * Adding an account reuses the same *Connect* probe as the login form.
 */
@Composable
fun SettingsScreen() {
    val container = LocalAppContainer.current
    val viewModel: SettingsViewModel = viewModel(
        factory = SettingsViewModel.factory(
            container.sessionController,
            container.accountStore,
            container.viewerPreferences,
        ),
    )
    val state by viewModel.state.collectAsStateWithLifecycle()

    // TV: start on the first setting rather than leaving focus in the nav rail.
    val isTv = isTvDevice()
    val firstFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { if (isTv) runCatching { firstFocus.requestFocus() } }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding(),
    ) {
        ScreenHeader(
            title = "Settings",
            subtitle = "STB Proxy ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})",
        )
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = ScreenGutter, vertical = 8.dp)
                .widthIn(max = 720.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            SettingsSection("Proxy", "The STB-Proxy server this app streams from.") {
                AppTextField(
                    value = state.baseUrl,
                    onValueChange = viewModel::onBaseUrlChange,
                    label = "Proxy address",
                    keyboardType = KeyboardType.Uri,
                    imeAction = ImeAction.Done,
                    modifier = Modifier.focusRequester(firstFocus),
                )
                Button(onClick = viewModel::saveBaseUrl, modifier = Modifier.focusRing()) {
                    Text("Save address")
                }
            }

            SettingsSection(
                "Channel grouping",
                "How Channels and the Guide arrange their rail. Blocks win when the account " +
                    "has any; otherwise channels are grouped by the portal's Genres either way.",
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    GroupMode.entries.forEach { option ->
                        if (option == state.groupMode) {
                            Button(
                                onClick = { viewModel.setGroupMode(option) },
                                modifier = Modifier.focusRing(),
                            ) { Text(option.label) }
                        } else {
                            OutlinedButton(
                                onClick = { viewModel.setGroupMode(option) },
                                modifier = Modifier.focusRing(),
                            ) { Text(option.label) }
                        }
                    }
                }
            }

            SettingsSection("Accounts", "Viewer accounts saved on this device.") {
                if (state.accounts.isEmpty()) {
                    Text(
                        text = "No accounts saved.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    state.accounts.forEach { username ->
                        AccountRow(
                            username = username,
                            active = username == state.activeUsername,
                            enabled = !state.busy,
                            onSwitch = { viewModel.switchTo(username) },
                            onRemove = { viewModel.remove(username) },
                        )
                    }
                }
                HorizontalDivider()
                Text("Add account", style = MaterialTheme.typography.titleSmall)
                AppTextField(
                    value = state.addUsername,
                    onValueChange = viewModel::onAddUsernameChange,
                    label = "Username",
                )
                AppTextField(
                    value = state.addPassword,
                    onValueChange = viewModel::onAddPasswordChange,
                    label = "Password",
                    password = true,
                    imeAction = ImeAction.Done,
                )
                Button(
                    onClick = viewModel::addAccount,
                    enabled = !state.busy,
                    modifier = Modifier.focusRing(),
                ) { Text(if (state.busy) "Checking…" else "Add account") }

                state.message?.let {
                    Text(text = it, color = MaterialTheme.colorScheme.primary)
                }
                state.error?.let {
                    Text(text = it, color = MaterialTheme.colorScheme.error)
                }
            }

            SettingsSection("Sign out", "Forget the active account on this device.") {
                OutlinedButton(
                    onClick = viewModel::signOut,
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.error,
                    ),
                    modifier = Modifier.focusRing(),
                ) { Text("Sign out") }
            }
        }
    }
}

/** A titled card grouping related settings. */
@Composable
private fun SettingsSection(
    title: String,
    description: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column {
            Text(title, style = MaterialTheme.typography.titleMedium)
            description?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        content()
    }
}

@Composable
private fun AccountRow(
    username: String,
    active: Boolean,
    enabled: Boolean,
    onSwitch: () -> Unit,
    onRemove: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text(username, style = MaterialTheme.typography.bodyLarge)
            if (active) {
                Text(
                    text = "Active",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            if (!active) {
                TextButton(onClick = onSwitch, enabled = enabled, modifier = Modifier.focusRing()) {
                    Text("Switch")
                }
            }
            TextButton(onClick = onRemove, enabled = enabled, modifier = Modifier.focusRing()) {
                Text("Remove")
            }
        }
    }
}
