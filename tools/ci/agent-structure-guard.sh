#!/usr/bin/env bash
#
# agent-structure-guard — fail a PR that silently REVERTS a landed agent refactor.
#
# Root cause this guards against: long-lived agent branches are created from an
# old base and never rebased. When a whole-file refactor lands on main — e.g.
# pr-review's modularization (one big main.rs → many modules) or the fleet's
# move to the shared `vaked_telemetry::setup_tracing` — the stale branch still
# carries the PRE-refactor whole file. A 3-way merge can't auto-reconcile a whole
# file, so resolving "in favour of the branch" silently re-monolithizes the crate
# or re-inlines tracing, reverting the landed work (this bit us on #156 and again,
# harder, on #173).
#
# The guard enforces three invariants per agent crate, comparing the PR against
# its merge base. None fire on a legitimate forward change; each fires on a revert:
#   1. Re-monolithization — a crate whose base main.rs is a thin dispatcher
#      (< THIN_CAP lines) must keep it thin. (pr-review 125 → 2924 trips this.)
#   2. Telemetry re-inlining — a crate whose base calls
#      `vaked_telemetry::setup_tracing` must not re-add a local `fn setup_tracing`.
#   3. Module-file deletion — a crate's existing `src/*.rs` modules must not vanish.
#
# Usage: agent-structure-guard.sh [BASE_REF]   (BASE_REF default: origin/main)
# Exits non-zero (and prints ::error:: lines for GitHub) if any invariant breaks.

set -uo pipefail

BASE="${1:-origin/main}"
# A dispatcher main.rs is well under this; the smallest monolith (swe-af) is ~800.
THIN_CAP=250
AGENTS=(pr-review provost label-tagger swe-af)
fail=0

base_show() { git show "$BASE:$1" 2>/dev/null; }

for a in "${AGENTS[@]}"; do
    dir="vaked-agents/ci/$a"
    main="$dir/src/main.rs"
    base_main="$(base_show "$main")"

    # If the crate had a main.rs on base but it's gone now, the entry point was
    # deleted (whole-`src` removal / stale-branch revert). Flag it — and crucially
    # do NOT skip the crate, or the module-deletion scan (3) below never runs and a
    # PR that drops the entire src tree slips past the gate.
    if [ -n "$base_main" ] && [ ! -f "$main" ]; then
        echo "::error file=$main::$a/src/main.rs exists on $BASE but is gone in this PR — the crate's entry point was deleted (whole-src removal or stale-branch revert)."
        fail=1
    fi

    # 1) Re-monolithization: a thin base main.rs must stay thin. (Needs the head
    #    main.rs present; a deleted main.rs is handled by the checks above/below.)
    if [ -f "$main" ]; then
        base_lines=$(printf '%s' "$base_main" | grep -c '' || true)
        head_lines=$(grep -c '' "$main" || true)
        if [ "$base_lines" -gt 0 ] && [ "$base_lines" -lt "$THIN_CAP" ] && [ "$head_lines" -ge "$THIN_CAP" ]; then
            echo "::error file=$main::$a/src/main.rs is a thin dispatcher on $BASE ($base_lines lines) but this PR balloons it to $head_lines. That re-monolithizes the crate and reverts its module split — rebase on $BASE and re-apply your change on top of the modules."
            fail=1
        fi
    fi

    # 2) Telemetry re-inlining: if the crate delegates to vaked_telemetry::setup_tracing
    #    ANYWHERE in its src on $BASE — the call may live in src/telemetry.rs rather
    #    than main.rs (e.g. modularized pr-review) — the head must still call it
    #    somewhere in src. A revert to the old inline OTLP builder drops the call.
    #    Scan the whole src tree on BOTH sides (base via `git grep`), not just main.rs.
    if git grep -q 'vaked_telemetry::setup_tracing' "$BASE" -- "$dir/src" 2>/dev/null; then
        if ! grep -rqs 'vaked_telemetry::setup_tracing' "$dir/src"; then
            echo "::error file=$main::$a delegates tracing to vaked_telemetry::setup_tracing on $BASE (somewhere in src), but this PR drops that call (re-inlining the old OTLP setup). That reverts the shared-telemetry refactor — keep calling vaked_telemetry::setup_tracing."
            fail=1
        fi
    fi

    # 3) Module-file deletion (runs regardless of main.rs presence): existing
    #    src/*.rs modules must not be removed.
    deleted=$(git diff --diff-filter=D --name-only "$BASE" -- "$dir/src" 2>/dev/null | grep '\.rs$' || true)
    if [ -n "$deleted" ]; then
        while IFS= read -r f; do
            echo "::error file=$f::$a deletes module file $f that exists on $BASE. If this is an intentional restructure, say so in the PR; otherwise it is a stale-branch revert of the module split."
        done <<< "$deleted"
        fail=1
    fi
done

if [ "$fail" -ne 0 ]; then
    echo ""
    echo "agent-structure-guard: a landed agent refactor would be reverted by this PR (see errors above)."
    echo "Fix: rebase the branch on $BASE so it carries the post-refactor files, then re-apply your change."
    exit 1
fi
echo "agent-structure-guard: OK — no agent refactor reverted."
