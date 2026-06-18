#!/usr/bin/env bash
# verify-seals.sh — the external verifier (hardened after the gate-breaker audit).
#
# The self cannot see itself: a file cannot contain its own hash. So the
# signature of each sealed artifact lives OUTSIDE it, in SEALS.sha256. This
# script recomputes every artifact and FAILS (exit 1) on any mismatch.
#
# Hardening over v1 (bypasses confirmed by honesty-gate-breaker):
#   - coverage gate: every artifact in the sealed set MUST be listed in the
#     manifest, so a rogue/new doc cannot escape verification by being unsealed.
#   - non-empty guard: an empty/garbage manifest is a FAIL, not a silent PASS
#     (sha256sum -c on an empty file exits 0 — the tooling false-pass).
#   - --strict on both platforms, so a malformed manifest line fails on mac too.
#   - HONESTY_REPO_ROOT override: CI runs THIS script from trusted main against
#     the PR's tree, so a PR cannot neuter its own verifier (gate-self-modify).
#
# Residual (cannot be fixed in-tree): the manifest itself is the unanchored trust
# root — an actor with write access can tamper-and-reseal in one commit. The real
# fix is an external anchor (signed git tag `git tag -v`, or Sigstore/Rekor). See
# the-honest-swarm-researcher/REPAIR_AUDIT.json -> residual_risks.
set -euo pipefail

REPO_ROOT="${HONESTY_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OPDIR="${REPO_ROOT}/the-honest-swarm-researcher"
MANIFEST="${OPDIR}/SEALS.sha256"

# the sealed set: every audit artifact that must be covered by the manifest.
# (anomaly_manifest.json is living state, guarded by reconcile-gate; SEALS.sha256
#  is the manifest itself and cannot list itself.)
sealed_set() {
  local f
  for f in "${OPDIR}"/*.md "${OPDIR}"/REPAIR_AUDIT.json \
           "${REPO_ROOT}"/docs/reports/2026-06-18-ceremony2-independent-reaudit.md \
           "${REPO_ROOT}"/docs/reports/2026-06-18-ceremony2b-the-self-cannot-see-itself.md; do
    [[ -f "$f" ]] || continue
    case "$f" in
      */anomaly_manifest.json|*/SEALS.sha256) continue ;;
    esac
    # emit repo-root-relative path (matches manifest entries)
    echo "${f#${REPO_ROOT}/}"
  done | sort -u
}

if [[ ! -f "$MANIFEST" ]]; then
  echo "FAIL: seal manifest not found: $MANIFEST" >&2
  exit 1
fi

# non-empty guard: count well-formed "<64hex>  <path>" lines
VALID_LINES="$(grep -cE '^[0-9a-fA-F]{64}[[:space:]]' "$MANIFEST" || true)"
if [[ "${VALID_LINES:-0}" -eq 0 ]]; then
  echo "FAIL: seal manifest has no valid checksum lines: $MANIFEST" >&2
  exit 1
fi

cd "$REPO_ROOT"

# coverage gate: every artifact in the sealed set must appear in the manifest.
missing=0
while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  if ! awk '{ $1=""; sub(/^[ \t]+/,""); print }' "$MANIFEST" | grep -qxF "$rel"; then
    echo "FAIL (coverage): artifact not sealed in manifest: $rel" >&2
    missing=1
  fi
done < <(sealed_set)
if [[ "$missing" -ne 0 ]]; then
  echo "FAIL: one or more artifacts are present on disk but absent from SEALS.sha256." >&2
  exit 1
fi

# pick a sha256 tool; --strict on both so malformed lines fail everywhere
if command -v sha256sum >/dev/null 2>&1; then
  CHECK=(sha256sum -c --strict)
elif command -v shasum >/dev/null 2>&1; then
  CHECK=(shasum -a 256 -c --strict)
else
  echo "FAIL: no sha256 tool (need sha256sum or shasum)" >&2
  exit 1
fi

echo "Verifying $VALID_LINES sealed artifacts against $(basename "$MANIFEST") (coverage OK) …"
if "${CHECK[@]}" "$MANIFEST"; then
  echo "OK: all seals hold. The external POV confirms the artifacts."
  exit 0
else
  echo "FAIL: a sealed artifact does not match its external signature — tampered or re-sealed without updating SEALS.sha256." >&2
  exit 1
fi
