#!/usr/bin/env bash
# Reproducible swe-af fan-out batch live smoke (debug / demo).
# Drives the deployed orchestrator on a worker host: enqueues one issue, watches
# the run, prints the resulting draft PR. Wrap with `asciinema rec -c` to record.
#
# Prereqs (see ../../vaked-agents/ci/swe-af-orchestrator/deploy/README.md):
#   - worker on the tailnet (tag:agents); gh authed (keyring) with HOME set;
#   - vaked-swe-af + swe-af-orchestrator + swe-af-enqueue in PATH;
#   - a JetStream NATS reachable at $NATS_URL; orchestrator running (systemd-run
#     or the unit) with OPENROUTER_BASE_URL=https://nixai-base.tail2870dc.ts.net/v1
#
# Usage:
#   NATS_URL=nats://127.0.0.1:4223 REPO=peterlodri-sec/vaked-base ./swe-af-smoke.sh [ISSUE]
set -euo pipefail
: "${NATS_URL:?set NATS_URL}"
REPO=${REPO:-peterlodri-sec/vaked-base}
ISSUE="${1:-}"

step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }

if [ -z "$ISSUE" ]; then
  step "create self-contained smoke issue"
  ISSUE=$(gh issue create -R "$REPO" \
    --title "smoke: swe-af self-test — create docs/SWE_AF_SMOKE.md" \
    --body $'Create `docs/SWE_AF_SMOKE.md` with one line: `swe-af smoke run OK`. Self-contained; safe to close.' \
    | grep -oE '[0-9]+$')
  echo "issue #$ISSUE"
fi

step "enqueue issue #$ISSUE onto $NATS_URL"
swe-af-enqueue --repo "$REPO" --issue "$ISSUE"

step "watch the orchestrator (Ctrl-C after 'task done')"
echo "journalctl -u swe-af-orchestrator -f   # or: -u swe-af-smoke"

step "poll for the draft PR"
for _ in $(seq 1 30); do
  url=$(gh pr list -R "$REPO" --head "swe-af/issue-$ISSUE" --json url -q '.[0].url' 2>/dev/null || true)
  [ -n "${url:-}" ] && { echo "PR: $url"; gh pr diff "$ISSUE" 2>/dev/null | head -20 || true; break; }
  sleep 4
done
[ -z "${url:-}" ] && echo "no PR yet — check journalctl for errors"
