package cc.selfhosters.stbproxy.ui.picker

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cc.selfhosters.stbproxy.R
import cc.selfhosters.stbproxy.data.network.NO_CHANNELS_NOTICE
import cc.selfhosters.stbproxy.data.network.SECURITY_OFF_NOTICE
import cc.selfhosters.stbproxy.di.LocalAppContainer

/**
 * Walking-skeleton channel list (ticket 06): a bare, scrollable list of the
 * account's channel names on both phone and TV. The Block-grouped rail + grid
 * (spec 2.5) replaces this in the picker ticket.
 */
@Composable
fun PickerScreen(
    onChannelClick: () -> Unit,
    onOpenSettings: () -> Unit,
    viewModel: PickerViewModel = viewModel(
        factory = PickerViewModel.factory(
            LocalAppContainer.current.apiClient,
            LocalAppContainer.current.sessionController,
        ),
    ),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(
                    text = stringResource(R.string.picker_title),
                    style = MaterialTheme.typography.headlineSmall,
                )
                state.accountLabel?.let { label ->
                    Text(
                        text = label,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            TextButton(onClick = onOpenSettings) {
                Text(stringResource(R.string.nav_settings))
            }
        }

        if (state.credentialsUnverified) {
            Text(
                text = SECURITY_OFF_NOTICE,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        when {
            state.loading -> CenteredMessage {
                CircularProgressIndicator()
            }

            state.error != null -> CenteredMessage {
                Text(
                    text = state.error ?: "",
                    color = MaterialTheme.colorScheme.error,
                )
                Button(onClick = viewModel::refresh) {
                    Text("Retry")
                }
            }

            state.channels.isEmpty() -> CenteredMessage {
                Text(
                    text = NO_CHANNELS_NOTICE,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(state.channels) { channel ->
                    Text(
                        text = channel.name,
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable(onClick = onChannelClick)
                            .padding(vertical = 12.dp),
                    )
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun CenteredMessage(content: @Composable () -> Unit) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            content()
        }
    }
}
