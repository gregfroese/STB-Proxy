# Pinned so a new Alpine release can't change Python, Flask or ffmpeg under us.
FROM alpine:3.24

# HOST is the address players use to reach STB-Proxy: it goes into the playlist,
# XMLTV and tuner links, so set it to this machine's address, e.g. 192.168.1.10:8001.
# CONFIG holds every portal and edit; devices.json (optional) sits next to it.
ENV HOST=localhost:8001
ENV CONFIG=/config/config.json
# Stops a threaded Python server holding on to memory it has freed.
ENV MALLOC_ARENA_MAX=2

# Alpine's own packages: its Python refuses system-wide pip installs.
RUN apk add --no-cache \
	ffmpeg \
	python3 \
	py3-flask \
	py3-requests \
	py3-waitress \
	tini \
	tzdata

WORKDIR /app

# Copy files
COPY /app.py /app/app.py
COPY /stb.py /app/stb.py
COPY /availability.py /app/availability.py
COPY /plex.py /app/plex.py
COPY /jellyfin.py /app/jellyfin.py
COPY /guide.py /app/guide.py
COPY /logos.py /app/logos.py
COPY /recordings.py /app/recordings.py
COPY /changelog.py /app/changelog.py
COPY /version.py /app/version.py
COPY /CHANGELOG.md /app/CHANGELOG.md
COPY /templates /app/templates
COPY /static /app/static

EXPOSE 8001
VOLUME /config

# tini runs as PID 1: it passes Docker's stop signal on to STB-Proxy (a process that is
# PID 1 itself ignores it, so every stop waited 10 s and was then killed) and cleans up
# finished ffmpeg processes.
ENTRYPOINT ["/sbin/tini","--","python3","-u","/app/app.py"]
