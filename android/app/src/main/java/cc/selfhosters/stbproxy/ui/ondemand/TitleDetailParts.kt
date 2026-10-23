package cc.selfhosters.stbproxy.ui.ondemand

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.picker.PickerPalette

private val WatchedGreen = Color(0xFF6FCF97)

/** What the detail's buttons and chips do. */
internal class TitleDetailActions(
    val onPlay: (PlayChoice?) -> Unit,
    val onToggleWatched: () -> Unit,
    val onRetry: () -> Unit,
    val onSeason: (String) -> Unit,
)

/**
 * A title's detail, shared by the TV preview pane ([tv]) and the phone detail page:
 * the poster, title, `originalName` and facts; the Play buttons with the inline error
 * under them; a Series' Season chips and Episodes; then the description, genre tags
 * (phone), credits and "From <portal>". [entry] goes on the main Play button (TV:
 * OK/→ on a row lands there).
 */
@Composable
internal fun TitleDetailBody(
    item: OnDemandItem,
    state: TitleDetailState,
    palette: PickerPalette,
    actions: TitleDetailActions,
    tv: Boolean,
    modifier: Modifier = Modifier,
    entry: FocusRequester? = null,
    posterWidth: Dp = 120.dp,
) {
    val detail = state.detail?.takeIf { state.key == itemKey(item) }
    val shown = if (state.key == itemKey(item)) state else TitleDetailState(item = item)
    Column(modifier = modifier) {
        Row {
            Poster(item.poster, item.name, posterWidth, palette)
            Spacer(Modifier.width(16.dp))
            Column(modifier = Modifier.weight(1f)) {
                Label(item.name, palette.onSurface, 22.sp, fontWeight = FontWeight.Medium)
                detail?.originalName?.takeIf { it.isNotBlank() && it != item.name }?.let {
                    Label(it, palette.muted, 12.sp)
                }
                Label(detailFacts(item, detail), palette.muted, 13.sp, modifier = Modifier.padding(top = 6.dp))
            }
        }

        shown.buttons?.let { buttons ->
            PlayActions(buttons, shown.busy, palette, actions, tv, entry, Modifier.padding(top = 16.dp))
        }
        shown.actionError?.let { InlineError(it, palette, actions.onRetry, Modifier.padding(top = 10.dp)) }

        if (detail != null && detail.isSeries && detail.seasons.isNotEmpty()) {
            SeasonsAndEpisodes(shown, palette, actions, Modifier.padding(top = 18.dp))
        }

        detail?.description?.takeIf { it.isNotBlank() }?.let {
            Label(it, palette.onSurface, 13.sp, modifier = Modifier.padding(top = 16.dp))
        }
        if (!tv) detail?.genres?.let { GenreTags(it, palette, Modifier.padding(top = 10.dp)) }
        detail?.let { credits(it) }?.forEach { (label, value) ->
            Row(modifier = Modifier.padding(top = 6.dp)) {
                Label(label, palette.muted, 12.sp, fontWeight = FontWeight.Medium, modifier = Modifier.width(70.dp))
                Label(value, palette.onSurface, 12.sp)
            }
        }
        if (item.portalName.isNotBlank()) {
            Label("From ${item.portalName}", palette.muted, 11.sp, modifier = Modifier.padding(top = 12.dp))
        }
    }
}

/**
 * The Play buttons. TV: one row (Play, Start over, Mark watched), the Series' note
 * beside them. Phone: a full-width Play/Resume, then Start over and Mark watched.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PlayActions(
    buttons: PlayButtons,
    busy: Boolean,
    palette: PickerPalette,
    actions: TitleDetailActions,
    tv: Boolean,
    entry: FocusRequester?,
    modifier: Modifier = Modifier,
) {
    val primary = @Composable { m: Modifier ->
        ActionButton(
            label = buttons.primary.label,
            primary = true,
            enabled = buttons.primary.choice != null,
            busy = busy,
            palette = palette,
            onClick = { actions.onPlay(buttons.primary.choice) },
            modifier = m.then(if (entry != null) Modifier.focusRequester(entry) else Modifier),
        )
    }
    val secondary = @Composable {
        buttons.startOver?.let {
            ActionButton(it.label, false, true, false, palette, { actions.onPlay(it.choice) })
        }
        buttons.watchedToggle?.let {
            ActionButton(
                it,
                primary = false,
                enabled = true,
                busy = false,
                palette = palette,
                onClick = actions.onToggleWatched,
                color = if (it == watchedToggleText(true)) WatchedGreen else null,
            )
        }
    }
    val note = @Composable { m: Modifier ->
        buttons.note?.let { Label(it, palette.muted, 12.sp, maxLines = 2, modifier = m) }
    }
    if (tv) {
        FlowRow(
            modifier = modifier,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            primary(Modifier)
            secondary()
            note(Modifier)
        }
    } else {
        Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            primary(Modifier.fillMaxWidth())
            note(Modifier)
            if (buttons.startOver != null || buttons.watchedToggle != null) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) { secondary() }
            }
        }
    }
}

@Composable
private fun ActionButton(
    label: String,
    primary: Boolean,
    enabled: Boolean,
    busy: Boolean,
    palette: PickerPalette,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    color: Color? = null,
) {
    val shape = RoundedCornerShape(22.dp)
    Box(
        modifier = modifier
            .clip(shape)
            .background(if (primary) palette.accent else palette.surfaceVariant)
            .focusRing(shape)
            // Stays focusable while it can't start yet, so TV focus has somewhere to land.
            .clickable(onClick = { if (enabled && !busy) onClick() })
            .padding(horizontal = 18.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (busy) {
                CircularProgressIndicator(
                    modifier = Modifier.size(14.dp),
                    strokeWidth = 2.dp,
                    color = if (primary) palette.background else palette.onSurface,
                )
                Spacer(Modifier.width(8.dp))
            }
            Label(
                label,
                (color ?: if (primary) palette.background else palette.onSurface)
                    .copy(alpha = if (enabled) 1f else 0.5f),
                14.sp,
                fontWeight = if (primary) FontWeight.Medium else null,
                maxLines = 1,
            )
        }
    }
}

/** The error under Play (or under the Episodes), with Try again. */
@Composable
internal fun InlineError(text: String, palette: PickerPalette, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(MaterialTheme.colorScheme.error.copy(alpha = 0.12f))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Label(text, MaterialTheme.colorScheme.error, 13.sp)
        ActionButton("Try again", false, true, false, palette, onRetry)
    }
}

/** Season chips (opening on Up next's Season), then the chosen Season's Episodes. */
@Composable
private fun SeasonsAndEpisodes(
    state: TitleDetailState,
    palette: PickerPalette,
    actions: TitleDetailActions,
    modifier: Modifier = Modifier,
) {
    val seasons = state.detail?.seasons.orEmpty()
    Column(modifier = modifier) {
        LazyRow(
            modifier = Modifier.fillMaxWidth(),
            contentPadding = PaddingValues(vertical = 2.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(seasons, key = { it.id }) { season ->
                val selected = season.id == state.seasonId
                val shape = RoundedCornerShape(20.dp)
                Box(
                    modifier = Modifier
                        .clip(shape)
                        .background(if (selected) palette.accent else palette.surfaceVariant)
                        .focusRing(shape)
                        .clickable { actions.onSeason(season.id) }
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                ) {
                    Label(
                        season.name?.takeIf { it.isNotBlank() } ?: "Season ${season.number ?: (seasons.indexOf(season) + 1)}",
                        if (selected) palette.background else palette.onSurface,
                        12.sp,
                        maxLines = 1,
                    )
                }
            }
        }
        val rows = state.episodeRows
        when {
            state.episodesError != null && rows == null ->
                InlineError(state.episodesError, palette, actions.onRetry, Modifier.padding(top = 10.dp))
            rows == null -> Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 16.dp),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator(modifier = Modifier.size(24.dp)) }
            rows.isEmpty() -> Label("No Episodes", palette.muted, 13.sp, modifier = Modifier.padding(top = 10.dp))
            else -> Column(
                modifier = Modifier.padding(top = 10.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                rows.forEach { row -> EpisodeRowView(row, palette) { actions.onPlay(row.choice) } }
            }
        }
    }
}

/** One Episode: number, name, "✓ Watched" / "mm:ss in", a thin bar and the Up next badge. */
@Composable
private fun EpisodeRowView(row: EpisodeRow, palette: PickerPalette, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(10.dp)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(if (row.upNext) palette.accent.copy(alpha = 0.14f) else palette.surface)
            .border(
                width = if (focused) 2.dp else 1.dp,
                color = if (focused) palette.focus else palette.surfaceVariant,
                shape = shape,
            )
            .onFocusChanged { focused = it.isFocused }
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Label(row.number, palette.muted, 14.sp, modifier = Modifier.width(30.dp))
        Column(modifier = Modifier.weight(1f)) {
            Label(row.name, palette.onSurface, 14.sp, maxLines = 1)
            row.status?.let {
                Label(
                    it,
                    if (row.watched) WatchedGreen else palette.muted,
                    11.sp,
                    maxLines = 1,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
            row.progress?.let { ProgressLine(it, palette, Modifier.padding(top = 4.dp)) }
        }
        if (row.upNext) {
            Spacer(Modifier.width(8.dp))
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(palette.accent)
                    .padding(horizontal = 8.dp, vertical = 2.dp),
            ) {
                Label("Up next", palette.background, 10.sp, maxLines = 1)
            }
        }
    }
}

/** The phone's genre tags, from the portal's comma-separated genres. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun GenreTags(genres: String, palette: PickerPalette, modifier: Modifier = Modifier) {
    val tags = genres.split(',').map { it.trim() }.filter { it.isNotEmpty() }
    if (tags.isEmpty()) return
    FlowRow(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        tags.forEach {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(12.dp))
                    .background(palette.surfaceVariant)
                    .padding(horizontal = 9.dp, vertical = 3.dp),
            ) {
                Label(it, palette.onSurface, 11.sp, maxLines = 1)
            }
        }
    }
}
