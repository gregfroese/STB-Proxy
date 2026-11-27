package cc.selfhosters.stbproxy.ui.settings

import cc.selfhosters.stbproxy.data.model.CompanionRelease
import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.update.ApkInstaller
import cc.selfhosters.stbproxy.data.update.isNewerVersion
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException

/** The Settings "App" section: whether the server offers a newer Companion, and the update's progress. */
sealed interface AppUpdateState {
    /** Asking the server what it offers. */
    data object Checking : AppUpdateState

    /** The server offers nothing newer (or no APK at all). */
    data object UpToDate : AppUpdateState

    /** The check failed (server unreachable, bad reply). */
    data object CheckFailed : AppUpdateState

    /**
     * [release] is newer than this app. [message] says what to do next (allow installs
     * from this app); [error] is why the last download or install failed.
     */
    data class Available(
        val release: CompanionRelease,
        val message: String? = null,
        val error: String? = null,
    ) : AppUpdateState

    /** Downloading [release]; [percent] is null while the size is unknown. */
    data class Downloading(val release: CompanionRelease, val percent: Int? = null) : AppUpdateState
}

/**
 * Checks the server's Companion APK (`GET /api/companion`) against [currentVersion] and,
 * on Update, downloads it into [updatesDir] (removing older files there) and hands it to
 * [installer]. When this app may not install packages yet, Update opens the system page
 * to allow it instead and asks the viewer to press Update again.
 *
 * Calls are expected on the main thread.
 */
class AppUpdateController(
    private val api: ApiClient,
    private val updatesDir: File,
    private val installer: ApkInstaller,
    private val scope: CoroutineScope,
    private val currentVersion: String,
) {
    private val _state = MutableStateFlow<AppUpdateState>(AppUpdateState.Checking)
    val state: StateFlow<AppUpdateState> = _state.asStateFlow()

    private var job: Job? = null

    /** Asks the server again (the screen opening, or Check again). Ignored while busy. */
    fun check() {
        if (job?.isActive == true) return
        _state.value = AppUpdateState.Checking
        job = scope.launch {
            _state.value = try {
                val release = api.fetchCompanion()
                if (release != null && isNewerVersion(release.versionName, currentVersion)) {
                    AppUpdateState.Available(release)
                } else {
                    AppUpdateState.UpToDate
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                AppUpdateState.CheckFailed
            }
        }
    }

    /** The Update button: download and install, or first ask for permission to install. */
    fun update() {
        val release = (_state.value as? AppUpdateState.Available)?.release ?: return
        if (job?.isActive == true) return
        if (!installer.canInstall()) {
            val opened = installer.openInstallPermission()
            _state.value = AppUpdateState.Available(
                release,
                message = if (opened) ALLOW_INSTALLS else ALLOW_INSTALLS_MANUALLY,
            )
            return
        }
        _state.value = AppUpdateState.Downloading(release)
        job = scope.launch {
            val apk = try {
                download(release)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.value = AppUpdateState.Available(release, error = DOWNLOAD_FAILED)
                return@launch
            }
            _state.value = try {
                installer.install(apk)
                AppUpdateState.Available(release)
            } catch (e: Exception) {
                AppUpdateState.Available(release, error = INSTALL_FAILED)
            }
        }
    }

    /**
     * Downloads [release] into [updatesDir], first clearing everything there (older
     * updates, an earlier copy of this one). Always fetched fresh: a server can rebuild
     * an APK without changing its version.
     */
    private suspend fun download(release: CompanionRelease): File = withContext(Dispatchers.IO) {
        updatesDir.listFiles()?.forEach { it.deleteRecursively() }
        if (!updatesDir.isDirectory && !updatesDir.mkdirs()) throw IOException("Can't create $updatesDir")
        val name = apkFileName(release.versionName)
        val target = File(updatesDir, name)
        val partial = File(updatesDir, "$name.part")
        try {
            api.downloadCompanion(release, partial) { read, total -> onProgress(read, total) }
            if (!partial.renameTo(target)) throw IOException("Can't save $target")
        } finally {
            partial.delete()
        }
        target
    }

    private fun onProgress(read: Long, total: Long?) {
        val percent = total?.let { ((read * 100) / it).toInt().coerceIn(0, 100) }
        _state.update { current ->
            if (current is AppUpdateState.Downloading && current.percent != percent) {
                current.copy(percent = percent)
            } else {
                current
            }
        }
    }

    companion object {
        const val ALLOW_INSTALLS = "Allow STB Proxy to install apps, then press Update again."
        const val ALLOW_INSTALLS_MANUALLY =
            "Allow installs from STB Proxy in Settings → Apps → Security & restrictions → " +
                "Unknown sources, then press Update again."
        const val DOWNLOAD_FAILED = "Couldn't download the update."
        const val INSTALL_FAILED = "Couldn't open the installer."

        /** `STB-Proxy-Companion-1.14.0.apk`, with anything odd in the version replaced. */
        fun apkFileName(versionName: String): String =
            "STB-Proxy-Companion-${versionName.replace(Regex("[^A-Za-z0-9._-]"), "_")}.apk"
    }
}
