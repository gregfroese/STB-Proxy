# The web viewer as one image: the SPA is built in a Node stage, and the BFF serves it.
# Build it from web/ (docker build web/). Base images are pinned, like the main Dockerfile's.
FROM node:22-alpine3.24 AS spa
WORKDIR /app
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ ./
RUN npm run build

FROM python:3.13-alpine3.24

# ffmpeg for the HLS fallback; tini so the stop signal reaches uvicorn and finished ffmpeg
# processes are cleaned up.
RUN apk add --no-cache ffmpeg tini

WORKDIR /web
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bff/ bff/
# The BFF's default STATIC_DIR is ../app/dist from the bff package.
COPY --from=spa /app/dist app/dist

# The session database and the HLS segments live in /data. PROXY_URL is STB-Proxy's address
# from this container; in a compose project next to it, that's its service name.
ENV SESSION_DB=/data/sessions.db \
	HLS_DIR=/data/hls \
	PROXY_URL=http://stb-proxy:8001
VOLUME /data
EXPOSE 8000

ENTRYPOINT ["/sbin/tini","--","uvicorn","bff.main:app","--host","0.0.0.0","--port","8000","--workers","1","--limit-concurrency","30"]
