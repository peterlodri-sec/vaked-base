#!/usr/bin/env bash
# GENESIS_SEAL: 7c242080
#
# tools/check-diff/run.sh — Python↔Zig differential harness for the checker
# (Zig rewrite plan Task 10, slice 1).
#
# Two mandatory steps, both must pass (exit 0):
#
#  1. PROBE — tools/check-diff/probe.vaked (a fixture triggering every
#     slice-1 rule family) is checked by BOTH front-ends and the FULL JSON
#     documents (messages + spans + related + ordering) must be identical
#     after filtering the Python side to the allowlist. This regression-locks
#     message-string parity.
#  2. SWEEP — every vaked/examples/**/*.vaked runs through both front-ends;
#     each side's diagnostics are filtered to the allowlist and projected to
#     sorted `code:line:col` rows, which must be identical per file
#     (positions, not messages — the probe owns message parity). A file BOTH
#     sides reject at parse time (exit 2) counts as agreement; a one-sided
#     parse failure, any exit code outside {0,1,2} (panic/segfault), or
#     unparseable JSON from either side is a hard mismatch.
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
export ALLOWLIST

# Minimum diagnostic count the probe must produce (see probe.vaked header) —
# guards against a silently-empty comparison passing vacuously.
PROBE_MIN=13

cd "$REPO" || exit 2

if [ ! -x "$VAKEDZ" ]; then
    echo "check-diff: vakedz binary not found at $VAKEDZ (zig build first)" >&2
    exit 2
fi

# Project a vakedc/vakedz --json document to sorted "code:line:col" lines,
# keeping only allowlisted codes. Unparseable/empty JSON exits 3 — the caller
# treats that as a hard mismatch (a crashed producer must never look like
# "zero diagnostics").
project() { # $1 = json file
    "$PYTHON" - "$1" <<'EOF'
import json, os, sys
allow = set(os.environ["ALLOWLIST"].split())
try:
    doc = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"project: unparseable JSON in {sys.argv[1]}: {e}", file=sys.stderr)
    sys.exit(3)
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

mismatches=0

# ---------------------------------------------------------------------------
# Step 1 — PROBE: full-JSON parity on the committed multi-violation fixture.
# ---------------------------------------------------------------------------
probe="tools/check-diff/probe.vaked"
"$PYTHON" -m vakedc check --json "$probe" >"$tmp/probe-py.json" 2>"$tmp/probe-py.err"
py_rc=$?
"$VAKEDZ" check --json --builtins vaked/schema/builtins.vaked "$probe" \
    >"$tmp/probe-zig.json" 2>"$tmp/probe-zig.err"
zig_rc=$?
if [ "$py_rc" -ne 1 ] || [ "$zig_rc" -ne 1 ]; then
    echo "MISMATCH (probe rc) $probe: expected rc=1 both sides," \
        "got python rc=$py_rc, vakedz rc=$zig_rc" >&2
    sed 's/^/  py:  /' "$tmp/probe-py.err" >&2
    sed 's/^/  zig: /' "$tmp/probe-zig.err" >&2
    mismatches=$((mismatches + 1))
elif ! PROBE_MIN="$PROBE_MIN" "$PYTHON" - "$tmp/probe-py.json" "$tmp/probe-zig.json" <<'EOF'
import json, os, sys
allow = set(os.environ["ALLOWLIST"].split())
min_count = int(os.environ["PROBE_MIN"])
try:
    py = [d for d in json.load(open(sys.argv[1]))["diagnostics"] if d["code"] in allow]
    zg = json.load(open(sys.argv[2]))["diagnostics"]
except Exception as e:
    print(f"probe: unparseable JSON: {e}", file=sys.stderr)
    sys.exit(1)
if len(py) < min_count:
    print(f"probe: only {len(py)} allowlisted python diagnostics (< {min_count}) — "
          f"fixture or filter is broken", file=sys.stderr)
    sys.exit(1)
if py != zg:
    print(f"probe: FULL-JSON divergence (py {len(py)} vs zig {len(zg)} diagnostics):",
          file=sys.stderr)
    for i, (p, z) in enumerate(zip(py, zg)):
        if p != z:
            for k in sorted(set(p) | set(z)):
                if p.get(k) != z.get(k):
                    print(f"  [{i}] {p.get('code')} field {k}:", file=sys.stderr)
                    print(f"    py : {p.get(k)!r}", file=sys.stderr)
                    print(f"    zig: {z.get(k)!r}", file=sys.stderr)
    if len(py) != len(zg):
        print(f"  py-only codes : {[d['code'] for d in py[len(zg):]]}", file=sys.stderr)
        print(f"  zig-only codes: {[d['code'] for d in zg[len(py):]]}", file=sys.stderr)
    sys.exit(1)
print(f"probe: {len(py)} diagnostics byte-identical (messages+spans+related+order)")
EOF
then
    echo "MISMATCH (probe) $probe" >&2
    mismatches=$((mismatches + 1))
fi

# ---------------------------------------------------------------------------
# Step 2 — SWEEP: code:line:col parity over every example.
# ---------------------------------------------------------------------------
total=0
parse_agree=0

while IFS= read -r f; do
    total=$((total + 1))

    "$PYTHON" -m vakedc check --json "$f" >"$tmp/py.json" 2>"$tmp/py.err"
    py_rc=$?
    "$VAKEDZ" check --json --builtins vaked/schema/builtins.vaked "$f" \
        >"$tmp/zig.json" 2>"$tmp/zig.err"
    zig_rc=$?

    # anything outside {0,1,2} is a crash (panic/segfault) — hard mismatch
    if [ "$py_rc" -gt 2 ] || [ "$zig_rc" -gt 2 ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (crash) $f: python rc=$py_rc, vakedz rc=$zig_rc" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
        sed 's/^/  zig: /' "$tmp/zig.err" >&2
        continue
    fi

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

    if ! project "$tmp/py.json" >"$tmp/py.rows"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (bad python JSON) $f" >&2
        continue
    fi
    if ! project "$tmp/zig.json" >"$tmp/zig.rows"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (bad vakedz JSON) $f" >&2
        continue
    fi

    if ! diff -u "$tmp/py.rows" "$tmp/zig.rows" >"$tmp/rows.diff"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH $f (allowlisted code:line:col sets differ):" >&2
        sed 's/^/  /' "$tmp/rows.diff" >&2
    fi
done < <(find vaked/examples -name '*.vaked' | sort)

echo "check-diff: probe + $total files, $mismatches mismatches" \
    "($parse_agree parse-rejected by both sides)"
[ "$mismatches" -eq 0 ] || exit 1
exit 0
