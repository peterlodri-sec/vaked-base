#!/usr/bin/env bash
# mint-token.test.sh — offline unit tests for mint-token.sh
#
# Tests:
#   1. base64url encoder: echo -n '{}' -> 'e30'
#   2. Script exits non-zero when VAKED_CI_APP_ID is unset
#   3. Script exits non-zero when PEM file is absent (VAKED_CI_APP_ID is set)
#
# No network access is required. All tests must pass offline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINT="${SCRIPT_DIR}/mint-token.sh"

PASS=0
FAIL=0

pass() { printf 'PASS: %s\n' "$1"; (( PASS++ )) || true; }
fail() { printf 'FAIL: %s\n' "$1"; (( FAIL++ )) || true; }

# ── helper: extract and call the base64url function from mint-token.sh ─────────
# We source the script in a guarded subshell that replaces the main body with
# a no-op by overriding the functions-only portion. Since the script uses
# set -e and exits on missing env, we can't source it directly. Instead we
# reproduce the base64url function inline (it's a pure bash+openssl construct)
# and test it independently.

base64url_test() {
  local b64
  if base64 --version >/dev/null 2>&1; then
    b64=$(base64 -w 0)
  else
    b64=$(base64)
  fi
  printf '%s' "${b64}" | tr '+/' '-_' | tr -d '='
}

# ── Test 1: base64url encoder ─────────────────────────────────────────────────
# RFC 4648 known vector: '{}' (2 bytes) -> base64 'e30=' -> base64url 'e30'
T1_OUT=$(printf '%s' '{}' | base64url_test)
if [[ "${T1_OUT}" == "e30" ]]; then
  pass "base64url('{}')==e30"
else
  fail "base64url('{}'): expected 'e30', got '${T1_OUT}'"
fi

# Additional vector: '' (empty) -> '' (empty)
T1B_OUT=$(printf '%s' '' | base64url_test)
if [[ "${T1B_OUT}" == "" ]]; then
  pass "base64url('')==''"
else
  fail "base64url(''): expected '', got '${T1B_OUT}'"
fi

# Additional vector: 'f' -> 'Zg' (base64 'Zg==', strip padding)
T1C_OUT=$(printf '%s' 'f' | base64url_test)
if [[ "${T1C_OUT}" == "Zg" ]]; then
  pass "base64url('f')=='Zg'"
else
  fail "base64url('f'): expected 'Zg', got '${T1C_OUT}'"
fi

# ── Test 2: exits non-zero when VAKED_CI_APP_ID is unset ─────────────────────
T2_EXIT=0
(
  unset VAKED_CI_APP_ID
  GHAPP_PRIVATE_KEY_FILE="/tmp/does-not-exist-for-test.pem"
  export GHAPP_PRIVATE_KEY_FILE
  bash "${MINT}" >/dev/null 2>/dev/null
) || T2_EXIT=$?

if [[ "${T2_EXIT}" -ne 0 ]]; then
  pass "exits non-zero when VAKED_CI_APP_ID unset (exit=${T2_EXIT})"
else
  fail "expected non-zero exit when VAKED_CI_APP_ID unset, got 0"
fi

# ── Test 3: exits non-zero when PEM file is absent ───────────────────────────
T3_EXIT=0
(
  export VAKED_CI_APP_ID="12345"
  GHAPP_PRIVATE_KEY_FILE="/tmp/no-such-pem-$(date +%s).pem"
  export GHAPP_PRIVATE_KEY_FILE
  bash "${MINT}" >/dev/null 2>/dev/null
) || T3_EXIT=$?

if [[ "${T3_EXIT}" -ne 0 ]]; then
  pass "exits non-zero when PEM file absent (exit=${T3_EXIT})"
else
  fail "expected non-zero exit when PEM absent, got 0"
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
printf 'Results: %d passed, %d failed\n' "${PASS}" "${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
