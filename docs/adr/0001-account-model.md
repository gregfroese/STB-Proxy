# Accounts scope the lineup by block, over HTTP Basic

STB-Proxy originally had a single `username`/`password` (the operator login) and a single `api token`. To serve different channel subsets to different players we added **Accounts**: viewer logins, resolved from HTTP Basic on the feed endpoints, each mapped to a set of **Blocks**. A channel is visible to an account iff it is a **public channel** (enabled individually) or it sits in a Block assigned to that account *and* globally on — and it is not dead; hidden ("STB-Proxy only") Blocks are kept out of anonymous and operator requests and the public API (see the amendment below). The operator's global block switch is a master kill-switch that *intersects* assignment rather than being replaced by it.

We kept the existing single login as the operator/admin credential for the web UI and `/api/*`, so nothing existing breaks and no migration is needed; requests without an account keep serving the full lineup. Basic was chosen over per-account API tokens so Plex, Jellyfin and any M3U/HDHomeRun player get per-account scoping for free.

## Considered options

- *Deny-by-default (nothing public; an account sees only its blocks)* — rejected: it would hide every individually-enabled channel from all accounts and break the existing "enabled = everyone" behaviour.
- *Assignment replaces the global switch* — rejected: the operator loses a single master control and accidental exposure becomes easier.
- *Per-account API tokens* — rejected for now: no existing player can use a Bearer token, so it would only serve the custom app.

## Anonymous default blocks

Requests that resolve to neither the Operator nor an Account would otherwise serve the **full lineup** (backward compatible), which defeats scoping for players that do not forward Basic to the feed endpoints (Plex, Jellyfin). To close that gap we added an **optional, default-off** top-level `config.json` key `default blocks`: a list of Block names that scopes such anonymous requests.

The anonymous view takes the **same shape as an Account's** — public channels union the channels of the configured, globally-on Blocks, minus dead; hidden Blocks are never included. It is **not** a filter, so individually-enabled public channels stay visible. Because the setting is a plain block-set dropped into the same `plexLineup(portal, blocks)` seam, it needs no new filtering code.

The set is *config*, not a **synthetic Account**: an anonymous request presents no username, so there is nothing for Basic to resolve. Consistent with "security gates rejection, not scoping", the set applies whenever configured, even with `enable security` off. `/play` stays credentials-optional as before — the default set scopes **discovery**, not stream URLs; a guessable URL still plays, the same residual already accepted for Accounts.

### Considered options

- *A synthetic "anonymous" Account* — rejected: a fake username can never be presented over Basic, so it could only act as a hidden fallback case; a config key says that plainly.
- *A pure filter (hide everything outside the default set, including public channels)* — rejected: it would break the "enabled = everyone" rule and duplicate hidden-block semantics.

## Hidden blocks can be assigned to accounts

"Hidden" ("STB-Proxy only") is really about **public** exposure: a hidden Block is left out of anonymous and operator requests, the public `/api/blocks` listing, and Plex/Jellyfin. It is *not* a restriction on Accounts. We therefore let an Account be **assigned a hidden Block**; when that Block is globally on, the account sees its channels (on `/playlist`, `/xmltv`, `/lineup.json`, `/lineup.post` and `/api/lineup`) exactly as it would a shared Block.

The rule is applied by one helper, `viewerHidden()`: it returns no hidden Blocks when the request resolved to an Account, and the full hidden list otherwise. So operator and anonymous requests are unchanged (Plex and Jellyfin authenticate as the operator, so they still never see hidden Blocks), while an account's own hidden Blocks come through. The `default blocks` set for anonymous clients still excludes hidden Blocks, since it scopes public requests.

### Considered options

- *Keep hidden Blocks unassignable* — rejected: it forces a second "hidden but assignable" concept for the same need (show a Block only to specific viewers).
- *Let the operator also see hidden Blocks on the feeds* — rejected: the operator credentials are what Plex and Jellyfin use, so it would leak hidden Blocks to those players and defeat the feature.
