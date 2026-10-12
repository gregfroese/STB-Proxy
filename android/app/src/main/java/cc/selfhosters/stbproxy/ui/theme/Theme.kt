package cc.selfhosters.stbproxy.ui.theme

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

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
    ) {
        // A Surface gives every screen the app background and a light default content
        // colour, so Text that doesn't set its own colour is readable (not the Compose
        // default black on our dark background).
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background,
            contentColor = MaterialTheme.colorScheme.onBackground,
            content = content,
        )
    }
}
