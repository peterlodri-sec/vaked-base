#!/usr/bin/env bash
# mint-token.test.sh — offline unit tests for mint-token.sh
#
# Tests:
#   1. The REAL base64url encoder (sourced from mint-token.sh): known vectors.
#   2. build_jwt emits iss as a JSON STRING (not a number).
#   3. Script exits non-zero when VAKED_CI_APP_ID is unset.
#   4. Script exits non-zero when PEM file is absent (VAKED_CI_APP_ID set).
#
# No network access is required. All tests must pass offline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINT="${SCRIPT_DIR}/mint-token.sh"

# Source the script in library mode: the MINT_TOKEN_LIB=1 guard makes it
# `return 0` before main runs, so only the functions get defined here.
# shellcheck source=tools/ghapp/mint-token.sh
MINT_TOKEN_LIB=1 source "${MINT}"

PASS=0
FAIL=0

pass() { printf 'PASS: %s\n' "$1"; PASS=$(( PASS + 1 )); }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=$(( FAIL + 1 )); }

# ── Test 1: REAL base64url encoder ────────────────────────────────────────────
# RFC 4648 known vectors (url-safe, padding stripped):
#   '{}' -> base64 'e30=' -> 'e30'
#   ''   -> ''
#   'f'  -> base64 'Zg==' -> 'Zg'
T1_OUT=$(printf '%s' '{}' | base64url)
if [[ "${T1_OUT}" == "e30" ]]; then
  pass "base64url('{}')==e30 (real fn)"
else
  fail "base64url('{}'): expected 'e30', got '${T1_OUT}'"
fi

T1B_OUT=$(printf '%s' '' | base64url)
if [[ "${T1B_OUT}" == "" ]]; then
  pass "base64url('')=='' (real fn)"
else
  fail "base64url(''): expected '', got '${T1B_OUT}'"
fi

T1C_OUT=$(printf '%s' 'f' | base64url)
if [[ "${T1C_OUT}" == "Zg" ]]; then
  pass "base64url('f')=='Zg' (real fn)"
else
  fail "base64url('f'): expected 'Zg', got '${T1C_OUT}'"
fi

# Guard against newline-wrapping: encode a long input and assert single line.
T1D_OUT=$(head -c 200 /dev/zero | tr '\0' 'A' | base64url)
T1D_LINES=$(printf '%s' "${T1D_OUT}" | wc -l | tr -d ' ')
if [[ "${T1D_LINES}" == "0" ]]; then
  pass "base64url long-input has no embedded newlines"
else
  fail "base64url long-input wrapped (newline count=${T1D_LINES})"
fi

# ── Test 2: build_jwt emits iss as a JSON string ──────────────────────────────
# Decode the JWT payload (segment 2) and verify iss is the typed string "12345".
# Use a throwaway RSA key so the openssl signing step succeeds offline.
TMP_PEM=$(mktemp 2>/dev/null || mktemp -t mintpem)
trap 'rm -f "${TMP_PEM}"' EXIT
openssl genrsa -out "${TMP_PEM}" 2048 >/dev/null 2>&1

JWT=$(build_jwt "12345" "${TMP_PEM}")
PAYLOAD_SEG=$(printf '%s' "${JWT}" | cut -d. -f2)
# Re-pad base64url for decoding, restore +/, then JSON-decode and check type.
ISS_TYPE=$(printf '%s' "${PAYLOAD_SEG}" | python3 -c '
import sys, base64, json
seg = sys.stdin.read().strip().replace("-", "+").replace("_", "/")
seg += "=" * (-len(seg) % 4)
p = json.loads(base64.b64decode(seg))
print(type(p["iss"]).__name__ + ":" + str(p["iss"]))
')
if [[ "${ISS_TYPE}" == "str:12345" ]]; then
  pass "build_jwt iss is JSON string \"12345\""
else
  fail "build_jwt iss type/value wrong: got '${ISS_TYPE}', expected 'str:12345'"
fi

# ── Test 3: exits non-zero when VAKED_CI_APP_ID is unset ─────────────────────
T3_EXIT=0
(
  unset VAKED_CI_APP_ID
  GHAPP_PRIVATE_KEY_FILE="/tmp/does-not-exist-for-test.pem"
  export GHAPP_PRIVATE_KEY_FILE
  bash "${MINT}" >/dev/null 2>/dev/null
) || T3_EXIT=$?

if [[ "${T3_EXIT}" -ne 0 ]]; then
  pass "exits non-zero when VAKED_CI_APP_ID unset (exit=${T3_EXIT})"
else
  fail "expected non-zero exit when VAKED_CI_APP_ID unset, got 0"
fi

# ── Test 4: exits non-zero when PEM file is absent ───────────────────────────
T4_EXIT=0
(
  export VAKED_CI_APP_ID="12345"
  GHAPP_PRIVATE_KEY_FILE="/tmp/no-such-pem-$(date +%s).pem"
  export GHAPP_PRIVATE_KEY_FILE
  bash "${MINT}" >/dev/null 2>/dev/null
) || T4_EXIT=$?

if [[ "${T4_EXIT}" -ne 0 ]]; then
  pass "exits non-zero when PEM file absent (exit=${T4_EXIT})"
else
  fail "expected non-zero exit when PEM absent, got 0"
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
printf 'Results: %d passed, %d failed\n' "${PASS}" "${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
