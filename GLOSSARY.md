# STB-Proxy

STB-Proxy turns IPTV portals (set-top-box accounts) into a single, Plex/Jellyfin-compatible channel lineup. This glossary fixes the vocabulary the code, docs and any client share.

## Language

**Portal**:
A single IPTV provider connection STB-Proxy logs into, identified by a URL and one or more MACs; the source of channels.
_Avoid_: feed, server, source, provider

**Lineup**:
The set of channels STB-Proxy exposes to external players. For a request authenticating as an **Account** it is that account's view (public channels plus its assigned, switched-on blocks); for a request with no account it is every available, non-dead channel from all enabled portals, minus channels only in hidden blocks — unless the operator has configured **Default blocks**, which scope such unauthenticated requests the same way an Account's blocks do.
_Avoid_: feed, channel list; the M3U served at `/playlist` is one rendering of the lineup, not the lineup itself

**Public channel**:
A channel enabled individually — visible to every Account and to no-account requests alike, regardless of blocks.
_Avoid_: free channel, common channel

**Operator**:
The person who runs STB-Proxy, authenticating to the Operator UI and `/api/*` with the single configured `username`/`password`. Distinct from an **Account**, which is viewer-only.
_Avoid_: admin, user, owner

**Operator UI**:
The web interface STB-Proxy serves to the **Operator**, rendered by Flask from `templates/` and `static/` at the server. Distinct from the viewer-facing clients: the **Companion app** (`android/`) and the **Web Viewer** (`web/`).
_Avoid_: web UI, admin panel, frontend; **Dashboard** is one page within it, not a synonym

**Account**:
A viewer login (username/password) usable as HTTP Basic on the feed endpoints, mapped to a set of **Blocks** (including STB-Proxy-only ones). The Lineup served to an account is its public channels plus the channels of its assigned, switched-on blocks. Separately from its blocks, the **Operator** switches **On Demand** on or off per account (off by default), and whether it sees **Adult On Demand**.
_Avoid_: user, login, profile, tenant

**Block**:
A named, switchable group of channels. A channel is available when it is enabled on its own or sits in any block that is on, and is not dead. A Block includes/excludes in the M3U, XMLTV and HDHomeRun feeds; it is also the grouping `/api/lineup` uses to arrange a channel list for the app. A Block marked **STB-Proxy only** (hidden) is kept out of anonymous and operator requests, the public API, Plex and Jellyfin — but it can still be assigned to an **Account**, which then sees it.
_Avoid_: group, category; a channel may sit in several blocks, and a block is not the same as a **Genre**

**Channel**:
One streamable entry offered by a portal, addressed as a (portal, channelId) pair.
_Avoid_: station, stream (the live connection to a channel, not the channel itself)

**Genre**:
The category a portal assigns a channel, carried in feeds as the M3U `group-title` attribute.
_Avoid_: block, category, group

**Guide**:
The schedule of **Programmes** for the channels in a **Lineup**, assembled from the portals' EPG and served to every client (the operator's `/guide` page, the apps' Guide screen). A viewer's Guide is scoped to their **Lineup** exactly as the channels are; programme rows join to channels by `epgId`.
_Avoid_: EPG (that's the feed/protocol, not the schedule), listings, TV guide

**Programme**:
One entry in the **Guide**: a title, a start and a stop time, and an optional description, for exactly one **Channel**. The apps' "now/next" teaser is the current **Programme** and the following one.
_Avoid_: show, event, entry

**Tuner**:
One concurrent distinct-channel stream STB-Proxy can serve; all viewers of the same channel share a single tuner.
_Avoid_: connection, slot, stream

**Multiview**:
Watching several channels at once in a grid of tiles.
_Avoid_: mosaic, multi-screen, grid

**Tile**:
One cell of a Multiview grid, playing a single channel.

**On Demand**:
A portal's catalogue of **Movies** and **Series** a viewer can play at any time, as opposed to the live **Lineup**. STB-Proxy merges every enabled portal's catalogue into one, and each item names its portal.
_Avoid_: VOD, Video Club, library, catch-up (catch-up is past **Programmes** on a live **Channel**, not On Demand)

**On Demand category**:
The grouping a portal assigns to On Demand items (e.g. "Action", "Kids"). One item can sit in several categories. Categories with the same name on different portals appear to viewers as one, and are hidden or shown as one. The **Operator** can hide a category from every viewer; an item in any hidden category is hidden everywhere, even if it also sits in a visible one.
_Avoid_: genre (that's a **Channel**'s category), block

**Adult On Demand**:
On Demand categories and items the portal flags as adult. Hidden from an **Account** unless the Operator allows it for that account.
_Avoid_: censored, locked, XXX

**Movie**:
One playable On Demand item with no episodes.
_Avoid_: film, title, asset

**Series**:
An On Demand item made of **Seasons**, each holding **Episodes**; only Episodes are playable.
_Avoid_: show, programme

**Season**:
A numbered set of **Episodes** within a **Series**.

**Episode**:
One playable part of a **Season**.
_Avoid_: programme (that's a **Guide** entry)

**On Demand session**:
One viewer playing one **Movie** or **Episode**. It is never shared. While it plays it takes one of its portal's playback slots, so it competes with live viewing on that portal, but it is not a **Tuner**. It ends when the viewer stops, when it sits idle, when the operator stops it, when the portal hands the slot to someone else, or when the portal stops sending it.
_Avoid_: stream, VOD session

**Resume point**:
Where an **Account** left off in a **Movie** or **Episode** it has not finished. It is kept by STB-Proxy, so it follows the viewer across devices.
_Avoid_: progress, bookmark, position

**Watched**:
A **Movie** or **Episode** an **Account** has played to 90% or to the end, or marked watched by hand. It stays watched when played again.
_Avoid_: seen, finished, completed

**Up next**:
The **Episode** a **Series** resumes at for an **Account**: the one it last played, if unfinished, or else the one after it.
_Avoid_: next episode, autoplay

**Continue watching**:
An **Account**'s unfinished **Movies** and **Series**, most recently played first.
_Avoid_: history, recently watched, in progress
