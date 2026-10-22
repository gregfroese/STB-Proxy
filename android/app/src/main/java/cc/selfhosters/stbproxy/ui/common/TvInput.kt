package cc.selfhosters.stbproxy.ui.common

import android.content.res.Configuration
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp

/** True on an Android TV (leanback) device. */
@Composable
fun isTvDevice(): Boolean =
    LocalConfiguration.current.uiMode and Configuration.UI_MODE_TYPE_MASK ==
        Configuration.UI_MODE_TYPE_TELEVISION

/** What a [TvEditable] hands its text field. */
class TvFieldHooks(
    /** Goes on the text field itself. */
    val modifier: Modifier,
    /** Call from the field's keyboard action (Done / Search / Next). */
    val onImeAction: () -> Unit,
)

/**
 * Makes a text field usable with a remote.
 *
 * On TV a focused text field raises the keyboard straight away and then swallows
 * the D-pad, so walking past one traps you in it. Here the field sits behind a
 * focusable box instead: the D-pad moves over it like a button, OK starts typing
 * (focus + keyboard), and the keyboard's action key, D-pad Up/Down or Back hand the
 * remote back. On phones the field is passed through untouched.
 */
@Composable
fun TvEditable(
    modifier: Modifier = Modifier,
    shape: Shape = RoundedCornerShape(12.dp),
    onEditingChange: (Boolean) -> Unit = {},
    content: @Composable (TvFieldHooks) -> Unit,
) {
    if (!isTvDevice()) {
        Box(modifier = modifier) { content(TvFieldHooks(Modifier, onImeAction = {})) }
        return
    }

    val boxFocus = remember { FocusRequester() }
    val fieldFocus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current
    var editing by remember { mutableStateOf(false) }
    var focused by remember { mutableStateOf(false) }

    LaunchedEffect(editing) {
        onEditingChange(editing)
        if (editing) {
            runCatching { fieldFocus.requestFocus() }
            keyboard?.show()
        }
    }

    fun finish(direction: FocusDirection?) {
        keyboard?.hide()
        if (direction == null || !focusManager.moveFocus(direction)) {
            runCatching { boxFocus.requestFocus() }
        }
        editing = false
    }

    BackHandler(enabled = editing) { finish(null) }

    val fieldModifier = Modifier
        .focusRequester(fieldFocus)
        .focusProperties { canFocus = editing }
        .onFocusChanged { if (editing && !it.isFocused) editing = false }
        .onPreviewKeyEvent { event ->
            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
            when (event.key) {
                Key.DirectionDown -> { finish(FocusDirection.Down); true }
                Key.DirectionUp -> { finish(FocusDirection.Up); true }
                else -> false
            }
        }

    Box(
        modifier = modifier
            .focusRequester(boxFocus)
            .onFocusChanged { focused = it.hasFocus }
            .border(
                width = if (focused) 3.dp else 0.dp,
                color = if (focused) TvFocusColor else Color.Transparent,
                shape = shape,
            )
            .clickable { editing = true },
    ) {
        content(TvFieldHooks(fieldModifier, onImeAction = { finish(FocusDirection.Down) }))
    }
}

/**
 * The app's standard labelled text field: an outlined field that behaves on TV
 * (see [TvEditable]) and as a normal field on phones.
 */
@Composable
fun AppTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    placeholder: String? = null,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Next,
    password: Boolean = false,
) {
    val isTv = isTvDevice()
    TvEditable(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(6.dp)) { hooks ->
        // On TV every keyboard action key hands the remote back; on phones keep the
        // defaults (Next moves to the next field, Done closes the keyboard).
        val actions = if (isTv) {
            KeyboardActions(
                onDone = { hooks.onImeAction() },
                onNext = { hooks.onImeAction() },
                onGo = { hooks.onImeAction() },
                onSearch = { hooks.onImeAction() },
            )
        } else {
            KeyboardActions.Default
        }
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            label = { Text(label) },
            placeholder = placeholder?.let { { Text(it) } },
            singleLine = true,
            visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(
                keyboardType = if (password) KeyboardType.Password else keyboardType,
                imeAction = imeAction,
            ),
            keyboardActions = actions,
            modifier = hooks.modifier.fillMaxWidth(),
        )
    }
}
