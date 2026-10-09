package com.trackguard.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val TrackGuardColors = darkColorScheme(
    primary = androidx.compose.ui.graphics.Color(0xFF6C63FF),
    secondary = androidx.compose.ui.graphics.Color(0xFF3DDC97),
    tertiary = androidx.compose.ui.graphics.Color(0xFFFFC857),
    background = androidx.compose.ui.graphics.Color(0xFF111827),
    surface = androidx.compose.ui.graphics.Color(0xFF1F2937),
    onPrimary = androidx.compose.ui.graphics.Color.White,
    onBackground = androidx.compose.ui.graphics.Color.White,
    onSurface = androidx.compose.ui.graphics.Color.White,
)

@Composable
fun TrackGuardTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = TrackGuardColors,
        content = content,
    )
}
