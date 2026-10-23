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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cc.selfhosters.stbproxy.data.model.OnDemandDetail
import cc.selfhosters.stbproxy.data.model.OnDemandItem
import cc.selfhosters.stbproxy.data.model.OnDemandPortalStatus
import cc.selfhosters.stbproxy.di.LocalAppContainer
import cc.selfhosters.stbproxy.ui.common.ScreenGutter
import cc.selfhosters.stbproxy.ui.common.focusRing
import cc.selfhosters.stbproxy.ui.picker.PickerPalette
import coil.compose.AsyncImage

private val Watched = Color(0xFF6FCF97)

@Composable
internal fun Label(
    text: String,
    color: Color,
    fontSize: TextUnit,
    modifier: Modifier = Modifier,
    fontWeight: FontWeight? = null,
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

/** A 2:3 poster from `/api/ondemand/poster/...` (sent with the login), or the title as a placeholder. */
@Composable
internal fun Poster(
    poster: String?,
    name: String,
    width: Dp,
    palette: PickerPalette,
    modifier: Modifier = Modifier,
) {
    val url = LocalAppContainer.current.apiClient.onDemandPosterUrl(poster)
    val shape = RoundedCornerShape(if (width < 60.dp) 4.dp else 8.dp)
    Box(
        modifier = modifier
            .size(width = width, height = width * 1.5f)
            .clip(shape)
            .background(palette.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        if (width >= 60.dp) {
            Label(name, palette.muted, 11.sp, maxLines = 3, modifier = Modifier.padding(6.dp))
        }
        if (url != null) {
            AsyncImage(
                model = url,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

/**
 * One title as a list row: a thumbnail, the title, then the facts (or, in Continue
 * watching, what's left), a thin progress line and the Series / ✓ badges.
 */
@Composable
internal fun TitleRow(
    item: OnDemandItem,
    palette: PickerPalette,
    continueRow: Boolean,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    focusRequester: FocusRequester? = null,
    onFocused: () -> Unit = {},
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(10.dp)
    val fraction = rowProgress(item)
    Row(
        modifier = modifier
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .fillMaxWidth()
            .clip(shape)
            .background(if (selected) palette.accent.copy(alpha = 0.14f) else palette.surface)
            .border(
                width = if (focused) 2.dp else 1.dp,
                color = if (focused) palette.focus else palette.surfaceVariant,
                shape = shape,
            )
            .onFocusChanged {
                focused = it.isFocused
                if (it.isFocused) onFocused()
            }
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Poster(item.poster, item.name, 38.dp, palette)
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Label(item.name, palette.onSurface, 14.sp, fontWeight = FontWeight.Medium, maxLines = 1)
            Label(
                if (continueRow) continueSubtitle(item) else factsLine(item),
                palette.muted,
                11.sp,
                maxLines = 1,
                modifier = Modifier.padding(top = 2.dp),
            )
            if (fraction != null) {
                ProgressLine(fraction, palette, Modifier.padding(top = 4.dp))
            }
        }
        if (item.isSeries) {
            Spacer(Modifier.width(6.dp))
            Badge("Series", palette.muted, palette)
        }
        if (item.progress?.watched == true) {
            Spacer(Modifier.width(6.dp))
            Badge("✓", Watched, palette)
        }
    }
}

@Composable
internal fun ProgressLine(fraction: Float, palette: PickerPalette, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(2.dp)
            .background(palette.surfaceVariant),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth(fraction)
                .height(2.dp)
                .background(palette.accent),
        )
    }
}

@Composable
private fun Badge(text: String, color: Color, palette: PickerPalette) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(palette.surfaceVariant)
            .padding(horizontal = 6.dp, vertical = 1.dp),
    ) {
        Label(text, color, 10.sp, maxLines = 1)
    }
}

/** The list's last row: "Loading more… (n of total)", then "n titles"; Retry after a failure. */
@Composable
internal fun ListFooter(list: TitleListState, palette: PickerPalette, onRetry: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        if (list.error != null) {
            Label(loadErrorText(list.error), MaterialTheme.colorScheme.error, 12.sp)
            Button(onClick = onRetry, modifier = Modifier.padding(top = 6.dp).focusRing()) { Text("Try again") }
        } else {
            list.footer?.let { Label(it, palette.muted, 12.sp) }
        }
    }
}

/** Recently added · A–Z · Year · Rating. */
@Composable
internal fun SortChips(
    shown: OnDemandSort?,
    onSort: (OnDemandSort) -> Unit,
    palette: PickerPalette,
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(horizontal = ScreenGutter, vertical = 2.dp),
) {
    LazyRow(
        modifier = modifier.fillMaxWidth(),
        contentPadding = contentPadding,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(OnDemandSort.entries, key = { it.param }) { option ->
            val selected = option == shown
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(if (selected) palette.accent else palette.surfaceVariant)
                    .focusRing(RoundedCornerShape(20.dp))
                    .clickable { onSort(option) }
                    .padding(horizontal = 12.dp, vertical = 6.dp),
            ) {
                Label(option.label, if (selected) palette.background else palette.onSurface, 12.sp, maxLines = 1)
            }
        }
    }
}

/** A pill per portal whose index isn't ready ("Main: Still indexing (42%) — newest first"). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun StatusPills(
    portals: List<OnDemandPortalStatus>,
    palette: PickerPalette,
    modifier: Modifier = Modifier,
) {
    val now = System.currentTimeMillis() / 1000
    val pills = portals.mapNotNull { status -> statusPill(status, now)?.let { status.status to it } }
    if (pills.isEmpty()) return
    FlowRow(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = ScreenGutter, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        pills.forEach { (status, text) ->
            val failed = status == "failed"
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(12.dp))
                    .background(if (failed) Color(0x24FF8A80) else Color(0x1FFFD34D))
                    .padding(horizontal = 9.dp, vertical = 3.dp),
            ) {
                Label(text, if (failed) Color(0xFFFF8A80) else Color(0xFFFFE08A), 11.sp, maxLines = 1)
            }
        }
    }
}

@Composable
internal fun Centered(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            content()
        }
    }
}

/**
 * What the TV preview pane and the phone detail page show of a title until ticket 14
 * adds Play, Seasons and Episodes: the poster, title, `originalName`, facts, the
 * description, credits and "From <portal>". [detail] fills in once it has loaded.
 */
@Composable
internal fun TitleSummary(
    item: OnDemandItem,
    detail: OnDemandDetail?,
    palette: PickerPalette,
    modifier: Modifier = Modifier,
    posterWidth: Dp = 120.dp,
) {
    Column(modifier = modifier) {
        Row {
            Poster(item.poster, item.name, posterWidth, palette)
            Spacer(Modifier.width(16.dp))
            Column(modifier = Modifier.weight(1f)) {
                Label(item.name, palette.onSurface, 22.sp, fontWeight = FontWeight.Medium)
                detail?.originalName?.let { Label(it, palette.muted, 12.sp) }
                Label(
                    detailFacts(item, detail),
                    palette.muted,
                    13.sp,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }
        detail?.description?.let {
            Label(it, palette.onSurface, 13.sp, modifier = Modifier.padding(top = 14.dp))
        }
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
