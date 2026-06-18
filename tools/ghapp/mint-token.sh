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
#
# Library mode: set MINT_TOKEN_LIB=1 before sourcing to define functions
# (base64url, build_jwt) WITHOUT running main — used by the test suite.

set -euo pipefail

# ── base64url encoder (url-safe, no padding, NO newlines) ──────────────────────
# Accepts binary on stdin; prints base64url to stdout.
# Capability-probes for GNU base64 (-w0) vs BSD/macOS base64 (no -w flag);
# strips any newlines in both branches so JWT segments never wrap.
base64url() {
  if base64 -w0 </dev/null >/dev/null 2>&1; then
    # GNU coreutils: -w0 disables line wrapping.
    base64 -w0 | tr -d '\n' | tr '+/' '-_' | tr -d '='
  else
    # BSD/macOS: no -w flag; strip newlines explicitly.
    base64 | tr -d '\n' | tr '+/' '-_' | tr -d '='
  fi
}

# ── build JWT ─────────────────────────────────────────────────────────────────
# Args: $1 = app id, $2 = pem file path. Echoes the signed JWT to stdout.
build_jwt() {
  local app_id="$1" pem="$2" now iat exp header payload signing_input sig
  now=$(date +%s)
  iat=$(( now - 60 ))
  exp=$(( now + 540 ))

  header='{"alg":"RS256","typ":"JWT"}'
  # NOTE: iss MUST be a JSON string — GitHub rejects a numeric iss.
  payload="{\"iat\":${iat},\"exp\":${exp},\"iss\":\"${app_id}\"}"

  local b64_header b64_payload
  b64_header=$(printf '%s' "${header}"  | base64url)
  b64_payload=$(printf '%s' "${payload}" | base64url)
  signing_input="${b64_header}.${b64_payload}"

  sig=$(printf '%s' "${signing_input}" \
    | openssl dgst -sha256 -sign "${pem}" \
    | base64url)

  printf '%s.%s' "${signing_input}" "${sig}"
}

# ── library-mode short-circuit ────────────────────────────────────────────────
# When sourced with MINT_TOKEN_LIB=1, return now so only functions are defined.
if [[ "${MINT_TOKEN_LIB:-}" == "1" ]]; then
  return 0
fi

# ── main ──────────────────────────────────────────────────────────────────────
main() {
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

  local jwt
  jwt=$(build_jwt "${VAKED_CI_APP_ID}" "${GHAPP_PRIVATE_KEY_FILE}")

  # ── resolve installation ID ──────────────────────────────────────────────
  # Capture body and HTTP status separately. On failure we print ONLY the
  # status code — never the body or request headers, which could echo the JWT.
  printf 'mint-token: resolving installation for %s\n' "${GHAPP_REPO}" >&2

  local install_resp install_status install_body install_id
  install_resp=$(curl --silent --show-error \
    -w '\n%{http_code}' \
    -H "Authorization: Bearer ${jwt}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${GHAPP_REPO}/installation" 2>/dev/null) || {
      printf 'mint-token: curl failed contacting installation endpoint\n' >&2
      exit 1
  }
  install_status="${install_resp##*$'\n'}"
  install_body="${install_resp%$'\n'*}"

  if [[ "${install_status}" != "200" ]]; then
    printf 'mint-token: installation lookup failed (HTTP %s)\n' "${install_status}" >&2
    exit 1
  fi

  install_id=$(printf '%s' "${install_body}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])' 2>/dev/null) || {
      printf 'mint-token: failed to parse installation id from response\n' >&2
      exit 1
  }

  if [[ -z "${install_id}" ]]; then
    printf 'mint-token: empty installation id in response\n' >&2
    exit 1
  fi

  printf 'mint-token: installation id=%s\n' "${install_id}" >&2

  # ── mint installation access token ───────────────────────────────────────
  local token_resp token_status token_body token
  token_resp=$(curl --silent --show-error \
    -w '\n%{http_code}' \
    -X POST \
    -H "Authorization: Bearer ${jwt}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/app/installations/${install_id}/access_tokens" 2>/dev/null) || {
      printf 'mint-token: curl failed contacting access_tokens endpoint\n' >&2
      exit 1
  }
  token_status="${token_resp##*$'\n'}"
  token_body="${token_resp%$'\n'*}"

  if [[ "${token_status}" != "201" && "${token_status}" != "200" ]]; then
    printf 'mint-token: token mint failed (HTTP %s)\n' "${token_status}" >&2
    exit 1
  fi

  token=$(printf '%s' "${token_body}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])' 2>/dev/null) || {
      printf 'mint-token: failed to parse token from response\n' >&2
      exit 1
  }

  if [[ -z "${token}" ]]; then
    printf 'mint-token: empty token in response\n' >&2
    exit 1
  fi

  printf 'mint-token: token minted successfully\n' >&2

  # Print ONLY the token to stdout.
  printf '%s\n' "${token}"
}

main "$@"
