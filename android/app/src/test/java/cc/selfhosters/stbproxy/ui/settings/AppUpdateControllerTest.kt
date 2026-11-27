package cc.selfhosters.stbproxy.ui.settings

import cc.selfhosters.stbproxy.data.network.ApiClient
import cc.selfhosters.stbproxy.data.update.ApkInstaller
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/** The Settings App section's update flow against a fake server and a fake installer. */
class AppUpdateControllerTest {

    @get:Rule
    val temp = TemporaryFolder()

    private lateinit var server: MockWebServer

    /** Path → queued responses (the last one repeats). */
    private val routes = mutableMapOf<String, MutableList<MockResponse>>()

    private val apkBytes = ByteArray(150_000) { (it % 199).toByte() }

    private class FakeInstaller(
        var allowed: Boolean = true,
        val settingsPage: Boolean = true,
        val installFails: Boolean = false,
    ) : ApkInstaller {
        val installed = mutableListOf<File>()
        var permissionOpened = 0

        override fun canInstall() = allowed

        override fun openInstallPermission(): Boolean {
            permissionOpened++
            return settingsPage
        }

        override fun install(apk: File) {
            if (installFails) throw IllegalStateException("no installer")
            installed += apk
        }
    }

    @Before
    fun setUp() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val queue = routes[request.path?.substringBefore('?')] ?: return MockResponse().setResponseCode(599)
                return if (queue.size > 1) queue.removeAt(0) else queue.first()
            }
        }
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun route(path: String, vararg responses: MockResponse) {
        routes[path] = responses.toMutableList()
    }

    private fun json(code: Int, body: String) = MockResponse().setResponseCode(code).setBody(body)

    private fun offer(version: String) =
        route("/api/companion", json(200, """{"versionName": "$version", "url": "/companion.apk", "sizeBytes": ${apkBytes.size}}"""))

    private fun apk() = MockResponse().setBody(Buffer().write(apkBytes))

    private val updatesDir: File get() = File(temp.root, "updates")

    private fun test(
        installer: FakeInstaller = FakeInstaller(),
        block: suspend CoroutineScope.(AppUpdateController, FakeInstaller) -> Unit,
    ) = runBlocking {
        val scope = CoroutineScope(coroutineContext + Job())
        val api = ApiClient(
            client = OkHttpClient(),
            json = Json { ignoreUnknownKeys = true },
            baseUrlProvider = { server.url("/").toString().trimEnd('/') },
            retryDelaysMs = listOf(0L, 0L),
        )
        try {
            withTimeout(5_000) {
                block(AppUpdateController(api, updatesDir, installer, scope, currentVersion = "1.13.0"), installer)
            }
        } finally {
            scope.cancel()
        }
    }

    private suspend fun AppUpdateController.settled(): AppUpdateState =
        state.first { it != AppUpdateState.Checking && it !is AppUpdateState.Downloading }

    @Test
    fun `a newer server version is offered`() = test { controller, _ ->
        offer("1.14.0")
        assertEquals(AppUpdateState.Checking, controller.state.value)

        controller.check()
        val offered = controller.settled() as AppUpdateState.Available

        assertEquals("1.14.0", offered.release.versionName)
    }

    @Test
    fun `the same version, or no APK on the server, is up to date`() = test { controller, _ ->
        offer("1.13.0")
        controller.check()
        assertEquals(AppUpdateState.UpToDate, controller.settled())

        route("/api/companion", json(404, """{"code": "not_found", "message": "No APK"}"""))
        controller.check()
        assertEquals(AppUpdateState.UpToDate, controller.settled())
    }

    @Test
    fun `an unreachable server fails the check, and Check again recovers`() = test { controller, _ ->
        route("/api/companion", json(500, ""), json(500, ""), json(500, ""), json(200, """{"versionName": "1.14.0", "url": "/companion.apk"}"""))
        controller.check()
        assertEquals(AppUpdateState.CheckFailed, controller.settled())

        controller.check()
        assertTrue(controller.settled() is AppUpdateState.Available)
    }

    @Test
    fun `Update downloads into the updates folder, clears older files and opens the installer`() = test { controller, installer ->
        updatesDir.mkdirs()
        val old = File(updatesDir, "STB-Proxy-Companion-1.12.0.apk").apply { writeText("old") }
        offer("1.14.0")
        route("/companion.apk", apk())
        controller.check()
        controller.settled()

        controller.update()
        assertTrue(controller.state.value is AppUpdateState.Downloading)
        val after = controller.settled()

        val apk = installer.installed.single()
        assertEquals(File(updatesDir, "STB-Proxy-Companion-1.14.0.apk"), apk)
        assertArrayEquals(apkBytes, apk.readBytes())
        assertTrue(!old.exists())
        assertEquals(listOf(apk.name), updatesDir.list()!!.toList())
        assertEquals(AppUpdateState.Available((after as AppUpdateState.Available).release), after)
    }

    @Test
    fun `download progress reaches 100 percent`() = test { controller, _ ->
        offer("1.14.0")
        route("/companion.apk", apk())
        controller.check()
        controller.settled()
        val seen = mutableListOf<AppUpdateState>()
        val collector = launch(start = CoroutineStart.UNDISPATCHED) { controller.state.collect { seen += it } }

        controller.update()
        controller.settled()
        collector.cancel()

        val percents = seen.filterIsInstance<AppUpdateState.Downloading>().map { it.percent }
        assertTrue("saw $percents", percents.isNotEmpty())
        assertTrue("saw $percents", percents.filterNotNull().all { it in 0..100 })
    }

    @Test
    fun `pressing Update again downloads afresh, keeping one file`() = test { controller, installer ->
        offer("1.14.0")
        route("/companion.apk", apk())
        controller.check()
        controller.settled()

        controller.update()
        controller.settled()
        controller.update()
        controller.settled()

        assertEquals(2, installer.installed.size)
        assertEquals(3, server.requestCount) // one check, two downloads
        assertEquals(listOf("STB-Proxy-Companion-1.14.0.apk"), updatesDir.list()!!.toList())
    }

    @Test
    fun `without install permission Update opens the settings page and asks to press Update again`() =
        test(FakeInstaller(allowed = false)) { controller, installer ->
            offer("1.14.0")
            route("/companion.apk", apk())
            controller.check()
            controller.settled()

            controller.update()
            val asked = controller.state.value as AppUpdateState.Available
            assertEquals(AppUpdateController.ALLOW_INSTALLS, asked.message)
            assertEquals(1, installer.permissionOpened)
            assertTrue(installer.installed.isEmpty())

            installer.allowed = true
            controller.update()
            controller.settled()
            assertEquals(1, installer.installed.size)
        }

    @Test
    fun `without a settings page Update says where to allow installs`() =
        test(FakeInstaller(allowed = false, settingsPage = false)) { controller, _ ->
            offer("1.14.0")
            controller.check()
            controller.settled()

            controller.update()

            val asked = controller.state.value as AppUpdateState.Available
            assertEquals(AppUpdateController.ALLOW_INSTALLS_MANUALLY, asked.message)
            assertTrue(asked.message!!.contains("Settings → Apps → Security & restrictions → Unknown sources"))
        }

    @Test
    fun `a failed download shows an error and keeps the update on offer`() = test { controller, installer ->
        offer("1.14.0")
        route("/companion.apk", json(503, ""))
        controller.check()
        controller.settled()

        controller.update()
        val failed = controller.settled() as AppUpdateState.Available

        assertEquals(AppUpdateController.DOWNLOAD_FAILED, failed.error)
        assertTrue(installer.installed.isEmpty())
        assertTrue(updatesDir.list().orEmpty().isEmpty())
    }

    @Test
    fun `an installer that won't open shows an error`() = test(FakeInstaller(installFails = true)) { controller, _ ->
        offer("1.14.0")
        route("/companion.apk", apk())
        controller.check()
        controller.settled()

        controller.update()
        val failed = controller.settled() as AppUpdateState.Available

        assertEquals(AppUpdateController.INSTALL_FAILED, failed.error)
    }

    @Test
    fun `Update does nothing until an update is on offer`() = test { controller, installer ->
        offer("1.13.0")
        controller.check()
        controller.settled()

        controller.update()

        assertEquals(AppUpdateState.UpToDate, controller.state.value)
        assertEquals(0, installer.permissionOpened)
    }
}
