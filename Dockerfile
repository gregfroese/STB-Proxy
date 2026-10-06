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
	tzdata

WORKDIR /app

# Copy files
COPY /app.py /app/app.py
COPY /stb.py /app/stb.py
COPY /availability.py /app/availability.py
COPY /plex.py /app/plex.py
COPY /guide.py /app/guide.py
COPY /templates /app/templates
COPY /static /app/static

EXPOSE 8001
VOLUME /config

ENTRYPOINT ["python3","-u","/app/app.py"]
