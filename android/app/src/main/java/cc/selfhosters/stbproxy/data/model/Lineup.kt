package cc.selfhosters.stbproxy.data.model

import kotlinx.serialization.Serializable

/**
 * Response of `GET /api/lineup` — see spec 1.4.
 *
 * Flat channel list plus the envelope fields. The app derives its Block sections
 * from [blocks] and each channel's own [Channel.blocks].
 */
@Serializable
data class Lineup(
    val account: String? = null,
    val blocks: List<String> = emptyList(),
    val channels: List<Channel> = emptyList(),
    val failedPortals: List<String> = emptyList(),
    /** True when this Account may use On Demand (ADR 0004); gates the nav entry. */
    val onDemand: Boolean = false,
)

@Serializable
data class Channel(
    val portal: String,
    val channelId: String,
    val name: String,
    val url: String,
    val portalName: String = "",
    val number: String? = null,
    val logo: String? = null,
    val genre: String? = null,
    val epgId: String? = null,
    val blocks: List<String> = emptyList(),
    val favourite: Boolean = false,
    val blockFavourites: List<String> = emptyList(),
)
