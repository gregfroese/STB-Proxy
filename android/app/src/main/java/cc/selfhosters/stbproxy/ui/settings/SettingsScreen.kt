package cc.selfhosters.stbproxy.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.BuildConfig
import cc.selfhosters.stbproxy.data.GroupMode
import cc.selfhosters.stbproxy.di.LocalAppContainer

/**
 * Settings (spec 2.4): edit the proxy URL, add/switch/remove accounts, sign out.
 * Adding an account reuses the same *Connect* probe as the login form.
 */
@Composable
fun SettingsScreen(onBack: () -> Unit = {}) {
    val container = LocalAppContainer.current
    val viewModel: SettingsViewModel = viewModel(
        factory = SettingsViewModel.factory(
            container.sessionController,
            container.accountStore,
            container.viewerPreferences,
        ),
    )
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .safeDrawingPadding()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Settings", style = MaterialTheme.typography.headlineSmall)
            TextButton(onClick = onBack) { Text("Back") }
        }

        Text("Proxy address", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = state.baseUrl,
            onValueChange = viewModel::onBaseUrlChange,
            label = { Text("Proxy address") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(onClick = viewModel::saveBaseUrl) { Text("Save address") }

        HorizontalDivider()

        Text("Channel grouping", style = MaterialTheme.typography.titleMedium)
        Text(
            text = "How the picker arranges its rail. Blocks win when the account has any; " +
                "otherwise the picker groups by the portal's Genres either way.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GroupMode.entries.forEach { option ->
                if (option == state.groupMode) {
                    Button(onClick = { viewModel.setGroupMode(option) }) { Text(option.label) }
                } else {
                    OutlinedButton(onClick = { viewModel.setGroupMode(option) }) { Text(option.label) }
                }
            }
        }

        HorizontalDivider()

        Text("Accounts", style = MaterialTheme.typography.titleMedium)
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

        Text("Add account", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = state.addUsername,
            onValueChange = viewModel::onAddUsernameChange,
            label = { Text("Username") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = state.addPassword,
            onValueChange = viewModel::onAddPasswordChange,
            label = { Text("Password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = viewModel::addAccount,
            enabled = !state.busy,
        ) { Text(if (state.busy) "Checking…" else "Add account") }

        state.message?.let {
            Text(text = it, color = MaterialTheme.colorScheme.primary)
        }
        state.error?.let {
            Text(text = it, color = MaterialTheme.colorScheme.error)
        }

        HorizontalDivider()

        OutlinedButton(onClick = viewModel::signOut) { Text("Sign out") }

        Text(
            text = "STB Proxy ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp),
        )
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
            TextButton(onClick = onSwitch, enabled = enabled && !active) { Text("Switch") }
            TextButton(onClick = onRemove, enabled = enabled) { Text("Remove") }
        }
    }
}
