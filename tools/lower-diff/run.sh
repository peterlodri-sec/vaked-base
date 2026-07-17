#!/usr/bin/env bash
# GENESIS_SEAL: 7c242080
#
# tools/lower-diff/run.sh — Python↔Zig differential harness for the LOWERER
# (Zig rewrite plan, lower.zig): BYTE parity of the generated artifact tree.
#
# Sibling of tools/check-diff/run.sh and tools/emit-diff/run.sh (same
# hardening, deliberately a separate script so those frozen harnesses stay
# untouched). For every vaked/examples/**/*.vaked plus both check-diff probes:
#
#   python3 -m vakedc lower <f> --out <tmp/py>
#   vakedz          lower <f> --out <tmp/zig> --allow-partial
#
# and require ALL of:
#   * exit-code agreement — lower exits 0 (emitted) or 1 (read/parse error, or
#     the check gate refused); any rc > 1 on the PYTHON side is a crash and a
#     hard mismatch. vakedz rc 2 is a vakedz-only bucket (see below);
#   * a file BOTH sides reject (rc 1) counts as agreement, but NEITHER side
#     may have written any artifact (a crashed emitter must never look like
#     agreement);
#   * on rc 0: each compared artifact must EXIST on both sides, be NON-EMPTY,
#     and be byte-identical (cmp);
#   * a minimum file count, so a silently-empty sweep can never pass.
#
# ############################################################################
# # !!! SCOPED COMPARISON — THIS HARNESS IS NOT YET FULL-TREE PARITY !!!      #
# ############################################################################
#
# lower.zig is a STAGED port. Only the artifacts listed in ARTIFACTS below are
# ported and compared; every other file vakedc emits (gen/zig/*.json,
# gen/catalog/*.jsonl, gen/otp/*.erl, gen/nixos/*, gen/caddy/*, gen/eventd*,
# gen/trust*, gen/memory*, gen/workflow*, gen/ebpf*, gen/colmena/*, AND
# provenance.json — whose entry set is contributed to by every emitter) is
# NOT compared. A green run of this script therefore means:
#
#     "the ported artifacts are byte-identical"
#
# and NOT "vakedz lower reproduces vakedc lower". Do not quote it as the
# latter. Each future slice must ADD its artifact(s) to ARTIFACTS; when the
# port is complete, delete ARTIFACTS entirely and compare the two trees with a
# recursive `diff -r`, which is the only real parity gate. `provenance.json`
# is the LAST thing to land, because it is complete only when every emitter is.
#
# vakedz refuses (exit 2) to write a knowingly-incomplete tree, so this harness
# passes --allow-partial. That flag exists ONLY for this script.
#
# KNOWN vakedc DEFECT (reference-crash bucket): vakedc's parse/emit crashes
# with `TypeError: Object of type Literal is not JSON serializable` on any file
# whose schema has a `default =` / `oneof` field refinement — parser.py
# `_refinement` stores raw AST nodes and resolve.py `_field_to_props` never
# maps them through `_value_to_props`. `lower` shares the resolve path, so the
# same files are affected here. Being fixed concurrently; such files are
# counted in a separate `py_ref_crash` bucket, reported loudly, and NOT counted
# as parity mismatches. Fix the vakedc bug and this bucket must go to 0.
#
# Usage (ON dev-cx53 — never build/run on the developer machine):
#
#   rsync -a --delete --exclude .zig-cache --exclude zig-out \
#       build.zig build.zig.zon lib vakedz tools vaked vakedc tests \
#       dev-cx53:~/vaked-lower-verify/
#   ssh dev-cx53 'cd ~/vaked-lower-verify && zig build \
#       && bash tools/lower-diff/run.sh'
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

# ---- THE PORT GAP, IN ONE VARIABLE ---------------------------------------- #
# Artifacts lower.zig has ported. ONLY these are byte-compared. See the loud
# banner above before you trust a green run.
ARTIFACTS="flake.nix gen/RUNTIME.md"
# --------------------------------------------------------------------------- #

cd "$REPO" || exit 2

if [ ! -x "$VAKEDZ" ]; then
    echo "lower-diff: vakedz binary not found at $VAKEDZ (zig build first)" >&2
    exit 2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mismatches=0
total=0
gate_agree=0
compared=0
py_ref_crash=0
zig_unported=0

echo "lower-diff: SCOPED to artifacts: $ARTIFACTS (the port is staged — a green" \
    "run does NOT mean full-tree parity; see the header)" >&2

while IFS= read -r f; do
    total=$((total + 1))
    rm -rf "$tmp/py" "$tmp/zig"

    "$PYTHON" -m vakedc lower "$f" --out "$tmp/py" \
        >"$tmp/py.out" 2>"$tmp/py.err"
    py_rc=$?
    "$VAKEDZ" lower "$f" --out "$tmp/zig" --allow-partial \
        >"$tmp/zig.out" 2>"$tmp/zig.err"
    zig_rc=$?

    # python lower exits 0 or 1 (2 only for an unreadable/unparseable builtins
    # catalog, which would be a harness bug); anything else is a crash.
    if [ "$py_rc" -gt 1 ]; then
        # reference-crash bucket: vakedc's own resolver TypeErrors on default/
        # oneof refinements (see header) — nothing to compare against.
        if grep -q "TypeError: Object of type .* is not JSON serializable" "$tmp/py.err"; then
            py_ref_crash=$((py_ref_crash + 1))
            echo "PY-REFERENCE-CRASH $f: vakedc lower cannot serialize default/oneof" \
                "field refinements (known vakedc bug — not a vakedz parity failure)" >&2
            continue
        fi
        mismatches=$((mismatches + 1))
        echo "MISMATCH (python crash) $f: rc=$py_rc" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
        continue
    fi

    # vakedz rc 2 with --allow-partial means a real vakedz failure (a usage or
    # builtins error) — never the unported-target refusal, which --allow-partial
    # suppresses. Treat it as a hard mismatch.
    if [ "$zig_rc" -gt 1 ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (vakedz crash) $f: rc=$zig_rc" >&2
        sed 's/^/  zig: /' "$tmp/zig.err" >&2
        continue
    fi

    if [ "$py_rc" -ne "$zig_rc" ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (rc) $f: python rc=$py_rc, vakedz rc=$zig_rc" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
        sed 's/^/  zig: /' "$tmp/zig.err" >&2
        continue
    fi

    # rc 1 on both sides: read/parse error or the check gate refused — and a
    # refusing front-end must not have written ANY artifact ("nothing written").
    if [ "$py_rc" -eq 1 ]; then
        py_n=$(find "$tmp/py" -type f 2>/dev/null | wc -l)
        zig_n=$(find "$tmp/zig" -type f 2>/dev/null | wc -l)
        if [ "$py_n" -ne 0 ] || [ "$zig_n" -ne 0 ]; then
            mismatches=$((mismatches + 1))
            echo "MISMATCH (refuse+write) $f: rc=1 both sides but files were written" \
                "(py=$py_n, zig=$zig_n)" >&2
            continue
        fi
        gate_agree=$((gate_agree + 1))
        continue
    fi

    # rc 0: byte parity over the ported artifact list.
    if grep -q "INCOMPLETE lowering" "$tmp/zig.err"; then
        zig_unported=$((zig_unported + 1))
    fi

    bad=0
    for art in $ARTIFACTS; do
        pa="$tmp/py/$art"
        za="$tmp/zig/$art"
        # An artifact vakedc did not emit for this graph is not applicable —
        # but then vakedz must not have emitted it either.
        if [ ! -f "$pa" ] && [ ! -f "$za" ]; then
            continue
        fi
        if [ ! -f "$pa" ] || [ ! -f "$za" ]; then
            bad=1
            echo "MISMATCH (artifact presence) $f: $art py=$([ -f "$pa" ] && echo yes || echo no)," \
                "zig=$([ -f "$za" ] && echo yes || echo no)" >&2
            continue
        fi
        # Empty bytes are a broken emitter, never a pass.
        if [ ! -s "$pa" ] || [ ! -s "$za" ]; then
            bad=1
            echo "MISMATCH (empty artifact) $f: $art py=$(wc -c <"$pa"), zig=$(wc -c <"$za")" >&2
            continue
        fi
        if ! cmp -s "$pa" "$za"; then
            bad=1
            echo "MISMATCH (artifact bytes) $f: $art" >&2
            diff "$pa" "$za" | head -40 | sed 's/^/  /' >&2
            continue
        fi
        compared=$((compared + 1))
    done
    if [ "$bad" -ne 0 ]; then
        mismatches=$((mismatches + 1))
    fi
done < <({
    find vaked/examples -name '*.vaked'
    echo tools/check-diff/probe.vaked
    echo tools/check-diff/probe2.vaked
} | sort)

echo "lower-diff: $total files, $mismatches mismatches," \
    "$compared artifacts byte-compared" \
    "($gate_agree refused by both sides," \
    "$zig_unported partial vakedz trees," \
    "$py_ref_crash python-reference crashes excluded)"
echo "lower-diff: REMINDER — scoped to [$ARTIFACTS]; provenance.json and every" \
    "unported emitter's artifacts were NOT compared." >&2

if [ "$total" -lt "$MIN_FILES" ]; then
    echo "lower-diff: only $total files swept (< $MIN_FILES) — sweep is broken" >&2
    exit 1
fi
if [ "$compared" -eq 0 ]; then
    echo "lower-diff: 0 artifacts compared — the sweep proved nothing" >&2
    exit 1
fi
[ "$mismatches" -eq 0 ] || exit 1
exit 0
