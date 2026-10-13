// Thin fetch wrapper (spec 2.1): 2-retry reads (0.5s, 1.5s), no retry for
// streams or mutations. Errors normalise to ApiError with the BFF envelope.

import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const RETRY_DELAYS = [500, 1500];

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function headersFor(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  const method = init?.method ?? "GET";
  if (method !== "GET") {
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  return headers;
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }
  let body: Partial<ApiErrorBody> = {};
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(
    response.status,
    body.code ?? "error",
    body.error ?? `Request failed (${response.status}).`,
  );
}

/** A read: 2 retries on network failure or 5xx, then surface. */
export async function read<T>(path: string): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= RETRY_DELAYS.length; attempt += 1) {
    try {
      const response = await fetch(path, {
        headers: headersFor(),
        credentials: "same-origin",
      });
      if (response.status >= 500 && attempt < RETRY_DELAYS.length) {
        await sleep(RETRY_DELAYS[attempt]);
        continue;
      }
      return await parse<T>(response);
    } catch (error) {
      lastError = error;
      if (error instanceof ApiError || attempt >= RETRY_DELAYS.length) throw error;
      await sleep(RETRY_DELAYS[attempt]);
    }
  }
  throw lastError;
}

/** A mutation: no retry (never replay a state change). */
export async function mutate<T>(
  path: string,
  body?: unknown,
  method: "POST" | "PUT" | "DELETE" = "POST",
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: headersFor({ method }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  return parse<T>(response);
}

export async function login(username: string, password: string) {
  return mutate<import("./types").SessionInfo>("/api/login", { username, password });
}

export async function logout(): Promise<void> {
  await mutate<{ ok: boolean }>("/api/logout");
}
