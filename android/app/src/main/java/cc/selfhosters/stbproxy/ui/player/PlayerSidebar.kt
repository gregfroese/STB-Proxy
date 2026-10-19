package cc.selfhosters.stbproxy.ui.player

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cc.selfhosters.stbproxy.data.epg.NowNext
import cc.selfhosters.stbproxy.data.epg.Programme
import cc.selfhosters.stbproxy.data.model.Channel
import java.time.Instant
import java.time.ZoneId

/** Fixed width of the TV sidebar. */
val SidebarWidth = 340.dp

/**
 * The persistent now/next sidebar (spec 2.6). On TV it is a right-hand pane; on
 * phone the same content fills the bottom sheet. TV uses a Compose-for-TV
 * surface, phone a mobile Material surface (spec 2.10).
 */
@Composable
fun PlayerSidebar(
    state: PlayerUiState,
    isTv: Boolean,
    onSelectChannel: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (isTv) {
        androidx.tv.material3.Surface(modifier = modifier) {
            SidebarContent(state, onSelectChannel)
        }
    } else {
        androidx.compose.material3.Surface(
            modifier = modifier,
            color = MaterialTheme.colorScheme.surface,
        ) {
            SidebarContent(state, onSelectChannel)
        }
    }
}

@Composable
private fun SidebarContent(
    state: PlayerUiState,
    onSelectChannel: (Int) -> Unit,
) {
    val zone = ZoneId.systemDefault()
    val channel = state.channel
    val resolved = resolveNowNext(channel?.epgId?.let { state.nowNext[it] }, state.now)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 14.dp, vertical = 12.dp),
    ) {
        BasicLabel(
            text = "CH ${channel?.number ?: "—"} · ${state.scopeLabel}",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp,
        )
        BasicLabel(
            text = channel?.name ?: "—",
            color = MaterialTheme.colorScheme.onSurface,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
        )

        Spacer(Modifier.height(10.dp))
        SectionLabel("On now")
        ProgrammeCard(resolved?.now, state.now, zone, showProgress = true)

        SectionLabel("Up next")
        ProgrammeCard(resolved?.next, state.now, zone, showProgress = false)

        SectionLabel("${state.scopeLabel} — channel up/down")
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            itemsIndexed(
                items = state.zapList,
                key = { _, c -> "${c.portal}/${c.channelId}" },
            ) { index, c ->
                ZapRow(
                    channel = c,
                    selected = index == state.currentIndex,
                    nowNext = c.epgId?.let { state.nowNext[it] },
                    now = state.now,
                    onClick = { onSelectChannel(index) },
                )
            }
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    BasicLabel(
        text = text.uppercase(),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 10.sp,
        fontWeight = FontWeight.Medium,
        modifier = Modifier.padding(top = 12.dp, bottom = 5.dp),
    )
}

@Composable
private fun ProgrammeCard(
    programme: Programme?,
    now: Instant,
    zone: ZoneId,
    showProgress: Boolean,
) {
    val scheme = MaterialTheme.colorScheme
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(scheme.surfaceVariant)
            .padding(10.dp),
    ) {
        if (programme == null) {
            BasicLabel("No guide data", scheme.onSurfaceVariant, 13.sp)
            return@Column
        }
        BasicLabel(programme.title, scheme.onSurface, 13.sp, FontWeight.SemiBold, maxLines = 2)
        BasicLabel(programme.timeRange(zone), scheme.onSurfaceVariant, 11.sp)
        programme.description?.let {
            BasicLabel(it, scheme.onSurfaceVariant, 11.sp, maxLines = 2)
        }
        if (showProgress) {
            Spacer(Modifier.height(7.dp))
            ProgressBar(programmeProgress(programme, now))
        }
    }
}

@Composable
private fun ProgressBar(fraction: Float) {
    val scheme = MaterialTheme.colorScheme
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(3.dp)
            .clip(RoundedCornerShape(3.dp))
            .background(scheme.onSurface.copy(alpha = 0.14f)),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth(fraction)
                .fillMaxHeight()
                .background(scheme.primary),
        )
    }
}

@Composable
private fun ZapRow(
    channel: Channel,
    selected: Boolean,
    nowNext: NowNext?,
    now: Instant,
    onClick: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(9.dp)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(if (selected) scheme.primary.copy(alpha = 0.16f) else Color.Transparent)
            .border(1.dp, if (selected) scheme.primary else Color.Transparent, shape)
            .clickable(onClick = onClick)
            .padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ChannelBadge(channel)
        Spacer(Modifier.width(9.dp))
        Column(modifier = Modifier.weight(1f)) {
            BasicLabel(channel.name, scheme.onSurface, 13.sp, maxLines = 1)
            val nowTitle = resolveNowNext(nowNext, now)?.now?.title ?: "No guide data"
            BasicLabel(
                "CH ${channel.number ?: "—"} · $nowTitle",
                scheme.onSurfaceVariant,
                11.sp,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun ChannelBadge(channel: Channel) {
    val scheme = MaterialTheme.colorScheme
    Box(
        modifier = Modifier
            .size(34.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(scheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        BasicLabel(initials(channel.name), scheme.onSurfaceVariant, 12.sp, FontWeight.Bold)
    }
}

@Composable
private fun BasicLabel(
    text: String,
    color: Color,
    fontSize: TextUnit,
    fontWeight: FontWeight? = null,
    modifier: Modifier = Modifier,
    maxLines: Int = Int.MAX_VALUE,
) {
    BasicText(
        text = text,
        modifier = modifier,
        style = TextStyle(color = color, fontSize = fontSize, fontWeight = fontWeight),
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
    )
}

private fun initials(name: String): String =
    name.split(' ')
        .filter { it.isNotBlank() }
        .map { it.first().uppercaseChar() }
        .joinToString("")
        .take(2)
