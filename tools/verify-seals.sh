#!/usr/bin/env bash
# verify-seals.sh — the external verifier.
#
# The self cannot see itself: a file cannot contain its own hash. So the
# signature of each sealed artifact lives OUTSIDE it, in SEALS.sha256. This
# script recomputes every artifact and FAILS (exit 1) on any mismatch.
#
# A seal that cannot fail is not a seal. This one can, and does.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${REPO_ROOT}/the-honest-swarm-researcher/SEALS.sha256"

if [[ ! -f "$MANIFEST" ]]; then
  echo "FAIL: seal manifest not found: $MANIFEST" >&2
  exit 1
fi

# pick a sha256 tool (shasum on macOS, sha256sum on Linux/CI)
if command -v sha256sum >/dev/null 2>&1; then
  CHECK=(sha256sum -c --strict)
elif command -v shasum >/dev/null 2>&1; then
  CHECK=(shasum -a 256 -c)
else
  echo "FAIL: no sha256 tool (need sha256sum or shasum)" >&2
  exit 1
fi

cd "$REPO_ROOT"
echo "Verifying sealed artifacts against $(basename "$MANIFEST") …"
if "${CHECK[@]}" "$MANIFEST"; then
  echo "OK: all seals hold. The external POV confirms the artifacts."
  exit 0
else
  echo "FAIL: a sealed artifact does not match its external signature — tampered or re-sealed without updating SEALS.sha256." >&2
  exit 1
fi
