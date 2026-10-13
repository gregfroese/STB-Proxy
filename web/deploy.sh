#!/usr/bin/env bash
# Build and deploy the STB-Proxy web viewer on LXC 119 (stb-proxy-web).
#
# Pull the repo, build the SPA, install BFF requirements, restart the unit.
# Override paths with environment variables if your checkout differs.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/stb-proxy}"
VENV_DIR="${VENV_DIR:-/opt/stb-proxy-web/venv}"
SERVICE="${SERVICE:-stb-proxy-web}"

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

echo "==> Pulling $REPO_DIR"
git -C "$REPO_DIR" pull --ff-only

echo "==> Building the SPA"
cd "$REPO_DIR/web/app"
npm ci
npm run build

echo "==> Installing BFF requirements"
"$VENV_DIR/bin/pip" install --upgrade -r "$REPO_DIR/web/requirements.txt"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "==> Installing ffmpeg (HLS fallback)"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg
fi

echo "==> Restarting $SERVICE"
$SUDO systemctl restart "$SERVICE"

echo "==> Done"
