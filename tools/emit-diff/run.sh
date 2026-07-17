#!/usr/bin/env bash
# GENESIS_SEAL: 7c242080
#
# tools/emit-diff/run.sh — Python↔Zig differential harness for the emitter
# (Zig rewrite plan Task 11): BYTE parity of the canonical graph JSON.
#
# Sibling of tools/check-diff/run.sh (same hardening, deliberately a separate
# script so the frozen check harness stays untouched). For every
# vaked/examples/**/*.vaked plus both check-diff probes, run
#
#   python3 -m vakedc parse <f> --json <tmp/py.graph.json>  --print
#   vakedz          parse <f> --json <tmp/zig.graph.json> --print
#
# and require ALL of:
#   * exit-code agreement — the parse command exits 0 (emitted) or
#     1 (read/lex/parse error); any rc > 1 on either side is a crash and a
#     hard mismatch;
#   * a file BOTH sides reject (rc 1) counts as agreement, but both stdouts
#     must be EMPTY (a crashed writer must never look like agreement);
#   * on rc 0: stdout non-empty on both sides (empty output is a hard
#     mismatch), stdout byte-identical (cmp), and the two --json files
#     byte-identical;
#   * a minimum file count, so a silently-empty sweep can never pass.
#
# SQLite (vakedc's graph.db) is NOT compared: deferred in vakedz (no SQLite
# in the Zig stdlib; see vakedz/src/emit.zig `sqlite_deferred`).
#
# KNOWN vakedc DEFECT (reference-crash bucket): vakedc's parse crashes with
# `TypeError: Object of type Literal is not JSON serializable` on any file
# whose schema has a `default =` / `oneof` field refinement —
# parser.py `_refinement` stores raw AST nodes and resolve.py
# `_field_to_props` never maps them through `_value_to_props`, so
# emit.py json.dumps raises (rc 1, EMPTY stdout, traceback). The Python
# reference produces no bytes to compare against. Such files are counted in
# a separate `py_ref_crash` bucket — detected by the exact TypeError
# signature, with the vakedz output still required to be non-empty valid
# JSON — reported loudly, and NOT counted as parity mismatches. Everything
# else (a py crash without that signature, a zig crash, differing bytes)
# stays a hard mismatch. Fix the vakedc bug and this bucket must go to 0.
#
# Usage (ON dev-cx53 — never build/run on the developer machine):
#
#   rsync -a --delete --exclude .zig-cache --exclude zig-out \
#       build.zig build.zig.zon lib vakedz tools vaked vakedc \
#       dev-cx53:~/vaked-ws-verify/
#   ssh dev-cx53 'cd ~/vaked-ws-verify && zig build \
#       && bash tools/emit-diff/run.sh'
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
MIN_FILES=58 # 56 examples + 2 probes; find fewer and the sweep is broken

cd "$REPO" || exit 2

if [ ! -x "$VAKEDZ" ]; then
    echo "emit-diff: vakedz binary not found at $VAKEDZ (zig build first)" >&2
    exit 2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mismatches=0
total=0
parse_agree=0
py_ref_crash=0

while IFS= read -r f; do
    total=$((total + 1))

    "$PYTHON" -m vakedc parse "$f" --json "$tmp/py.graph.json" --print \
        >"$tmp/py.out" 2>"$tmp/py.err"
    py_rc=$?
    "$VAKEDZ" parse "$f" --json "$tmp/zig.graph.json" --print \
        >"$tmp/zig.out" 2>"$tmp/zig.err"
    zig_rc=$?

    # parse exits 0 or 1; anything above is a crash/usage bug — hard mismatch
    if [ "$py_rc" -gt 1 ] || [ "$zig_rc" -gt 1 ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (crash) $f: python rc=$py_rc, vakedz rc=$zig_rc" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
        sed 's/^/  zig: /' "$tmp/zig.err" >&2
        continue
    fi

    # reference-crash bucket: vakedc's own emitter TypeErrors on default/
    # oneof refinements (see header) — nothing to compare against. Require
    # the exact signature, an empty python stdout, and non-empty VALID JSON
    # from vakedz; anything else falls through to a hard mismatch.
    if [ "$py_rc" -eq 1 ] && [ "$zig_rc" -eq 0 ] && [ ! -s "$tmp/py.out" ] \
        && grep -q "TypeError: Object of type .* is not JSON serializable" "$tmp/py.err" \
        && [ -s "$tmp/zig.out" ] \
        && "$PYTHON" -c 'import json,sys; json.load(open(sys.argv[1]))' "$tmp/zig.out" 2>/dev/null; then
        py_ref_crash=$((py_ref_crash + 1))
        echo "PY-REFERENCE-CRASH $f: vakedc parse cannot serialize default/oneof" \
            "field refinements (known vakedc bug — not a vakedz parity failure;" \
            "vakedz output verified as valid JSON)" >&2
        continue
    fi

    if [ "$py_rc" -ne "$zig_rc" ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (rc) $f: python rc=$py_rc, vakedz rc=$zig_rc" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
        sed 's/^/  zig: /' "$tmp/zig.err" >&2
        continue
    fi

    # rc 1 on both sides: lex/parse rejection agreement — but a rejecting
    # front-end must not have produced graph bytes
    if [ "$py_rc" -eq 1 ]; then
        if [ -s "$tmp/py.out" ] || [ -s "$tmp/zig.out" ]; then
            mismatches=$((mismatches + 1))
            echo "MISMATCH (reject+output) $f: rc=1 both sides but stdout not empty" >&2
            continue
        fi
        parse_agree=$((parse_agree + 1))
        continue
    fi

    # rc 0: byte parity. Empty stdout means a broken emitter, never a pass.
    if [ ! -s "$tmp/py.out" ] || [ ! -s "$tmp/zig.out" ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (empty output) $f: python bytes=$(wc -c <"$tmp/py.out"), vakedz bytes=$(wc -c <"$tmp/zig.out")" >&2
        continue
    fi
    if ! cmp -s "$tmp/py.out" "$tmp/zig.out"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (stdout bytes) $f:" >&2
        cmp "$tmp/py.out" "$tmp/zig.out" 2>&1 | sed 's/^/  /' >&2
        diff <(head -c 400 "$tmp/py.out") <(head -c 400 "$tmp/zig.out") | sed 's/^/  /' >&2
        continue
    fi
    if ! cmp -s "$tmp/py.graph.json" "$tmp/zig.graph.json"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (--json file bytes) $f" >&2
        continue
    fi
done < <({
    find vaked/examples -name '*.vaked'
    echo tools/check-diff/probe.vaked
    echo tools/check-diff/probe2.vaked
} | sort)

echo "emit-diff: $total files, $mismatches mismatches" \
    "($parse_agree parse-rejected by both sides," \
    "$py_ref_crash python-reference crashes excluded)"

if [ "$total" -lt "$MIN_FILES" ]; then
    echo "emit-diff: only $total files swept (< $MIN_FILES) — sweep is broken" >&2
    exit 1
fi
[ "$mismatches" -eq 0 ] || exit 1
exit 0
