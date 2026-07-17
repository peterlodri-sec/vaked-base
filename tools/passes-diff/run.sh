#!/usr/bin/env bash
# GENESIS_SEAL: 7c242080
#
# tools/passes-diff/run.sh — Python↔Zig differential harness for the pass
# pipeline (topology → WAL → AOT): BYTE parity of `passes --json`.
#
# Sibling of tools/check-diff/run.sh and tools/emit-diff/run.sh (same
# hardening, deliberately a separate script so those frozen harnesses stay
# untouched). For every tests/corpus/0024-differential/fixtures/*.vaked plus
# every vaked/examples/**/*.vaked, run
#
#   python3 -m vakedc passes --json <f>
#   vakedz           passes --json <f>
#
# and require ALL of:
#   * exit-code agreement — `passes` exits 0 (clean) or 1 (any diagnostic, OR
#     a read/lex/parse error: `_cmd_passes` returns 1 for both, unlike
#     `check`'s 2). Any rc > 1 on either side is a crash and a hard mismatch;
#   * a file BOTH sides reject at parse time (rc 1, EMPTY stdout) counts as
#     agreement — but a rc-1 file with output on one side only is a hard
#     mismatch (a crashed producer must never look like agreement);
#   * on any rc with output: stdout must be non-empty, PARSEABLE JSON on both
#     sides (unparseable/empty JSON from either side is a hard mismatch — this
#     is what stops a segfaulted producer from "agreeing" vacuously), and
#     byte-identical (cmp);
#   * a minimum file count, so a silently-empty sweep can never pass.
#
# NO SCOPING, NO ALLOWLIST, NO SEED PIN. Every byte of every document on every
# file is compared under the AMBIENT PYTHONHASHSEED.
#
# HISTORY (why you might expect a knob here): vakedc's cycle diagnostic used to
# be hash-seed dependent — pass01_topology.py iterated the DFS roots over the
# `step_names` SET, so the reported ROTATION of a cycle changed run-to-run and
# vakedc disagreed with ITSELF (all three rotations of cyclic.vaked were
# reachable across seeds). This harness briefly carried a PYTHONHASHSEED pin and
# a CYCLE_ROTATION_TOLERANT bucket to work around that. The bug is FIXED
# (pass01_topology.py now iterates `steps`, declaration order) and BOTH were
# removed: while a pin is in place, any future rotation-class bug in that path is
# invisible to CI. The fix is regression-locked by
# tests/spec/test_vakedc_passes.py, which asserts the exact cycle message under
# several PYTHONHASHSEEDs. If a rotation difference EVER reappears here, it is a
# real regression — fix it, do not re-introduce a tolerance.
#
# Usage (ON dev-cx53 — never build/run on the developer machine):
#
#   rsync -a --delete --exclude .zig-cache --exclude zig-out \
#       build.zig build.zig.zon lib vakedz tools vaked vakedc tests \
#       dev-cx53:~/vaked-passes-verify/
#   ssh dev-cx53 'cd ~/vaked-passes-verify && zig build \
#       && bash tools/passes-diff/run.sh'
#
# Environment:
#   VAKEDZ  path to the vakedz binary   (default: ./zig-out/bin/vakedz)
#   PYTHON  python interpreter          (default: python3)
#   REPO    tree containing vaked/ + vakedc/ (default: .)
set -u

REPO="${REPO:-.}"
VAKEDZ="${VAKEDZ:-$REPO/zig-out/bin/vakedz}"
PYTHON="${PYTHON:-python3}"

MIN_FILES=62 # 56 examples + 6 corpus fixtures; find fewer and the sweep is broken

cd "$REPO" || exit 2

if [ ! -x "$VAKEDZ" ]; then
    echo "passes-diff: vakedz binary not found at $VAKEDZ (zig build first)" >&2
    exit 2
fi

# Exit 3 (hard mismatch for the caller) on empty/unparseable JSON: a crashed
# producer must never be mistaken for "no workflows, no diagnostics".
validate() { # $1 = json file, $2 = label
    "$PYTHON" - "$1" "$2" <<'EOF'
import json, sys
path, label = sys.argv[1], sys.argv[2]
try:
    with open(path) as fh:
        text = fh.read()
except OSError as e:
    print(f"validate: cannot read {label} output: {e}", file=sys.stderr)
    sys.exit(3)
if not text.strip():
    print(f"validate: {label} produced EMPTY output", file=sys.stderr)
    sys.exit(3)
try:
    doc = json.loads(text)
except Exception as e:
    print(f"validate: {label} produced unparseable JSON: {e}", file=sys.stderr)
    sys.exit(3)
for key in ("workflows", "diagnostics", "artifacts", "status"):
    if key not in doc:
        print(f"validate: {label} JSON is missing required key {key!r}",
              file=sys.stderr)
        sys.exit(3)
EOF
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mismatches=0
total=0
parse_agree=0

while IFS= read -r f; do
    total=$((total + 1))

    "$PYTHON" -m vakedc passes --json "$f" >"$tmp/py.json" 2>"$tmp/py.err"
    py_rc=$?
    "$VAKEDZ" passes --json "$f" >"$tmp/zig.json" 2>"$tmp/zig.err"
    zig_rc=$?

    # anything outside {0,1} is a crash (panic/segfault) — hard mismatch
    if [ "$py_rc" -gt 1 ] || [ "$zig_rc" -gt 1 ]; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (crash) $f: python rc=$py_rc, vakedz rc=$zig_rc" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
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

    # rc=1 with NO output on both sides = a read/lex/parse rejection both sides
    # agree on. One-sided emptiness falls through to validate() below and is a
    # hard mismatch there.
    if [ "$py_rc" -eq 1 ] && [ ! -s "$tmp/py.json" ] && [ ! -s "$tmp/zig.json" ]; then
        parse_agree=$((parse_agree + 1))
        continue
    fi

    if ! validate "$tmp/py.json" "python"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (bad python JSON) $f" >&2
        sed 's/^/  py:  /' "$tmp/py.err" >&2
        continue
    fi
    if ! validate "$tmp/zig.json" "vakedz"; then
        mismatches=$((mismatches + 1))
        echo "MISMATCH (bad vakedz JSON) $f" >&2
        sed 's/^/  zig: /' "$tmp/zig.err" >&2
        continue
    fi

    if cmp -s "$tmp/py.json" "$tmp/zig.json"; then
        continue
    fi

    mismatches=$((mismatches + 1))
    echo "MISMATCH $f (passes --json bytes differ):" >&2
    diff -u "$tmp/py.json" "$tmp/zig.json" | sed 's/^/  /' >&2
done < <(find tests/corpus/0024-differential/fixtures vaked/examples \
    -name '*.vaked' | sort)

if [ "$total" -lt "$MIN_FILES" ]; then
    echo "passes-diff: only $total files swept (< $MIN_FILES) — sweep is broken" >&2
    exit 1
fi

echo "passes-diff: $total files, $mismatches mismatches" \
    "($parse_agree parse-rejected by both sides)"
[ "$mismatches" -eq 0 ] || exit 1
exit 0
