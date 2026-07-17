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
#   * a minimum file count, so a silently-empty sweep can never pass.
#
# ############################################################################
# # TWO-TIER GATE — read this before quoting a green run.                     #
# ############################################################################
#
# lower.zig is a STAGED port, so on rc 0 a file lands in one of two tiers:
#
#  1. FULL-TREE (`full_tree` in the summary) — the graph selects ONLY ported
#     emitters, so vakedz wrote a COMPLETE tree and gets the TERMINAL GATE now:
#     recursive `diff -r` of the whole output, provenance.json included. This
#     is exactly the check the port's final commit applies to everything. For
#     these files, green DOES mean "vakedz lower reproduces vakedc lower".
#
#  2. SCOPED (`zig_unported`) — the graph selects an emitter that is not ported
#     yet, so vakedz's tree is knowingly incomplete and ONLY the artifacts in
#     ARTIFACTS below are compared. provenance.json is NOT compared for these
#     (every emitter contributes entries to it, so it is correct only once all
#     of them are). For these files, green means "the ported artifacts are
#     byte-identical" and NOT full parity. Do not quote it as the latter.
#
# Each slice ADDS its artifact(s) to ARTIFACTS and moves files from tier 2 to
# tier 1 as their emitters land. The port is complete when tier 2 is empty; at
# that point ARTIFACTS, --allow-partial, and LowerResult.unported_targets all
# get deleted together and every file is gated by `diff -r`.
#
# vakedz refuses (exit 2) to write a knowingly-incomplete tree, so this harness
# passes --allow-partial. That flag exists ONLY for this script, and is inert
# for tier-1 files.
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

# ---- THE PORT GAP, IN ONE VARIABLE ---------------------------------------- #
# Artifacts lower.zig has ported. ONLY these are byte-compared. See the loud
# banner above before you trust a green run.
ARTIFACTS="flake.nix gen/RUNTIME.md gen/zig gen/catalog gen/otp gen/nixos gen/caddy"
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
full_tree=0

echo "lower-diff: files whose graph selects only PORTED emitters get the terminal" \
    "full-tree 'diff -r' gate (provenance.json included). The rest are SCOPED to:" \
    "$ARTIFACTS — for those, a green run does NOT mean full-tree parity." >&2

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

    # rc 0: byte parity.
    #
    # A graph that selects ONLY ported emitters lowers to a COMPLETE tree, so
    # it gets the TERMINAL GATE right now: a recursive diff of the whole
    # output, provenance.json included. This is the same check the port's final
    # commit will apply to every file; applying it per-file as slices land
    # means each newly-completed fixture is fully gated immediately, and
    # provenance.json (whose entry set every emitter contributes to) is
    # exercised long before the last slice.
    if ! grep -q "INCOMPLETE lowering" "$tmp/zig.err"; then
        if ! diff -r "$tmp/py" "$tmp/zig" >/dev/null 2>&1; then
            mismatches=$((mismatches + 1))
            echo "MISMATCH (full tree) $f: complete lowering differs from vakedc" >&2
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
        continue
    fi
    zig_unported=$((zig_unported + 1))

    bad=0
    for art in $ARTIFACTS; do
        pa="$tmp/py/$art"
        za="$tmp/zig/$art"
        # An artifact vakedc did not emit for this graph is not applicable —
        # but then vakedz must not have emitted it either.
        if [ ! -e "$pa" ] && [ ! -e "$za" ]; then
            continue
        fi
        if [ ! -e "$pa" ] || [ ! -e "$za" ]; then
            bad=1
            echo "MISMATCH (artifact presence) $f: $art py=$([ -e "$pa" ] && echo yes || echo no)," \
                "zig=$([ -e "$za" ] && echo yes || echo no)" >&2
            continue
        fi

        # An ARTIFACTS entry may name a DIRECTORY of per-decl artifacts
        # (gen/zig/<fiber>.json). Compare it recursively — never skip it, or a
        # whole emitter's output would silently escape the sweep.
        if [ -d "$pa" ] || [ -d "$za" ]; then
            if [ ! -d "$pa" ] || [ ! -d "$za" ]; then
                bad=1
                echo "MISMATCH (file/dir kind) $f: $art" >&2
                continue
            fi
            n=$(find "$pa" -type f | wc -l)
            if [ "$n" -eq 0 ]; then
                bad=1
                echo "MISMATCH (empty artifact dir) $f: $art emitted no files" >&2
                continue
            fi
            if find "$pa" "$za" -type f -empty | grep -q .; then
                bad=1
                echo "MISMATCH (empty artifact in dir) $f: $art" >&2
                continue
            fi
            if ! diff -r "$pa" "$za" >/dev/null 2>&1; then
                bad=1
                echo "MISMATCH (artifact dir) $f: $art" >&2
                diff -r "$pa" "$za" 2>&1 | head -40 | sed 's/^/  /' >&2
                continue
            fi
            compared=$((compared + n))
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
    "($full_tree FULL-TREE diff -r gated," \
    "$gate_agree refused by both sides," \
    "$zig_unported partial vakedz trees scoped to ARTIFACTS," \
    "$py_ref_crash python-reference crashes excluded)"
if [ "$zig_unported" -gt 0 ]; then
    echo "lower-diff: REMINDER — $zig_unported file(s) still scoped to [$ARTIFACTS];" \
        "for those, provenance.json and every unported emitter's artifacts were" \
        "NOT compared. Only the $full_tree full-tree file(s) are truly gated." >&2
fi

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
