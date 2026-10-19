package cc.selfhosters.stbproxy.data.model

import kotlinx.serialization.Serializable

/**
 * The account-scoped Guide contract (ADR 0002). Times are epoch **seconds**, as
 * the server sends them — unlike `/xmltv`, which is ISO strings.
 */
@Serializable
data class GuideProgramme(
    val start: Long,
    val stop: Long,
    val title: String,
    val desc: String = "",
)

/** One programme in a search hit, joined to the Channel it airs on. */
@Serializable
data class GuideHit(
    val portal: String,
    val channelId: String,
    val channelName: String,
    val channelNumber: String? = null,
    val logo: String? = null,
    val epgId: String? = null,
    val start: Long,
    val stop: Long,
    val title: String,
    val desc: String = "",
)

/** Response of `GET /api/guide/search`. */
@Serializable
data class GuideSearchResult(
    val results: List<GuideHit> = emptyList(),
    val total: Int = 0,
    val loadedAt: Double? = null,
    val programmes: Int = 0,
    val failed: List<String> = emptyList(),
    val partial: List<String> = emptyList(),
    val account: String? = null,
)

/** Response of `GET /api/guide/channel`: one Channel's upcoming programmes. */
@Serializable
data class GuideChannelProgrammes(
    val portal: String = "",
    val channelId: String = "",
    val programmes: List<GuideProgramme> = emptyList(),
)
