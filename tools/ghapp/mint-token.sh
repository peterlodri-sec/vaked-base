#!/usr/bin/env bash
# mint-token.sh — Mint a GitHub App installation access token (valid ~1h).
#
# Usage:
#   VAKED_CI_APP_ID=<app-id> bash mint-token.sh
#
# Env vars:
#   VAKED_CI_APP_ID         (required) GitHub App numeric ID
#   GHAPP_PRIVATE_KEY_FILE  (default: ~/.config/vaked-ci/app.pem) RSA private key
#   GHAPP_REPO              (default: peterlodri-sec/vaked-base) owner/repo
#
# Prints ONLY the installation access token to stdout. All diagnostic output
# goes to stderr. Exits non-zero on any error. Never logs the PEM, JWT, or token.
#
# Note: tokens expire in ~1 hour (GitHub max). Re-mint as needed.

set -euo pipefail

# ── env / defaults ─────────────────────────────────────────────────────────────
: "${GHAPP_PRIVATE_KEY_FILE:=${HOME}/.config/vaked-ci/app.pem}"
: "${GHAPP_REPO:=peterlodri-sec/vaked-base}"

if [[ -z "${VAKED_CI_APP_ID:-}" ]]; then
  printf 'mint-token: VAKED_CI_APP_ID is not set\n' >&2
  exit 1
fi

if [[ ! -f "${GHAPP_PRIVATE_KEY_FILE}" ]]; then
  printf 'mint-token: PEM file not found: %s\n' "${GHAPP_PRIVATE_KEY_FILE}" >&2
  exit 1
fi

# ── base64url encoder (url-safe, no padding) ───────────────────────────────────
# Accepts binary on stdin; prints base64url to stdout.
base64url() {
  # base64 (macOS and GNU both support -w0 / no-wrap via different flags)
  local b64
  if base64 --version >/dev/null 2>&1; then
    # GNU coreutils
    b64=$(base64 -w 0)
  else
    # macOS
    b64=$(base64)
  fi
  printf '%s' "${b64}" | tr '+/' '-_' | tr -d '='
}

# ── build JWT ─────────────────────────────────────────────────────────────────
NOW=$(date +%s)
IAT=$(( NOW - 60 ))
EXP=$(( NOW + 540 ))

HEADER_JSON='{"alg":"RS256","typ":"JWT"}'
PAYLOAD_JSON="{\"iat\":${IAT},\"exp\":${EXP},\"iss\":${VAKED_CI_APP_ID}}"

B64_HEADER=$(printf '%s' "${HEADER_JSON}"  | base64url)
B64_PAYLOAD=$(printf '%s' "${PAYLOAD_JSON}" | base64url)
SIGNING_INPUT="${B64_HEADER}.${B64_PAYLOAD}"

B64_SIG=$(printf '%s' "${SIGNING_INPUT}" \
  | openssl dgst -sha256 -sign "${GHAPP_PRIVATE_KEY_FILE}" \
  | base64url)

JWT="${SIGNING_INPUT}.${B64_SIG}"

# ── resolve installation ID ───────────────────────────────────────────────────
printf 'mint-token: resolving installation for %s\n' "${GHAPP_REPO}" >&2

INSTALL_RESP=$(curl --silent --fail-with-body \
  -H "Authorization: Bearer ${JWT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GHAPP_REPO}/installation")

INSTALL_ID=$(printf '%s' "${INSTALL_RESP}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

if [[ -z "${INSTALL_ID}" ]]; then
  printf 'mint-token: failed to parse installation id from response\n' >&2
  exit 1
fi

printf 'mint-token: installation id=%s\n' "${INSTALL_ID}" >&2

# ── mint installation access token ───────────────────────────────────────────
TOKEN_RESP=$(curl --silent --fail-with-body \
  -X POST \
  -H "Authorization: Bearer ${JWT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/app/installations/${INSTALL_ID}/access_tokens")

TOKEN=$(printf '%s' "${TOKEN_RESP}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

if [[ -z "${TOKEN}" ]]; then
  printf 'mint-token: failed to parse token from response\n' >&2
  exit 1
fi

printf 'mint-token: token minted successfully\n' >&2

# Print ONLY the token to stdout
printf '%s\n' "${TOKEN}"
