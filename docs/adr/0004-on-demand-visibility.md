# On Demand visibility is a per-Account switch beside Blocks

**On Demand** is a second visibility axis on an **Account**, independent of its **Blocks**. Each Account record gains two operator-set booleans, `"on demand"` and `"adult on demand"`, both default off. `config.json` gains a top-level, operator-wide `"hidden on demand categories"` list. Every On Demand route resolves the request through one helper. Anything other than an enabled Account with `"on demand"` on gets **404**: a switched-off Account, an anonymous request, or the operator login, which Plex and Jellyfin use. The `/api/lineup` envelope carries `"onDemand": true|false` so the clients can show or hide their nav entry without an extra call.

Hidden categories are keyed by the **merged, normalised name** (case-folded, whitespace collapsed) and not by `(portal, category id)`, even though ids are the stable key on the portal. Viewers see same-named categories from different portals as one ([ADR 0003](0003-on-demand-local-index.md)), so hiding by name hides exactly what viewers see. A per-portal key could leave a "KIDS" half-hidden. A name that no longer matches any portal category is flagged as stale on the Operator UI's On Demand page, so a portal-side rename doesn't go unnoticed.

Hiding is **strict**. An item in any hidden category, in any of its three category slots, disappears from every listing, from "All", from counts, from search and from play, even if it also sits in a visible category. Adult content uses the same rule. While an Account's `"adult on demand"` is off, categories the portal flags `censored` and items flagged `censored`/`lock` are removed for that Account. The operator-wide hidden list applies whether `"adult on demand"` is on or off.

## Considered options

- *Key hidden categories by `(portal uuid, category id)`* (research 01's recommendation): rejected once categories merged by name. It survives renames but splits one viewer-visible category into per-portal switches.
- *Lenient hiding (hide an item only under the hidden category)*: rejected. "All" and search would still surface the content the operator meant to hide.
- *Auto-add adult categories to the hidden list when first seen*: rejected. Un-hiding one would need a second "seen" list to stop the next pull re-hiding it.
- *An operator-wide adult switch*: rejected in favour of per-Account, so one household member can be allowed adult content without everyone being allowed it. There is no viewer PIN: the operator decides, not the viewer.
- *403, or an empty catalogue, for a switched-off Account*: rejected. A 403 advertises a feature the viewer may not use, and an empty catalogue looks broken. 404 also covers the operator login, keeping On Demand out of Plex and Jellyfin.
- *Model On Demand as a special Block*: rejected. Blocks group live Channels and feed M3U/XMLTV/HDHomeRun. On Demand has none of those, and Default blocks for anonymous requests must never reach it.
