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
A viewer login (username/password) usable as HTTP Basic on the feed endpoints, mapped to a set of **Blocks** (including STB-Proxy-only ones). The Lineup served to an account is its public channels plus the channels of its assigned, switched-on blocks.
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
