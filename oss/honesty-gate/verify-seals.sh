#!/usr/bin/env bash
# verify-seals.sh — the external, failable verifier.
#
# The self cannot see itself: a file cannot contain its own hash. So the
# signature of each artifact lives OUTSIDE it, in a manifest. This recomputes
# every artifact and EXITS 1 on any mismatch. A seal that cannot fail is not a seal.
#
# Config (all optional, via env):
#   HONESTY_MANIFEST   path to the SHA-256 manifest      (default: ./SEALS.sha256)
#   HONESTY_ROOT       repo root the manifest paths are relative to (default: manifest dir)
#   HONESTY_COVER      space-separated globs that MUST all be sealed (coverage gate)
#   HONESTY_ANCHOR_TAG glob for a GPG-signed git tag carrying sha256(manifest)
#                      e.g. "seals-anchor-*"  — verified with `git tag -v`
#
# MIT licensed. Extracted from github.com/peterlodri-sec/vaked-base.
set -euo pipefail

MANIFEST="${HONESTY_MANIFEST:-./SEALS.sha256}"
[[ -f "$MANIFEST" ]] || { echo "FAIL: manifest not found: $MANIFEST" >&2; exit 1; }
ROOT="${HONESTY_ROOT:-$(cd "$(dirname "$MANIFEST")" && pwd)}"

# pick a sha256 tool; --strict so malformed lines fail on every platform
if command -v sha256sum >/dev/null 2>&1; then CHECK=(sha256sum -c --strict); HASH=(sha256sum)
elif command -v shasum  >/dev/null 2>&1; then CHECK=(shasum -a 256 -c --strict); HASH=(shasum -a 256)
else echo "FAIL: need sha256sum or shasum" >&2; exit 1; fi

# non-empty guard: an empty/garbage manifest is a FAIL, not a silent pass
VALID=$(grep -cE '^[0-9a-fA-F]{64}[[:space:]]' "$MANIFEST" || true)
[[ "${VALID:-0}" -gt 0 ]] || { echo "FAIL: manifest has no valid checksum lines: $MANIFEST" >&2; exit 1; }

cd "$ROOT"

# coverage gate: every file matched by HONESTY_COVER must appear in the manifest
if [[ -n "${HONESTY_COVER:-}" ]]; then
  miss=0
  for g in $HONESTY_COVER; do
    for f in $g; do
      [[ -f "$f" ]] || continue
      rel="${f#./}"
      if ! awk '{ $1=""; sub(/^[ \t]+/,""); print }' "$MANIFEST" | grep -qxF "$rel"; then
        echo "FAIL (coverage): present on disk but unsealed: $rel" >&2; miss=1
      fi
    done
  done
  [[ "$miss" -eq 0 ]] || { echo "FAIL: unsealed artifacts exist." >&2; exit 1; }
fi

echo "Verifying $VALID sealed artifact(s) against $(basename "$MANIFEST") …"
"${CHECK[@]}" "$MANIFEST" || { echo "FAIL: a sealed artifact does not match its signature." >&2; exit 1; }
echo "OK: all seals hold."

# external anchor (optional): a GPG-signed tag carrying sha256(manifest). The key
# is NOT in the repo, so a tamper-and-reseal in the same commit fails this.
if [[ -n "${HONESTY_ANCHOR_TAG:-}" ]]; then
  TAG="$(git -C "$ROOT" tag -l "$HONESTY_ANCHOR_TAG" 2>/dev/null | sort | tail -1 || true)"
  if [[ -n "$TAG" ]]; then
    git -C "$ROOT" tag -v "$TAG" >/dev/null 2>&1 || { echo "FAIL (anchor): $TAG signature invalid." >&2; exit 1; }
    want="$(git -C "$ROOT" tag -l --format='%(contents)' "$TAG" | grep -oiE '[0-9a-f]{64}' | head -1)"
    got="$("${HASH[@]}" "$MANIFEST" | cut -d' ' -f1)"
    [[ -z "$want" || "$want" == "$got" ]] || { echo "FAIL (anchor): manifest $got != signed tag $want." >&2; exit 1; }
    echo "OK: external anchor $TAG verified (signed, hash matches)."
  else
    echo "NOTE: no $HONESTY_ANCHOR_TAG tag yet — manifest unanchored. Create with:"
    echo "  git tag -s seals-anchor-\$(date +%Y%m%d) -m \"sha256(manifest)=\$(${HASH[*]} $MANIFEST | cut -d' ' -f1)\""
  fi
fi
exit 0
