#!/usr/bin/env bash
# GENESIS_SEAL: 7c242080
#
# tools/check-diff/run.sh — Python↔Zig differential harness for the checker
# (Zig rewrite plan Task 10, slice 2 — FULL parity, no allowlist).
#
# Two mandatory steps, both must pass (exit 0):
#
#  1. PROBE — tools/check-diff/probe.vaked (slice-1 rule families) and
#     tools/check-diff/probe2.vaked (slice-2 families: caps/POLA, egress,
#     ref-resolution, workflow, determinism, ebpf, generics, repr rendering)
#     are checked by BOTH front-ends and the FULL JSON documents (messages +
#     spans + related + ordering) must be byte-identical. This
#     regression-locks message-string parity.
#  2. SWEEP — every vaked/examples/**/*.vaked runs through both front-ends;
#     each side's diagnostics are projected to sorted
#     `code:severity:line:col` rows, which must be identical per file
#     (positions + severity, not messages — the probes own message parity).
#     A file BOTH sides reject at parse time (exit 2) counts as agreement; a
#     one-sided parse failure, any exit code outside {0,1,2}
#     (panic/segfault), or unparseable JSON from either side is a hard
#     mismatch.
#
# Exit-code contract (both front-ends): 0 clean, 1 ANY diagnostic (warnings
# included), 2 lex/parse/IO error.
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

cd "$REPO" || exit 2

if [ ! -x "$VAKEDZ" ]; then
    echo "check-diff: vakedz binary not found at $VAKEDZ (zig build first)" >&2
    exit 2
fi

# Project a vakedc/vakedz --json document to sorted "code:severity:line:col"
# lines. Unparseable/empty JSON exits 3 — the caller treats that as a hard
# mismatch (a crashed producer must never look like "zero diagnostics").
project() { # $1 = json file
    "$PYTHON" - "$1" <<'EOF'
import json, sys
try:
    doc = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"project: unparseable JSON in {sys.argv[1]}: {e}", file=sys.stderr)
    sys.exit(3)
rows = []
for d in doc.get("diagnostics", []):
    s = d.get("span", {})
    rows.append(f'{d["code"]}:{d.get("severity")}:{s.get("line")}:{s.get("col")}')
for r in sorted(rows):
    print(r)
EOF
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mismatches=0

# ---------------------------------------------------------------------------
# Step 1 — PROBE: full-JSON parity on the committed multi-violation fixtures.
# Each probe carries a minimum diagnostic count (see the fixture headers) so
# a silently-empty comparison can never pass vacuously.
# ---------------------------------------------------------------------------
run_probe() { # $1 = fixture path, $2 = minimum diagnostic count
    local probe="$1" min="$2"
    "$PYTHON" -m vakedc check --json "$probe" >"$tmp/probe-py.json" 2>"$tmp/probe-py.err"
    local py_rc=$?
    "$VAKEDZ" check --json --builtins vaked/schema/builtins.vaked "$probe" \
        >"$tmp/probe-zig.json" 2>"$tmp/probe-zig.err"
    local zig_rc=$?
    if [ "$py_rc" -ne 1 ] || [ "$zig_rc" -ne 1 ]; then
        echo "MISMATCH (probe rc) $probe: expected rc=1 both sides," \
            "got python rc=$py_rc, vakedz rc=$zig_rc" >&2
        sed 's/^/  py:  /' "$tmp/probe-py.err" >&2
        sed 's/^/  zig: /' "$tmp/probe-zig.err" >&2
        mismatches=$((mismatches + 1))
        return
    fi
    if ! PROBE_MIN="$min" PROBE_NAME="$probe" "$PYTHON" - "$tmp/probe-py.json" "$tmp/probe-zig.json" <<'EOF'
import json, os, sys
min_count = int(os.environ["PROBE_MIN"])
name = os.environ["PROBE_NAME"]
try:
    py = json.load(open(sys.argv[1]))["diagnostics"]
    zg = json.load(open(sys.argv[2]))["diagnostics"]
except Exception as e:
    print(f"probe {name}: unparseable JSON: {e}", file=sys.stderr)
    sys.exit(1)
if len(py) < min_count:
    print(f"probe {name}: only {len(py)} python diagnostics (< {min_count}) — "
          f"fixture is broken", file=sys.stderr)
    sys.exit(1)
if py != zg:
    print(f"probe {name}: FULL-JSON divergence (py {len(py)} vs zig {len(zg)} diagnostics):",
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
print(f"probe {name}: {len(py)} diagnostics byte-identical (messages+spans+related+order)")
EOF
    then
        echo "MISMATCH (probe) $probe" >&2
        mismatches=$((mismatches + 1))
    fi
}

run_probe "tools/check-diff/probe.vaked" 13
run_probe "tools/check-diff/probe2.vaked" 28

# ---------------------------------------------------------------------------
# Step 2 — SWEEP: code:severity:line:col parity over every example.
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

    # exit codes must agree exactly (0 = clean, 1 = any diagnostic)
    if [ "$py_rc" -ne "$zig_rc" ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (rc) $f: python rc=$py_rc, vakedz rc=$zig_rc" >&2
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
        echo "MISMATCH $f (code:severity:line:col sets differ):" >&2
        sed 's/^/  /' "$tmp/rows.diff" >&2
    fi
done < <(find vaked/examples -name '*.vaked' | sort)

echo "check-diff: 2 probes + $total files, $mismatches mismatches" \
    "($parse_agree parse-rejected by both sides)"
[ "$mismatches" -eq 0 ] || exit 1
exit 0
