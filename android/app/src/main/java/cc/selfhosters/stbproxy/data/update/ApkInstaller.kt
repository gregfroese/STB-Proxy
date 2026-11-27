package cc.selfhosters.stbproxy.data.update

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import java.io.File

/** Hands a downloaded APK to the system installer. An interface so the update flow is testable. */
interface ApkInstaller {
    /** Whether this app may ask the system to install packages ("unknown sources"). */
    fun canInstall(): Boolean

    /**
     * Opens the system page where the viewer allows this app to install apps.
     * False when the device has no such page (some Android TV builds).
     */
    fun openInstallPermission(): Boolean

    /** Starts the system installer on [apk]; throws when there is no installer to open. */
    fun install(apk: File)
}

/**
 * The real installer: the APK is shared through the `${applicationId}.updates`
 * [FileProvider] (see `res/xml/update_paths.xml`, which covers `cacheDir/updates/`).
 * minSdk is 26, so `canRequestPackageInstalls()` and the unknown-sources settings page
 * are always available as APIs.
 */
class AndroidApkInstaller(context: Context) : ApkInstaller {

    private val context = context.applicationContext

    override fun canInstall(): Boolean = context.packageManager.canRequestPackageInstalls()

    override fun openInstallPermission(): Boolean {
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${context.packageName}"),
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            context.startActivity(intent)
            true
        } catch (e: ActivityNotFoundException) {
            false
        } catch (e: SecurityException) {
            false
        }
    }

    override fun install(apk: File) {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.updates", apk)
        val flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK

        @Suppress("DEPRECATION") // Still the installer's own action; ACTION_VIEW is the fallback.
        val install = Intent(Intent.ACTION_INSTALL_PACKAGE)
            .setDataAndType(uri, APK_MIME_TYPE)
            .addFlags(flags)
        try {
            context.startActivity(install)
        } catch (e: ActivityNotFoundException) {
            context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, APK_MIME_TYPE).addFlags(flags))
        }
    }

    companion object {
        const val APK_MIME_TYPE = "application/vnd.android.package-archive"
    }
}
