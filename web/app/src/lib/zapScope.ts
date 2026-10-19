// The player's zap scope: which Channels up/down steps through (ticket 07). A `group`
// keeps the shipped behaviour (`block=` plus the device GroupMode); a `list` carries an
// ordered set of Channel keys walked directly. Small lists ride in the URL; longer ones
// are held in a store (sessionStorage, so a reload keeps them) behind a short token.

import type { Channel } from "./types";

export interface ZapScopeGroup {
  kind: "group";
  block: string;
  label: string;
}

export interface ZapScopeList {
  kind: "list";
  keys: string[];
  label: string;
}

export type ZapScope = ZapScopeGroup | ZapScopeList;

/** A list this short is inlined in the URL; longer ones go through the store. */
export const INLINE_KEY_LIMIT = 50;

const STORAGE_KEY = "stbproxy.zapScopes";

const scopes = new Map<string, ZapScope>();
let counter = 0;

function storage(): Storage | null {
  try {
    return typeof sessionStorage !== "undefined" ? sessionStorage : null;
  } catch {
    return null;
  }
}

function load(): void {
  const store = storage();
  if (!store) return;
  try {
    const raw = store.getItem(STORAGE_KEY);
    if (!raw) return;
    for (const [token, scope] of Object.entries(JSON.parse(raw) as Record<string, ZapScope>)) {
      scopes.set(token, scope);
    }
    counter = scopes.size;
  } catch {
    /* malformed storage: start empty */
  }
}

function persist(): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(scopes)));
  } catch {
    /* storage full / disabled: keep the in-memory copy */
  }
}

load();

/** A Channel's identity — the GLOSSARY's `(portal, channelId)` pair, as one key. */
export function scopeKey(channel: { portal: string; channelId: string }): string {
  return `${channel.portal}:${channel.channelId}`;
}

/** The distinct Channel keys of [channels], in order. */
export function scopeKeys(channels: Channel[]): string[] {
  const seen = new Set<string>();
  const keys: string[] = [];
  for (const channel of channels) {
    const key = scopeKey(channel);
    if (!seen.has(key)) {
      seen.add(key);
      keys.push(key);
    }
  }
  return keys;
}

/** Park [scope] in the store and return the token the URL carries. */
export function putScope(scope: ZapScope): string {
  counter += 1;
  const token = `s${counter}`;
  scopes.set(token, scope);
  persist();
  return token;
}

export function getScope(token: string | null): ZapScope | null {
  return token ? (scopes.get(token) ?? null) : null;
}

/** Append the small descriptor for [scope] to a query string. */
export function appendScope(query: URLSearchParams, scope: ZapScope): void {
  if (scope.label) query.set("label", scope.label);
  if (scope.kind === "group") {
    query.set("scope", "group");
    query.set("block", scope.block);
    return;
  }
  query.set("scope", "list");
  if (scope.keys.length <= INLINE_KEY_LIMIT) {
    query.set("keys", scope.keys.join(","));
  } else {
    query.set("token", putScope(scope));
  }
}

/** The scope a player route carries; absent scope is a `group` (the shipped shape). */
export function parseScope(query: URLSearchParams): ZapScope {
  const label = query.get("label") ?? "";
  if (query.get("scope") === "list") {
    const inline = query.get("keys");
    if (inline) return { kind: "list", keys: inline.split(",").filter(Boolean), label };
    const stored = getScope(query.get("token"));
    if (stored && stored.kind === "list") return { ...stored, label: label || stored.label };
    return { kind: "list", keys: [], label };
  }
  const block = query.get("block") ?? "";
  return { kind: "group", block, label: label || block };
}

/** The `/watch` URL for [channel] launched under [scope]. */
export function watchUrl(channel: { portal: string; channelId: string }, scope: ZapScope): string {
  const query = new URLSearchParams();
  query.set("portal", channel.portal);
  query.set("id", channel.channelId);
  appendScope(query, scope);
  return `/watch?${query.toString()}`;
}
