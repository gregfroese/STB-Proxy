package cc.selfhosters.stbproxy.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NavDestinationsTest {

    @Test
    fun `On Demand sits between Guide and Multiview when the lineup offers it`() {
        assertEquals(
            listOf(
                Destination.CHANNELS,
                Destination.GUIDE,
                Destination.ON_DEMAND,
                Destination.MULTIVIEW,
                Destination.SETTINGS,
            ),
            visibleDestinations(onDemand = true),
        )
    }

    @Test
    fun `On Demand is hidden otherwise`() {
        assertFalse(Destination.ON_DEMAND in visibleDestinations(onDemand = false))
        assertEquals(4, visibleDestinations(onDemand = false).size)
    }

    @Test
    fun `On Demand's own screens are left when it is switched off`() {
        assertTrue(leavesOnDemand(route = Routes.ON_DEMAND, onDemand = false))
        assertTrue(leavesOnDemand(route = Routes.ON_DEMAND_CATEGORY_ROUTE, onDemand = false))
        assertTrue(leavesOnDemand(route = Routes.ON_DEMAND_ITEM_ROUTE, onDemand = false))
        assertFalse(leavesOnDemand(route = Routes.ON_DEMAND, onDemand = true))
        assertFalse(leavesOnDemand(route = Routes.GUIDE, onDemand = false))
        assertFalse(leavesOnDemand(route = null, onDemand = false))
    }

    @Test
    fun `a category screen is not a top-level destination, so the bottom bar hides`() {
        assertEquals(Destination.ON_DEMAND, Destination.of(Routes.ON_DEMAND))
        assertEquals(null, Destination.of(Routes.ON_DEMAND_CATEGORY_ROUTE))
    }
}
