package cc.selfhosters.stbproxy.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AccountStoreTest {

    @Test
    fun `base url is normalised on write`() {
        val store = AccountStore(FakeAccountStorage())
        store.setBaseUrl("  192.168.1.10:8000/  ")
        assertEquals("http://192.168.1.10:8000", store.state.value.baseUrl)
    }

    @Test
    fun `multiple accounts share one base url and the latest becomes active`() {
        val store = AccountStore(FakeAccountStorage())
        store.setBaseUrl("proxy.local")
        store.addAccount("katie", "one")
        store.addAccount("greg", "two")

        val state = store.state.value
        assertEquals("http://proxy.local", state.baseUrl)
        assertEquals(listOf("katie", "greg"), state.usernames)
        assertEquals("greg", state.activeUsername)
        assertEquals("greg" to "two", store.activeCredentials())
    }

    @Test
    fun `adding an existing account updates its password and activates it`() {
        val storage = FakeAccountStorage()
        val store = AccountStore(storage)
        store.addAccount("katie", "old")
        store.addAccount("katie", "new")

        assertEquals(listOf("katie"), store.state.value.usernames)
        assertEquals("katie" to "new", store.activeCredentials())
        assertEquals(1, storage.passwordCount())
    }

    @Test
    fun `switching changes the active credentials`() {
        val store = AccountStore(FakeAccountStorage())
        store.addAccount("katie", "one")
        store.addAccount("greg", "two")

        store.setActive("katie")

        assertEquals("katie", store.state.value.activeUsername)
        assertEquals("katie" to "one", store.activeCredentials())
    }

    @Test
    fun `removing the active account promotes another`() {
        val store = AccountStore(FakeAccountStorage())
        store.addAccount("katie", "one")
        store.addAccount("greg", "two")

        store.removeAccount("greg")

        assertEquals(listOf("katie"), store.state.value.usernames)
        assertEquals("katie", store.state.value.activeUsername)
        assertEquals("katie" to "one", store.activeCredentials())
    }

    @Test
    fun `removing a non-active account leaves the active one`() {
        val store = AccountStore(FakeAccountStorage())
        store.addAccount("katie", "one")
        store.addAccount("greg", "two")
        store.setActive("katie")

        store.removeAccount("greg")

        assertEquals("katie", store.state.value.activeUsername)
        assertFalse(store.state.value.usernames.contains("greg"))
    }

    @Test
    fun `sign out clears active but keeps saved accounts`() {
        val store = AccountStore(FakeAccountStorage())
        store.setBaseUrl("proxy.local")
        store.addAccount("katie", "one")

        store.signOut()

        val state = store.state.value
        assertNull(state.activeUsername)
        assertEquals(listOf("katie"), state.usernames)
        assertEquals("http://proxy.local", state.baseUrl)
        assertNull(store.activeCredentials())
    }

    @Test
    fun `active credentials are null when nothing is stored`() {
        val store = AccountStore(FakeAccountStorage())
        assertNull(store.activeCredentials())
        assertTrue(store.state.value.usernames.isEmpty())
    }

    @Test
    fun `switching to an unknown account is ignored`() {
        val store = AccountStore(FakeAccountStorage())
        store.addAccount("katie", "one")
        store.setActive("nobody")
        assertEquals("katie", store.state.value.activeUsername)
    }
}
