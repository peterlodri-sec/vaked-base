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
# ---------------------------------------------------------------------------
# CYCLE_ROTATION_TOLERANT — the one scoping knob (default: 1)
# ---------------------------------------------------------------------------
# vakedc's cycle diagnostic is NOT REPRODUCIBLE. pass01_topology.py:58 iterates
# the cycle-detection DFS roots with `for root in step_names`, where
# `step_names` is a **set** — Python's set iteration order for strings depends
# on PYTHONHASHSEED, so vakedc reports an arbitrary ROTATION of the true cycle
# and disagrees with ITSELF between runs. Measured on cyclic.vaked, all three
# rotations occur across 12 seeds:
#
#     PYTHONHASHSEED=3 -> "cycle: A -> B -> C -> A"
#     PYTHONHASHSEED=0 -> "cycle: B -> C -> A -> B"
#     PYTHONHASHSEED=1 -> "cycle: C -> A -> B -> C"
#
# There is therefore no single Python behaviour to be byte-compatible WITH.
# vakedz iterates roots in `steps` declaration order (deterministic). With
# CYCLE_ROTATION_TOLERANT=1 this harness pins PYTHONHASHSEED=3 — the seed whose
# rotation IS declaration order — so the comparison stays a true BYTE compare
# on every file, including the cyclic ones. Nothing is excluded or normalised:
# every byte of every document is still compared.
#
# Set CYCLE_ROTATION_TOLERANT=0 to run with the ambient PYTHONHASHSEED instead.
# Files whose ONLY difference is a rotation of the cycle name list are then
# reported in a separate `cycle_rotation` bucket rather than as mismatches; any
# other difference stays a hard mismatch. Expect that bucket to be nonzero
# roughly 2/3 of the time — that is the vakedc bug, not a vakedz regression.
#
# FIX THE vakedc BUG (iterate `steps`, not the `step_names` set) and this whole
# knob can be deleted: pin it to 0, watch `cycle_rotation` stay 0, then remove.
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
#   VAKEDZ                   path to the vakedz binary (default: ./zig-out/bin/vakedz)
#   PYTHON                   python interpreter        (default: python3)
#   REPO                     tree containing vaked/ + vakedc/ (default: .)
#   CYCLE_ROTATION_TOLERANT  see above                 (default: 1)
set -u

REPO="${REPO:-.}"
VAKEDZ="${VAKEDZ:-$REPO/zig-out/bin/vakedz}"
PYTHON="${PYTHON:-python3}"
CYCLE_ROTATION_TOLERANT="${CYCLE_ROTATION_TOLERANT:-1}"

MIN_FILES=62 # 56 examples + 6 corpus fixtures; find fewer and the sweep is broken

cd "$REPO" || exit 2

if [ ! -x "$VAKEDZ" ]; then
    echo "passes-diff: vakedz binary not found at $VAKEDZ (zig build first)" >&2
    exit 2
fi

if [ "$CYCLE_ROTATION_TOLERANT" = "1" ]; then
    cat >&2 <<'BANNER'
###########################################################################
# passes-diff: CYCLE_ROTATION_TOLERANT=1 — PYTHONHASHSEED is PINNED to 3.
#
# vakedc's cycle message is hash-seed dependent (pass01_topology.py:58
# iterates a set). Seed 3 is the rotation that equals steps-declaration
# order, which is what vakedz emits deterministically. This is a byte
# compare of EVERY byte of EVERY file — nothing is excluded or normalised.
# Fix the vakedc bug and this pin can be removed. See the header.
###########################################################################
BANNER
    export PYTHONHASHSEED=3
else
    echo "passes-diff: CYCLE_ROTATION_TOLERANT=0 — ambient PYTHONHASHSEED;" \
        "cycle-message rotations are bucketed, not counted as mismatches" >&2
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

# Exit 0 when the two documents differ ONLY by a rotation of the cycle name
# list inside an E-WORKFLOW-CYCLE message; exit 1 otherwise. Only consulted
# when CYCLE_ROTATION_TOLERANT=0.
cycle_rotation_only() { # $1 = py json, $2 = zig json
    "$PYTHON" - "$1" "$2" <<'EOF'
import json, re, sys

def load(p):
    with open(p) as fh:
        return json.load(fh)

CYCLE = re.compile(r"cycle: ([^(]+?) \(express")

def rotations(names):
    n = len(names) - 1  # the list repeats its first element at the end
    if n <= 0:
        return {tuple(names)}
    base = names[:n]
    return {tuple(base[i:] + base[:i] + [base[i]]) for i in range(n)}

def norm(doc):
    """Replace each cycle name list with its canonical rotation set."""
    out = []
    for d in doc.get("diagnostics", []):
        m = CYCLE.search(d.get("message", ""))
        if d.get("code") == "E-WORKFLOW-CYCLE" and m:
            names = [s.strip() for s in m.group(1).split("->")]
            out.append(("E-WORKFLOW-CYCLE", frozenset(rotations(names))))
        else:
            out.append((d.get("code"), d.get("message")))
    rest = dict(doc)
    rest.pop("diagnostics", None)
    return rest, out

py, zg = load(sys.argv[1]), load(sys.argv[2])
py_rest, py_diags = norm(py)
zg_rest, zg_diags = norm(zg)
# Everything outside the cycle message must still match EXACTLY.
if py_rest != zg_rest or py_diags != zg_diags:
    sys.exit(1)
# ... and at least one diagnostic must actually BE a cycle, else this is not
# the rotation bucket.
if not any(c == "E-WORKFLOW-CYCLE" for c, _ in py_diags):
    sys.exit(1)
sys.exit(0)
EOF
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mismatches=0
total=0
parse_agree=0
cycle_rotation=0

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

    if [ "$CYCLE_ROTATION_TOLERANT" != "1" ] && cycle_rotation_only "$tmp/py.json" "$tmp/zig.json"; then
        cycle_rotation=$((cycle_rotation + 1))
        echo "cycle-rotation (vakedc hash-seed bug, NOT a vakedz defect) $f" >&2
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
    "($parse_agree parse-rejected by both sides, $cycle_rotation cycle-rotation)"
[ "$mismatches" -eq 0 ] || exit 1
exit 0
