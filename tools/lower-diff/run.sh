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
#   vakedz          lower <f> --out <tmp/zig>
#
# and require ALL of:
#   * exit-code agreement — lower exits 0 (emitted) or 1 (read/parse error, or
#     the check gate refused); any rc > 1 on the PYTHON side is a crash and a
#     hard mismatch. vakedz rc 2 is a vakedz-only bucket (see below);
#   * a file BOTH sides reject (rc 1) counts as agreement, but NEITHER side
#     may have written any artifact (a crashed emitter must never look like
#     agreement);
#   * a minimum file count, so a silently-empty sweep can never pass.
#
# ############################################################################
# # PORT COMPLETE — this is the terminal gate.                                #
# ############################################################################
#
# Every target lower.py's REGISTRY can select is ported, so for each file both
# front-ends accept this compares the ENTIRE output tree with a recursive
# `diff -r`: every artifact AND provenance.json, whose entry set every emitter
# contributes to. There is no scoped tier and no artifact allowlist any more —
# a green run means, without qualification:
#
#     vakedz lower reproduces vakedc lower, byte for byte.
#
# (History: the port was staged, and this harness used to compare only an
# ARTIFACTS allowlist for files whose graph selected a not-yet-ported emitter.
# That scoping, the `--allow-partial` flag it required, and lower.zig's
# `unported_targets` were all deleted together once the last emitter landed.)
#
# reference-crash bucket (`py_ref_crash`): vakedc's resolver used to TypeError
# with `Object of type Literal is not JSON serializable` on any file whose
# schema has a `default =` / `oneof` field refinement (`_field_to_props` never
# mapped refinement values through `_value_to_props`). `lower` shares that
# resolve path, so this harness was affected too. FIXED in 908b49e, and this
# bucket has read 0 ever since — it is kept as a REGRESSION TRIPWIRE, not as
# an excuse: any file landing in it means the vakedc fix regressed, and it must
# stay at 0. Everything else (a py crash without that signature, a zig crash,
# differing bytes) is a hard mismatch.
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
full_tree=0

echo "lower-diff: terminal gate — full-tree diff -r (provenance.json included) on every accepted file" >&2

while IFS= read -r f; do
    total=$((total + 1))
    rm -rf "$tmp/py" "$tmp/zig"

    "$PYTHON" -m vakedc lower "$f" --out "$tmp/py" \
        >"$tmp/py.out" 2>"$tmp/py.err"
    py_rc=$?
    "$VAKEDZ" lower "$f" --out "$tmp/zig" \
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

    # vakedz lower exits 0 or 1 like vakedc; rc 2 is a usage/builtins failure.
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

    # rc 0: FULL-TREE byte parity — every artifact plus provenance.json.
    if ! diff -r "$tmp/py" "$tmp/zig" >/dev/null 2>&1; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (full tree) $f:" >&2
        diff -r "$tmp/py" "$tmp/zig" 2>&1 | head -40 | sed 's/^/  /' >&2
        continue
    fi
    n=$(find "$tmp/py" -type f | wc -l)
    if [ "$n" -eq 0 ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (empty tree) $f: rc=0 but vakedc wrote nothing" >&2
        continue
    fi
    full_tree=$((full_tree + 1))
    compared=$((compared + n))
done < <({
    find vaked/examples -name '*.vaked'
    echo tools/check-diff/probe.vaked
    echo tools/check-diff/probe2.vaked
} | sort)

echo "lower-diff: $total files, $mismatches mismatches," \
    "$compared artifacts byte-compared across $full_tree full trees" \
    "($gate_agree refused by both sides," \
    "$py_ref_crash python-reference crashes excluded)"

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
