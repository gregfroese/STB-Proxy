import { writable } from "svelte/store";
import { read, setCsrfToken, setUnauthorizedHandler } from "./api";
import { resetEpg } from "./epg";
import { clearLineup } from "./lineup";
import { resetMultiview } from "./multiview";
import { navigate } from "./router";
import type { SessionInfo } from "./types";

export const session = writable<SessionInfo | null>(null);
export const sessionChecked = writable(false);
/** A one-shot message to show on the login screen (expiry / revoked credentials). */
export const sessionMessage = writable<string | null>(null);

export function accountLabel(info: SessionInfo | null): string {
  if (!info) return "";
  return info.operator ? "Full lineup (operator / security off)" : (info.account ?? "");
}

export function installUnauthorizedHandler(): void {
  setUnauthorizedHandler((code) => {
    clearSession();
    clearLineup();
    resetEpg();
    resetMultiview();
    sessionMessage.set(
      code === "session_invalid"
        ? "Your credentials are no longer valid."
        : "Your session expired. Please sign in again.",
    );
    navigate("/login", true);
  });
}

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
