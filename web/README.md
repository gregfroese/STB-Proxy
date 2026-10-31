# STB-Proxy web viewer

A browser client for STB-Proxy: log in as an **Account**, browse channels grouped by **Block**, play
one channel with now/next EPG, or watch several at once in a **Multiview** — for desktop and phone
equally.

It is a **BFF + SPA** pair, hosted on its own public LXC behind Caddy at
`https://watch.home.gregfroese.com`:

- **`bff/`** — a small **FastAPI** server. It holds Account credentials server-side, talks to the
  int-only STB-Proxy (`http://192.168.5.71:8001`), proxies the lineup / guide / live TS, and serves
  the built SPA. The browser only ever talks to the BFF.
- **`app/`** — a **Svelte 5 + Vite + TypeScript** static SPA. It never learns the proxy's address.

The full design is in [`../.scratch/web-client/spec.md`](../.scratch/web-client/spec.md).

## Layout

```
web/
  bff/            FastAPI BFF (config, sessions, security, epg, main)
  app/            Svelte SPA (src/lib logic + routes)
  tests/          pytest suite for the BFF
  requirements.txt
  requirements-dev.txt
  .env.example    every config key
  deploy.sh       pull + build + install + restart
  Dockerfile      the BFF and the built SPA as one image (docker build web/)
  systemd/        the stb-proxy-web unit
```

## Local development

Two processes: the BFF and the Vite dev server. Vite proxies `/api` and `/stream` to the BFF, and
the BFF points at the LAN proxy.

```bash
# 1. Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

# 2. Run the BFF (dev: local session db, no __Host- cookie over http, accept the Vite origin)
SESSION_DB=./sessions.db COOKIE_SECURE=false \
  PUBLIC_ORIGIN=http://localhost:5173 \
  PROXY_URL=http://192.168.5.71:8001 \
  .venv/bin/uvicorn bff.main:app --reload

# 3. In another shell, the SPA
cd app
npm install
npm run dev        # http://localhost:5173, proxies /api and /stream to :8000
```

`COOKIE_SECURE=false` drops the `__Host-` cookie prefix so login works over plain http; never do
this in production.

## Tests

```bash
# SPA logic (Vitest, mirrors the Android Kotlin tests)
cd app && npm test

# SPA types/lint/format
cd app && npm run check && npm run lint && npx prettier --check .

# BFF (pytest)
cd web && .venv/bin/python -m pytest tests
```

## Configuration

All config is environment variables, documented in [`.env.example`](.env.example). In production
they live in a root-owned `/etc/stb-proxy-web/env` (`chmod 600`) loaded by systemd's
`EnvironmentFile`. Secrets (`SESSION_SECRET`, `FERNET_KEY`) are never committed; generate them with
the commands in the example file. Rotate the Fernet key via `FERNET_KEYS_FALLBACK` (newest key in
`FERNET_KEY`, older keys in the fallback list).

Key settings: `PROXY_URL`, `PUBLIC_ORIGIN`, `LINEUP_TTL=30`, `EPG_TTL=300`, `IDLE=3600`,
`ABS=43200`, `REVALIDATE=900`, `SESSION_DB=/var/lib/stb-proxy-web/sessions.db`.

### Playback and the HLS fallback

Playback is `mpegts.js` over the proxied TS (client-side TS→fMP4→MSE). Some streams — notably
B-frame-heavy 1080p60 — produce fMP4 samples the browser's hardware decoder rejects, which stutters.
When the player sees a high dropped-frame rate it transparently switches to the **HLS fallback**:
the BFF runs `ffmpeg -c copy` to remux the channel to HLS (`/hls/<portal>/<channelId>/index.m3u8`)
and `hls.js` plays it. This needs **ffmpeg on the host** (installed by `deploy.sh`); tune with
`HLS_ENABLED`, `HLS_DIR`, `HLS_TTL` (idle seconds before an idle remux is reaped), `FFMPEG_BIN`.

## Production (LXC 119 `stb-proxy-web`, 192.168.5.72)

```bash
# one-time
sudo useradd --system --home /opt/stb-proxy-web stbproxy
sudo mkdir -p /var/lib/stb-proxy-web /etc/stb-proxy-web
sudo install -o root -g root -m 600 /dev/null /etc/stb-proxy-web/env   # fill from .env.example
python3 -m venv /opt/stb-proxy-web/venv
/opt/stb-proxy-web/venv/bin/pip install -r web/requirements.txt
sudo cp web/systemd/stb-proxy-web.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now stb-proxy-web

# every deploy
./web/deploy.sh
```

The unit runs `uvicorn` on `:8000` (matching the Caddy upstream), `Restart=always`, and serves the
built SPA from `app/dist`. Caddy terminates TLS/HSTS and proxies `watch.home.gregfroese.com` →
`192.168.5.72:8000`; the BFF sets `X-Accel-Buffering: no` on `/stream`, so Caddy's default
streaming is enough (add `flush_interval -1` only if testing shows buffering).

## Security

- Server-side sessions (opaque token; only its sha256 stored) behind an
  `HttpOnly; Secure; SameSite=Lax` `__Host-session` cookie; idle 60 min + absolute 12 h.
- The Account's `user:pass` is Fernet-encrypted at rest and re-attached as HTTP Basic upstream; the
  browser never sees it, the proxy address, or the account list.
- Login is rate-limited per-IP at Caddy and per-username (exponential backoff) in the BFF; sessions
  are re-validated against `GET /api/lineup` every ~15 min and dropped if the account is revoked.
- CSP / `nosniff` / `Referrer-Policy` / `frame-ancestors 'none'` from the BFF; HSTS from Caddy.

## Versioning

The web client shares STB-Proxy's version (`../version.py`). `web/` changes bump the same version and
add a `CHANGELOG.md` entry; the SPA shows the repo version, injected at build time.
