#!/usr/bin/env bash
# Deploy vaked-telebot as a persistent systemd daemon on a stock host (crabcc.app).
# Idempotent: re-running pulls the repo, reinstalls the unit, and restarts.
#
#   # 1) one-time: the secrets file (root-only)
#   sudo install -m 600 /dev/stdin /etc/vaked-telebot.env <<'ENV'
#   TELEGRAM_TOKEN=123:abc
#   TELEGRAM_TO=-5386943266
#   TELEGRAM_ADMIN_IDS=<your numeric telegram id>
#   GITHUB_TOKEN=ghp_...                 # Actions: read/write, Contents: read
#   GITHUB_REPOSITORY=peterlodri-sec/vaked-base
#   OPENROUTER_API_KEY=sk-or-...
#   ENV
#
#   # 2) deploy (clones to /opt/vaked-base if absent; pass a path to override)
#   sudo bash tools/telebot/deploy.sh [/path/to/checkout]
#
# NixOS: don't use this — write a systemd.services.vaked-telebot module with the
# store python3 + sops/agenix for the credential (the daemon is stdlib-only).
set -euo pipefail

REPO="${1:-/opt/vaked-base}"
ENVFILE=/etc/vaked-telebot.env
UNIT=/etc/systemd/system/vaked-telebot.service
REMOTE="https://github.com/peterlodri-sec/vaked-base"

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }

if [ ! -d "$REPO/.git" ]; then
  echo "==> cloning $REMOTE → $REPO"
  git clone --depth 1 "$REMOTE" "$REPO"
else
  echo "==> updating $REPO"
  git -C "$REPO" pull --ff-only || echo "  (pull skipped)"
fi

if [ ! -f "$ENVFILE" ]; then
  echo "ERROR: $ENVFILE not found. Create it first (see the header of this script)." >&2
  exit 1
fi
chmod 600 "$ENVFILE"

echo "==> installing unit → $UNIT"
install -m 644 "$REPO/tools/telebot/vaked-telebot.service" "$UNIT"
if [ "$REPO" != "/opt/vaked-base" ]; then
  sed -i "s#^WorkingDirectory=.*#WorkingDirectory=$REPO#" "$UNIT"
fi

command -v python3 >/dev/null || { echo "python3 not found on PATH"; exit 1; }

systemctl daemon-reload
systemctl enable --now vaked-telebot
echo "==> status"
systemctl --no-pager --lines=0 status vaked-telebot || true
echo
echo "Deployed. Logs:  journalctl -u vaked-telebot -f"
echo "Then send /menu in the vaked group. (Stop the GitHub 'telebot' workflow if it's running — one poller at a time.)"
