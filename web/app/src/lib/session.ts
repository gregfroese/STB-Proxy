import { writable } from "svelte/store";
import { read, setCsrfToken } from "./api";
import type { SessionInfo } from "./types";

export const session = writable<SessionInfo | null>(null);
export const sessionChecked = writable(false);

export async function loadSession(): Promise<void> {
  try {
    const info = await read<SessionInfo>("/api/session");
    setCsrfToken(info.csrf);
    session.set(info);
  } catch {
    setCsrfToken(null);
    session.set(null);
  } finally {
    sessionChecked.set(true);
  }
}

export function setSession(info: SessionInfo): void {
  setCsrfToken(info.csrf);
  session.set(info);
}

export function clearSession(): void {
  setCsrfToken(null);
  session.set(null);
}
