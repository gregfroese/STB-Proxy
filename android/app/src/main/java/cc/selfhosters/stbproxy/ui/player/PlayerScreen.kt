package cc.selfhosters.stbproxy.ui.player

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import cc.selfhosters.stbproxy.R

/**
 * Placeholder for the split player + now/next screen (spec 2.6). Media3
 * (`PlayerSurface`, ExoPlayer) lands in the playback ticket.
 *
 * [portal]/[channelId] identify the channel to play and [launchBlock] is the
 * Block it was launched from — the zap list for channel up/down (spec 2.6).
 */
@Composable
fun PlayerScreen(
    portal: String,
    channelId: String,
    launchBlock: String,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(R.string.player_title),
            style = MaterialTheme.typography.headlineSmall,
        )
        Text(
            text = "Player placeholder.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (channelId.isNotBlank()) {
            Text(
                text = "Channel $portal/$channelId · Block: $launchBlock",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
