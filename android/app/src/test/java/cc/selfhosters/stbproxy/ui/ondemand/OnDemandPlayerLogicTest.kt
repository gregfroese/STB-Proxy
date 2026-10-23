package cc.selfhosters.stbproxy.ui.ondemand

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OnDemandPlayerLogicTest {

    private var now = 0L
    private val clock = { now }

    // ---- seek acceleration (TV ← →) ----

    @Test
    fun `a single press seeks 10 s either way`() {
        val keys = SeekKeys(clock)
        assertEquals(10, keys.press(+1, repeat = false))
        now = 5_000
        assertEquals(-10, keys.press(-1, repeat = false))
    }

    @Test
    fun `holding speeds up to 30 s after 1 s and 60 s after 3 s`() {
        val keys = SeekKeys(clock)
        assertEquals(10, keys.press(+1, repeat = false))
        now = 800
        assertEquals(10, keys.press(+1, repeat = true))
        now = 1_000
        assertEquals(30, keys.press(+1, repeat = true))
        now = 2_800
        assertEquals(30, keys.press(+1, repeat = true))
        now = 3_000
        assertEquals(60, keys.press(+1, repeat = true))
        now = 9_000
        assertEquals(60, keys.press(+1, repeat = true))
    }

    @Test
    fun `a held key steps about 5 times a second, dropping faster repeats`() {
        val keys = SeekKeys(clock)
        keys.press(-1, repeat = false)
        now = 50
        assertNull(keys.press(-1, repeat = true))
        now = 179
        assertNull(keys.press(-1, repeat = true))
        now = 180
        assertEquals(-10, keys.press(-1, repeat = true))
        now = 300
        assertNull(keys.press(-1, repeat = true))
    }

    @Test
    fun `a fresh press starts the speed-up again`() {
        val keys = SeekKeys(clock)
        keys.press(+1, repeat = false)
        now = 4_000
        assertEquals(60, keys.press(+1, repeat = true))
        now = 4_100
        assertEquals(10, keys.press(+1, repeat = false))
    }

    // ---- phone double-tap ----

    @Test
    fun `double-tapping the left or right side seeks 10 s, the middle does nothing`() {
        assertEquals(-10, doubleTapSeek(0.1f))
        assertEquals(-10, doubleTapSeek(0.39f))
        assertNull(doubleTapSeek(0.5f))
        assertEquals(10, doubleTapSeek(0.61f))
        assertEquals(10, doubleTapSeek(0.95f))
    }

    // ---- end card, autoplay and "Still watching?" ----

    @Test
    fun `an Episode with a next one ends on the Next card, which plays it after 15 s`() {
        val end = EndOfPlayback(clock)
        now = 1_000
        end.ended(hasNext = true)
        assertEquals(EndCard.Next, end.card)
        assertEquals(15, end.secondsLeft())
        now = 1_000 + 14_100
        assertNull(end.tick())
        assertEquals(1, end.secondsLeft())
        now = 1_000 + 15_000
        assertEquals(EndAction.PlayNext(auto = true), end.tick())
        assertNull("the countdown fires once", end.tick())
    }

    @Test
    fun `a Movie or the last Episode ends on the Watched card, which goes back to details after 15 s`() {
        val end = EndOfPlayback(clock)
        end.ended(hasNext = false)
        assertEquals(EndCard.Watched, end.card)
        now = 14_999
        assertNull(end.tick())
        now = 15_000
        assertEquals(EndAction.BackToDetails, end.tick())
    }

    @Test
    fun `after 3 autoplays in a row with no input, the next end asks Still watching and waits`() {
        val end = EndOfPlayback(clock)
        repeat(3) {
            end.ended(hasNext = true)
            assertEquals(EndCard.Next, end.card)
            now += 15_000
            assertEquals(EndAction.PlayNext(auto = true), end.tick())
            end.handedOver(auto = true)
            assertNull(end.card)
        }
        end.ended(hasNext = true)
        assertEquals(EndCard.StillWatching, end.card)
        now += 60_000
        assertNull("Still watching has no countdown", end.tick())
    }

    @Test
    fun `any input resets the autoplay count`() {
        val end = EndOfPlayback(clock)
        repeat(2) {
            end.ended(hasNext = true)
            now += 15_000
            end.tick()
            end.handedOver(auto = true)
        }
        end.input()
        end.ended(hasNext = true)
        now += 15_000
        end.tick()
        end.handedOver(auto = true)
        end.ended(hasNext = true)
        assertEquals("only 1 autoplay since the input", EndCard.Next, end.card)
    }

    @Test
    fun `a manual hand-over (Next Episode, Play now, Continue) resets the count`() {
        val end = EndOfPlayback(clock)
        repeat(3) {
            end.ended(hasNext = true)
            now += 15_000
            end.tick()
            end.handedOver(auto = true)
        }
        end.ended(hasNext = true)
        assertEquals(EndCard.StillWatching, end.card)
        end.handedOver(auto = false)
        assertNull(end.card)
        end.ended(hasNext = true)
        assertEquals(EndCard.Next, end.card)
    }

    @Test
    fun `the last Episode gets the Watched card even after 3 autoplays`() {
        val end = EndOfPlayback(clock)
        repeat(3) {
            end.ended(hasNext = true)
            now += 15_000
            end.tick()
            end.handedOver(auto = true)
        }
        end.ended(hasNext = false)
        assertEquals(EndCard.Watched, end.card)
    }

    @Test
    fun `dismissing the card (Play again, a seek back) stops its countdown`() {
        val end = EndOfPlayback(clock)
        end.ended(hasNext = true)
        end.dismiss()
        assertNull(end.card)
        now += 20_000
        assertNull(end.tick())
        assertNull(end.secondsLeft())
    }

    // ---- progress report cadence ----

    @Test
    fun `a report falls due after every 30 s of playback`() {
        val schedule = ReportSchedule(clock)
        for (t in 0L..29_000L step 1_000) {
            now = t
            assertFalse("at $t", schedule.tick(playing = true))
        }
        now = 30_000
        assertTrue(schedule.tick(playing = true))
        schedule.reported()
        now = 31_000
        assertFalse(schedule.tick(playing = true))
        now = 60_000
        assertTrue(schedule.tick(playing = true))
    }

    @Test
    fun `paused or buffering time doesn't count towards the next report`() {
        val schedule = ReportSchedule(clock)
        schedule.tick(playing = true)
        now = 20_000
        schedule.tick(playing = true)
        now = 300_000
        assertFalse(schedule.tick(playing = false))
        now = 309_000
        assertFalse(schedule.tick(playing = true))
        now = 310_000
        assertTrue(schedule.tick(playing = true))
    }

    @Test
    fun `an event report (pause, hand-over) restarts the 30 s`() {
        val schedule = ReportSchedule(clock)
        schedule.tick(playing = true)
        now = 25_000
        schedule.tick(playing = true)
        schedule.reported()
        now = 50_000
        assertFalse(schedule.tick(playing = true))
        now = 55_000
        assertTrue(schedule.tick(playing = true))
    }

    // ---- a 410's reason ----

    @Test
    fun `a 410 session_ended body gives its reason`() {
        fun body(reason: String) = """{"error": "Session ended", "code": "session_ended", "reason": "$reason"}""".toByteArray()
        assertEquals(SessionEnd.IDLE, sessionEndOf(410, body("idle")))
        assertEquals(SessionEnd.EVICTED, sessionEndOf(410, body("evicted")))
        assertEquals(SessionEnd.FAILED, sessionEndOf(410, body("failed")))
        assertEquals(SessionEnd.STOPPED, sessionEndOf(410, body("stopped")))
    }

    @Test
    fun `a 410 without a readable reason still ends the session, other statuses don't`() {
        assertEquals(SessionEnd.UNKNOWN, sessionEndOf(410, null))
        assertEquals(SessionEnd.UNKNOWN, sessionEndOf(410, "<html>".toByteArray()))
        assertEquals(SessionEnd.UNKNOWN, sessionEndOf(410, """{"reason": "later"}""".toByteArray()))
        assertNull(sessionEndOf(404, """{"reason": "idle"}""".toByteArray()))
        assertNull(sessionEndOf(null, null))
    }
}
