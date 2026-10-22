package cc.selfhosters.stbproxy.ui.picker

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text as M3Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.Text as TvText
import cc.selfhosters.stbproxy.ui.common.ScreenGutter

/**
 * TV Block rail: a vertical, D-pad-focusable list of Blocks (spec 2.5/2.10).
 * While searching it shows a "Results" row plus per-Block match counts, dimmed
 * at zero, and rows are disabled (navigation suspended).
 */
@Composable
internal fun TvBlockRail(
    rail: List<BlockEntry>,
    activeBlock: String?,
    searching: Boolean,
    resultCount: Int,
    blockCounts: Map<String, Int>,
    palette: PickerPalette,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier
            .fillMaxHeight()
            .width(180.dp)
            .focusGroup()
            .padding(vertical = 8.dp),
        contentPadding = PaddingValues(horizontal = 10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (searching) {
            item(key = "__results__") {
                TvRailRow(
                    name = "Results",
                    count = resultCount,
                    selected = true,
                    dimmed = false,
                    enabled = false,
                    palette = palette,
                    onClick = {},
                )
            }
        }
        items(rail, key = { it.name }) { entry ->
            val count = if (searching) blockCounts[entry.name] ?: 0 else entry.count
            TvRailRow(
                name = entry.name,
                count = count,
                selected = !searching && entry.name == activeBlock,
                dimmed = searching && count == 0,
                enabled = !searching,
                palette = palette,
                onClick = { onSelect(entry.name) },
            )
        }
    }
}

@Composable
private fun TvRailRow(
    name: String,
    count: Int,
    selected: Boolean,
    dimmed: Boolean,
    enabled: Boolean,
    palette: PickerPalette,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(10.dp)
    val background = when {
        selected -> palette.accent.copy(alpha = 0.18f)
        focused -> palette.surfaceVariant
        else -> Color.Transparent
    }
    val alpha = if (dimmed) 0.38f else 1f

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(background)
            .border(1.dp, if (focused) palette.focus else Color.Transparent, shape)
            .onFocusChanged { focused = it.isFocused }
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TvText(
            text = name,
            color = palette.onSurface.copy(alpha = alpha),
            fontSize = 14.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        TvText(
            text = count.toString(),
            color = palette.muted.copy(alpha = alpha),
            fontSize = 12.sp,
        )
    }
}

/**
 * Phone Block strip: the rail becomes a horizontal row of chips (spec 2.5).
 * Same search behaviour as the TV rail.
 */
@Composable
internal fun PhoneBlockChips(
    rail: List<BlockEntry>,
    activeBlock: String?,
    searching: Boolean,
    resultCount: Int,
    blockCounts: Map<String, Int>,
    palette: PickerPalette,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyRow(
        modifier = modifier
            .fillMaxWidth()
            .focusGroup(),
        contentPadding = PaddingValues(horizontal = ScreenGutter, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        if (searching) {
            item(key = "__results__") {
                PhoneChip(
                    label = "Results $resultCount",
                    selected = true,
                    dimmed = false,
                    enabled = false,
                    palette = palette,
                    onClick = {},
                )
            }
        }
        items(rail, key = { it.name }) { entry ->
            val count = if (searching) blockCounts[entry.name] ?: 0 else entry.count
            PhoneChip(
                label = "${entry.name} $count",
                selected = !searching && entry.name == activeBlock,
                dimmed = searching && count == 0,
                enabled = !searching,
                palette = palette,
                onClick = { onSelect(entry.name) },
            )
        }
    }
}

@Composable
private fun PhoneChip(
    label: String,
    selected: Boolean,
    dimmed: Boolean,
    enabled: Boolean,
    palette: PickerPalette,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(20.dp)
    val background = if (selected) palette.accent.copy(alpha = 0.22f) else palette.surfaceVariant
    val alpha = if (dimmed) 0.38f else 1f

    Box(
        modifier = Modifier
            .clip(shape)
            .background(background)
            .border(1.dp, if (focused) palette.focus else palette.surfaceVariant, shape)
            .onFocusChanged { focused = it.isFocused }
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        M3Text(
            text = label,
            color = palette.onSurface.copy(alpha = alpha),
            fontSize = 12.sp,
            maxLines = 1,
        )
    }
}
