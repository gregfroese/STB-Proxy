package cc.selfhosters.stbproxy.ui.multiview

import cc.selfhosters.stbproxy.data.model.Channel
import cc.selfhosters.stbproxy.ui.player.PlaybackError
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MultiviewLogicTest {

    private fun channel(id: String, name: String = "CH $id"): Channel = Channel(
        portal = "1",
        channelId = id,
        name = name,
        url = "/play/1/$id",
    )

    private val a = channel("1", "BBC One")
    private val b = channel("2", "BBC Two")
    private val c = channel("3", "ITV")
    private val d = channel("4", "C4")

    private fun grid(vararg channels: Channel?): List<MultiviewTile> =
        channels.mapIndexed { index, ch -> MultiviewTile(slot = index, channel = ch) }

    // ---- tuner budgeting (spec 2.7) ----

    @Test
    fun `two distinct channels with two tuners are both playable`() {
        val tiles = grid(a, b)
        assertEquals(setOf(0, 1), withinTunerBudget(tiles, 2))
        assertTrue(overBudgetSlots(tiles, 2).isEmpty())
    }

    @Test
    fun `a third distinct channel is over budget`() {
        val tiles = grid(a, b, c)
        assertEquals(setOf(0, 1), withinTunerBudget(tiles, 2))
        assertEquals(setOf(2), overBudgetSlots(tiles, 2))
    }

    @Test
    fun `two tiles on the same channel cost one tuner`() {
        val tiles = grid(a, a, b)
        // Slots 0 and 1 share channel a (one tuner); slot 2 opens b (the second).
        assertEquals(setOf(0, 1, 2), withinTunerBudget(tiles, 2))
        assertTrue(overBudgetSlots(tiles, 2).isEmpty())
        assertEquals(2, distinctChannelCount(tiles))
    }

    @Test
    fun `empty tiles never consume a tuner`() {
        val tiles = grid(null, a, null, b)
        assertEquals(setOf(1, 3), withinTunerBudget(tiles, 2))
        assertTrue(overBudgetSlots(tiles, 2).isEmpty())
    }

    @Test
    fun `a later duplicate of an overflow channel is still over budget`() {
        // a and b take the two tuners; c (slot 2) and c (slot 3) both overflow,
        // and the duplicate doesn't sneak in.
        val tiles = grid(a, b, c, c)
        assertEquals(setOf(0, 1), withinTunerBudget(tiles, 2))
        assertEquals(setOf(2, 3), overBudgetSlots(tiles, 2))
    }

    @Test
    fun `a zero tuner count is floored to one`() {
        val tiles = grid(a, b)
        assertEquals(setOf(0), withinTunerBudget(tiles, 0))
        assertEquals(setOf(1), overBudgetSlots(tiles, 0))
    }

    @Test
    fun `raising the budget makes previously busy tiles playable`() {
        val tiles = grid(a, b, c)
        assertEquals(setOf(2), overBudgetSlots(tiles, 2))
        assertTrue(overBudgetSlots(tiles, 3).isEmpty())
    }

    // ---- swap (spec 2.7) ----

    @Test
    fun `swap exchanges two tiles' channels`() {
        val swapped = swapTiles(grid(a, b), 0, 1)
        assertEquals(b, swapped[0].channel)
        assertEquals(a, swapped[1].channel)
    }

    @Test
    fun `swap exchanges a filled and an empty tile`() {
        val swapped = swapTiles(grid(a, null), 0, 1)
        assertNull(swapped[0].channel)
        assertEquals(a, swapped[1].channel)
    }

    @Test
    fun `swapping a tile with itself is a no-op`() {
        val tiles = grid(a, b)
        assertEquals(tiles, swapTiles(tiles, 0, 0))
    }

    @Test
    fun `swapping an unknown slot is a no-op`() {
        val tiles = grid(a, b)
        assertEquals(tiles, swapTiles(tiles, 0, 9))
    }

    // ---- remove (spec 2.7) ----

    @Test
    fun `remove clears only the addressed slot`() {
        val tiles = grid(a, b, c)
        val removed = removeTile(tiles, 1)
        assertNull(removed[1].channel)
        assertEquals(a, removed[0].channel)
        assertEquals(c, removed[2].channel)
    }

    // ---- pick / assign (spec 2.7) ----

    @Test
    fun `assign puts a channel into the addressed slot only`() {
        val assigned = assignChannel(grid(null, b), 0, a)
        assertEquals(a, assigned[0].channel)
        assertEquals(b, assigned[1].channel)
    }

    // ---- audio source (spec 2.7) ----

    @Test
    fun `audio falls back to the first non-empty slot when none is requested`() {
        assertEquals(1, effectiveAudioSlot(grid(null, a, b), requested = null))
    }

    @Test
    fun `the requested audio slot is honoured when it has a channel`() {
        assertEquals(2, effectiveAudioSlot(grid(a, b, c), requested = 2))
    }

    @Test
    fun `moving audio updates the single source`() {
        val tiles = grid(a, b, c)
        assertEquals(0, effectiveAudioSlot(tiles, requested = 0))
        assertEquals(1, effectiveAudioSlot(tiles, requested = 1))
    }

    @Test
    fun `an empty requested slot falls back to a filled one`() {
        assertEquals(0, effectiveAudioSlot(grid(a, null), requested = 1))
    }

    @Test
    fun `removing the audio tile falls back to the next non-empty slot`() {
        val tiles = grid(a, b, c)
        val removed = removeTile(tiles, 0)
        assertEquals(1, effectiveAudioSlot(removed, requested = 0))
    }

    @Test
    fun `an empty grid has no audio source`() {
        assertNull(effectiveAudioSlot(grid(null, null), requested = 0))
    }

    @Test
    fun `audio prefers a playable tile over an over-budget one`() {
        val tiles = grid(a, b, c)
        val playable = withinTunerBudget(tiles, 2)
        // Slot 2 is requested but over budget; audio moves to a playable tile.
        assertEquals(0, effectiveAudioSlot(tiles, requested = 2, playable = playable))
    }

    // ---- status derivation (spec 2.7) ----

    @Test
    fun `status is empty without a channel`() {
        assertEquals(TileStatus.Empty, tileStatus(MultiviewTile(0), emptySet(), null))
    }

    @Test
    fun `status is tuner-busy when over budget or on a live 503`() {
        val tile = MultiviewTile(0, a)
        assertEquals(TileStatus.TunerBusy, tileStatus(tile, overBudget = setOf(0), error = null))
        assertEquals(
            TileStatus.TunerBusy,
            tileStatus(tile, overBudget = emptySet(), error = PlaybackError.AllTunersBusy),
        )
    }

    @Test
    fun `a non-503 error is a per-tile failure`() {
        assertEquals(
            TileStatus.Failed(PlaybackError.Unreachable),
            tileStatus(MultiviewTile(0, a), emptySet(), PlaybackError.Unreachable),
        )
    }

    @Test
    fun `a playable tile with no error is live`() {
        assertEquals(TileStatus.Live, tileStatus(MultiviewTile(0, a), emptySet(), null))
    }
}
