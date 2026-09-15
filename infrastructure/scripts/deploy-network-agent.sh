#!/usr/bin/env bash
# Pulls the latest Network Agent code and restarts it on the Network VPS.
# Usage: sudo ./deploy-network-agent.sh [git-ref]

set -euo pipefail

APP_DIR="/opt/infinity-radius"
# Only apps/network-agent (+ infrastructure/) is deployed here, not a full
# monorepo checkout — see infrastructure/systemd/network-agent.service —
# so this is a plain subdirectory, not "apps/network-agent". Confirmed
# against the first real deployment (infinity-radius-network-01, 2026-09-14).
AGENT_DIR="$APP_DIR/network-agent"
SERVICE_NAME="infinity-radius-network-agent"
GIT_REF="${1:-main}"

if [[ $EUID -ne 0 ]]; then
    echo "Run as root (sudo ./deploy-network-agent.sh [git-ref])" >&2
    exit 1
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
    echo "$APP_DIR is not a git checkout — clone the repo there first." >&2
    exit 1
fi

echo "==> Fetching $GIT_REF"
git -C "$APP_DIR" fetch origin "$GIT_REF"
git -C "$APP_DIR" checkout "$GIT_REF"
git -C "$APP_DIR" pull --ff-only origin "$GIT_REF"

echo "==> Installing dependencies"
cd "$AGENT_DIR"
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi
./.venv/bin/pip install --no-cache-dir -e "."

echo "==> Running checks before restart"
./.venv/bin/python -m compileall app >/dev/null

echo "==> Restarting service"
systemctl restart "$SERVICE_NAME"
sleep 2
systemctl is-active --quiet "$SERVICE_NAME" && echo "$SERVICE_NAME is active" || {
    echo "$SERVICE_NAME failed to start — check: journalctl -u $SERVICE_NAME -n 100" >&2
    exit 1
}

echo "==> Deployed $GIT_REF"
