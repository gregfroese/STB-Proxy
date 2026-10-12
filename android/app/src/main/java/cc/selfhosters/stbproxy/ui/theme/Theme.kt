package cc.selfhosters.stbproxy.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val AppColorScheme = darkColorScheme(
    primary = BrandAccent,
    onPrimary = BrandBackground,
    secondary = BrandAccent,
    background = BrandBackground,
    onBackground = BrandOn,
    surface = BrandSurface,
    onSurface = BrandOn,
    onSurfaceVariant = BrandMuted,
)

@Composable
fun StbProxyTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = AppColorScheme,
        typography = AppTypography,
        content = content,
    )
}
