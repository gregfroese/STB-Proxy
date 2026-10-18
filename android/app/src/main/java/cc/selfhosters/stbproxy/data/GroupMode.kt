package cc.selfhosters.stbproxy.data

/**
 * Which taxonomy the viewer's picker groups channels by. A per-device preference
 * (spec follow-up): Blocks (default), or the portal's Genres when the account has
 * no visible Blocks.
 */
enum class GroupMode(val label: String) {
    BLOCKS("Blocks"),
    GENRES("Genres"),
}
