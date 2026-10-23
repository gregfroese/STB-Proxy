package cc.selfhosters.stbproxy.data.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.jsonPrimitive

/*
 * The viewer On Demand API (`/api/ondemand/...`, ADR 0005/0006). Ids are opaque: the
 * server may send a portal's ids as strings or numbers, and they are kept as text.
 */

/** An id the server may send as a string or a number, kept as text. */
object IdSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("OnDemandId", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String =
        if (decoder is JsonDecoder) decoder.decodeJsonElement().jsonPrimitive.content
        else decoder.decodeString()

    override fun serialize(encoder: Encoder, value: String) = encoder.encodeString(value)
}

typealias Id = @Serializable(with = IdSerializer::class) String

/** `GET /api/ondemand/categories`. */
@Serializable
data class OnDemandCategories(
    val categories: List<OnDemandCategory> = emptyList(),
    val portals: List<OnDemandPortalStatus> = emptyList(),
)

/** A merged On Demand category; [id] is opaque and goes back as `category=`. */
@Serializable
data class OnDemandCategory(
    val id: Id,
    val name: String,
    val count: Int = 0,
)

/** One enabled portal's index status: ready, indexing, stale, partial or failed. */
@Serializable
data class OnDemandPortalStatus(
    val portal: Id,
    val name: String = "",
    val status: String = "ready",
    val progress: Int? = null,
    /** Epoch seconds. */
    val lastRefresh: Long? = null,
)

/** `GET /api/ondemand/items`: one page, with the exact [total]. */
@Serializable
data class OnDemandPage(
    val items: List<OnDemandItem> = emptyList(),
    val total: Int = 0,
)

/** A Movie or Series as a list row (also Continue watching's rows). */
@Serializable
data class OnDemandItem(
    val portal: Id,
    val id: Id,
    val kind: String = MOVIE,
    val name: String = "",
    val portalName: String = "",
    val year: Int? = null,
    val rating: Double? = null,
    val added: String? = null,
    /** Server-relative `/api/ondemand/poster/...`, or null for none. */
    val poster: String? = null,
    /** A Movie's viewer state (08); null for none and for a Series. */
    val progress: OnDemandProgress? = null,
    /** A Series' Up next (08); null for none and for a Movie. */
    val upNext: OnDemandUpNext? = null,
) {
    val isSeries: Boolean get() = kind == SERIES

    companion object {
        const val MOVIE = "movie"
        const val SERIES = "series"
    }
}

@Serializable
data class OnDemandProgress(
    val positionSec: Int? = null,
    val durationSec: Int? = null,
    val watched: Boolean = false,
    val updatedAt: Long? = null,
)

@Serializable
data class OnDemandUpNext(
    val seasonId: Id,
    val seasonNumber: Int? = null,
    val episodeId: Id,
    val episodeNumber: Int? = null,
    val name: String? = null,
    val positionSec: Int? = null,
    val durationSec: Int? = null,
)

/** `GET /api/ondemand/item/<portal>/<id>`: the list item plus the portal's facts. */
@Serializable
data class OnDemandDetail(
    val portal: Id,
    val id: Id,
    val kind: String = OnDemandItem.MOVIE,
    val name: String = "",
    val portalName: String = "",
    val year: Int? = null,
    val rating: Double? = null,
    val added: String? = null,
    val poster: String? = null,
    val originalName: String? = null,
    val description: String? = null,
    val genres: String? = null,
    val director: String? = null,
    val actors: String? = null,
    val country: String? = null,
    val durationMin: Int? = null,
    val ageRating: String? = null,
    val categories: List<String> = emptyList(),
    val progress: OnDemandProgress? = null,
    val upNext: OnDemandUpNext? = null,
    /** A Series' Seasons, ascending. */
    val seasons: List<OnDemandSeason> = emptyList(),
) {
    val isSeries: Boolean get() = kind == OnDemandItem.SERIES
}

@Serializable
data class OnDemandSeason(
    val id: Id,
    val number: Int? = null,
    val name: String? = null,
    val episodeCount: Int? = null,
)

/** One of `GET /api/ondemand/series/<p>/<s>/season/<id>`'s Episodes, ascending. */
@Serializable
data class OnDemandEpisode(
    val id: Id,
    val seasonId: Id,
    val number: Int? = null,
    val name: String? = null,
    val progress: OnDemandProgress? = null,
)

/** `POST /api/ondemand/play`: an On Demand session. */
@Serializable
data class OnDemandPlayback(
    val session: String,
    val type: String = "hls",
    /** Server-relative master playlist URL. */
    val url: String,
    val durationSec: Int? = null,
    /** [url] joined onto the server's base URL by the client. */
    @Transient val absoluteUrl: String = url,
)

@Serializable
internal data class OnDemandItemList(val items: List<OnDemandItem> = emptyList())

/** What `/play` and `/progress` name: a Movie, or one Episode of a Series. */
sealed interface OnDemandKey {
    val portal: String

    data class Movie(override val portal: String, val id: String) : OnDemandKey

    data class Episode(
        override val portal: String,
        val seriesId: String,
        val seasonId: String,
        val episodeId: String,
    ) : OnDemandKey
}
