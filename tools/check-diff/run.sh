#!/usr/bin/env bash
# GENESIS_SEAL: 7c242080
#
# tools/check-diff/run.sh — Python↔Zig differential harness for the checker
# (Zig rewrite plan Task 10, slice 1).
#
# For every vaked/examples/**/*.vaked it runs BOTH front-ends:
#
#     python3 -m vakedc check --json <file>
#     <vakedz> check --json --builtins vaked/schema/builtins.vaked <file>
#
# filters BOTH diagnostic sets to the allowlist of codes implemented by the
# slice-1 check.zig port (see ALLOWLIST below — slice 2 extends it until it is
# removed entirely), projects each surviving diagnostic to
# `code:line:col` (positions, not messages — message-string parity is asserted
# separately by vakedz unit tests for the golden fixtures), sorts, and diffs.
# A file where BOTH sides fail to parse (exit 2) counts as agreement; a
# one-sided parse failure is a mismatch. Zero mismatches = exit 0.
#
# Usage (ON dev-cx53 — never build/run on the developer machine):
#
#   # one-time sync of both trees from the dev machine:
#   rsync -a --delete --exclude .zig-cache --exclude zig-out \
#       build.zig build.zig.zon lib vakedz tools vaked vakedc \
#       dev-cx53:~/vaked-ws-verify/
#   ssh dev-cx53 'cd ~/vaked-ws-verify && zig build \
#       && bash tools/check-diff/run.sh'
#
# Environment:
#   VAKEDZ  path to the vakedz binary   (default: ./zig-out/bin/vakedz)
#   PYTHON  python interpreter          (default: python3)
#   REPO    tree containing vaked/ + vakedc/ (default: .)
#
set -u

REPO="${REPO:-.}"
VAKEDZ="${VAKEDZ:-$REPO/zig-out/bin/vakedz}"
PYTHON="${PYTHON:-python3}"

# ---------------------------------------------------------------------------
# Slice-1 allowlist — the diagnostic codes check.zig implements today.
# Conformance + constraints + load-time well-formedness + collisions.
# Slice 2 adds: E-CAP-USE/UNKNOWN-*/ATTENUATION, W-POLA-EXCESS,
# W-CONFUSED-DEPUTY, E-EGRESS-USE, W-EGRESS-UNREFINED, E-REF-UNRESOLVED,
# E-WORKFLOW-*, E-DETERMINISM-EFFECT, E-EBPF-*, E-GENERIC-INCONSISTENT.
# ---------------------------------------------------------------------------
ALLOWLIST="E-CONFORM-MISSING-FIELD E-CONFORM-UNKNOWN-FIELD E-CONFORM-TYPE \
E-CONSTRAINT-NONEMPTY E-CONSTRAINT-ONEOF E-CONSTRAINT-RANGE E-CONSTRAINT-MATCHES \
E-SCHEMA-REFINEMENT E-SCHEMA-BAD-REGEX E-SCHEMA-BAD-ONEOF E-SCHEMA-BAD-RANGE \
E-SCHEMA-BAD-DEFAULT E-CAP-ORDER-DANGLING E-CAP-ORDER-CYCLE E-DECL-NAME-COLLISION"

cd "$REPO" || exit 2

if [ ! -x "$VAKEDZ" ]; then
    echo "check-diff: vakedz binary not found at $VAKEDZ (zig build first)" >&2
    exit 2
fi

# Project a vakedc/vakedz --json document to sorted "code:line:col" lines,
# keeping only allowlisted codes.
project() { # $1 = json file
    ALLOWLIST="$ALLOWLIST" "$PYTHON" - "$1" <<'EOF'
import json, os, sys
allow = set(os.environ["ALLOWLIST"].split())
try:
    doc = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
rows = []
for d in doc.get("diagnostics", []):
    if d.get("code") in allow:
        s = d.get("span", {})
        rows.append(f'{d["code"]}:{s.get("line")}:{s.get("col")}')
for r in sorted(rows):
    print(r)
EOF
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

total=0
mismatches=0
parse_agree=0

while IFS= read -r f; do
    total=$((total + 1))

    "$PYTHON" -m vakedc check --json "$f" >"$tmp/py.json" 2>"$tmp/py.err"
    py_rc=$?
    "$VAKEDZ" check --json --builtins vaked/schema/builtins.vaked "$f" \
        >"$tmp/zig.json" 2>"$tmp/zig.err"
    zig_rc=$?

    # exit 2 = lex/parse (or read) failure on that side
    if [ "$py_rc" -eq 2 ] || [ "$zig_rc" -eq 2 ]; then
        if [ "$py_rc" -eq 2 ] && [ "$zig_rc" -eq 2 ]; then
            parse_agree=$((parse_agree + 1))
            continue
        fi
        mismatches=$((mismatches + 1))
        echo "MISMATCH (parse) $f: python rc=$py_rc, vakedz rc=$zig_rc" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
        sed 's/^/  zig: /' "$tmp/zig.err" >&2
        continue
    fi

    project "$tmp/py.json" >"$tmp/py.rows"
    project "$tmp/zig.json" >"$tmp/zig.rows"

    if ! diff -u "$tmp/py.rows" "$tmp/zig.rows" >"$tmp/rows.diff"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH $f (allowlisted code:line:col sets differ):" >&2
        sed 's/^/  /' "$tmp/rows.diff" >&2
    fi
done < <(find vaked/examples -name '*.vaked' | sort)

echo "check-diff: $total files, $mismatches mismatches" \
    "($parse_agree parse-rejected by both sides)"
[ "$mismatches" -eq 0 ] || exit 1
exit 0
