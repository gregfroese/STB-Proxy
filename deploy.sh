#!/usr/bin/env bash
# Deploy STB-Proxy to the stb-proxy LXC.
#
# The LXC (CT 115) runs a git checkout of this repo on master and the
# stb-proxy.service unit. Deploying means: commit the working tree, push it,
# have the LXC pull, and restart the unit. Run from a checkout on the dev
# machine:
#
#     ./deploy.sh "portals: fix Add modal scroll and surface test feedback"
#
# With nothing to commit it re-deploys the current commit. Override the target
# with PROXMOX_HOST / CTID / REMOTE_DIR / SERVICE / BRANCH.
set -euo pipefail

PROXMOX_HOST="${PROXMOX_HOST:-proxmox}"
CTID="${CTID:-115}"
REMOTE_DIR="${REMOTE_DIR:-/opt/stb-proxy/app}"
SERVICE="${SERVICE:-stb-proxy}"
BRANCH="${BRANCH:-master}"

cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    message="${1:-}"
    if [ -z "$message" ]; then
        echo "error: there are uncommitted changes; pass a commit message:" >&2
        echo "       $0 \"what changed\"" >&2
        exit 1
    fi
    echo "==> Committing changes"
    git add -u
    git commit -m "$message"
else
    echo "==> No tracked changes to commit"
fi

untracked="$(git ls-files --others --exclude-standard)"
if [ -n "$untracked" ]; then
    echo "==> Note: these untracked files are NOT deployed (git add them to include):"
    echo "$untracked" | sed 's/^/      /'
fi

echo "==> Pushing $BRANCH to origin"
git push origin "$BRANCH"

echo "==> Deploying on $PROXMOX_HOST (CT $CTID)"
ssh "$PROXMOX_HOST" "pct exec $CTID -- bash -lc 'git -C $REMOTE_DIR pull --ff-only && systemctl restart $SERVICE'"

echo "==> Waiting for $SERVICE"
active=""
for _ in $(seq 1 15); do
    active="$(ssh "$PROXMOX_HOST" "pct exec $CTID -- systemctl is-active $SERVICE" 2>/dev/null || true)"
    [ "$active" = "active" ] && break
    sleep 1
done

if [ "$active" != "active" ]; then
    echo "error: $SERVICE is not active on CT $CTID" >&2
    ssh "$PROXMOX_HOST" "pct exec $CTID -- journalctl -u $SERVICE -n 30 --no-pager" >&2 || true
    exit 1
fi

echo "==> Deployed $(git rev-parse --short HEAD) — $SERVICE active on CT $CTID"
