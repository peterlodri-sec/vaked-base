"""dogfood.kernel — the JUDGE: gate, record, replay-verify one transition.

Pipeline (proposer/judge split):

    snapshot base → run proposer (mutates tree) → detect actual changes →
    CAPABILITY gate (changes ⊆ granted scope) →
    DECLARED-vs-ACTUAL gate (claims == filesystem reality) →
    [OBSERVED gate — declared ≈ Frida-observed, when available (M3)] →
    capture post-images → REPLAY gate (base + post-images ⇒ recorded state hash) →
    accept ⇒ append to eventd WAL ;  reject ⇒ roll the tree back to base.

A transition is accepted only when every gate passes. On rejection the working
tree is restored to its pre-proposal state, so a rejected proposal leaves no
trace except (optionally) the operator's logs. The accepted record lands in the
real eventd append-only hash chain (``dogfood.wal``).

CLI:
    kernel.py propose --scope tools/dogfood/sandbox --intent "..." \\
        [--proposer stub --edit rel=path | --proposer opencode]
    kernel.py verify        # re-open WAL, boot tamper-check + replay summary
    kernel.py log           # list recorded transitions

Pure-stdlib; runs on macOS (no kernel features needed — that is L2's job).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import capability               # noqa: E402
import transition as T          # noqa: E402
import wal as W                 # noqa: E402

DEFAULT_WAL = os.path.join(".dogfood", "wal", "transitions.jsonl")
DEFAULT_BLOBS = os.path.join(".dogfood", "blobs")


# --- change detection -------------------------------------------------------

def _is_git(root: str) -> bool:
    return subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
                          capture_output=True, text=True).returncode == 0


def _git_universe(root: str) -> list[str]:
    """Files git 'sees': tracked + untracked-but-not-ignored. Respects
    .gitignore via --exclude-standard, so the kernel's own .dogfood state and
    build artifacts stay out of the judged tree."""
    out = subprocess.run(
        ["git", "-C", root, "ls-files", "--cached", "--others",
         "--exclude-standard", "-z"],
        capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def _git_snapshot(root: str) -> dict[str, str]:
    """Content snapshot of the git file universe: {rel: sha}. The before/after
    delta of two of these is exactly one proposal's effect — independent of any
    pre-existing dirty state in the worktree."""
    snap = {}
    for rel in _git_universe(root):
        full = os.path.join(root, rel)
        if os.path.isfile(full):
            snap[rel] = T.file_sha(full)
    return snap


def _full_changes(root: str, base_full: dict) -> dict:
    """Whole-``root`` change set via snapshot diff (non-git fallback, e.g. tests)."""
    cur_full = T.tree_snapshot(root, ["."])
    return T.changed_set(base_full, cur_full)


# --- rollback ---------------------------------------------------------------

def _restore_in_scope(root: str, blobs: str, base_scope: dict, scope: list[str]) -> None:
    """Restore in-scope files to their captured base images; remove any in-scope
    file that did not exist at base. Used to undo a rejected proposal."""
    for rel in T.iter_scope_files(root, scope):
        if rel not in base_scope:
            os.remove(os.path.join(root, rel))      # created by the proposal
    for rel, sha in base_scope.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "wb") as f:
            f.write(T.load_blob(blobs, sha))


def _git_restore(root: str, paths: list[str]) -> None:
    """Best-effort revert of out-of-scope violation paths in a git worktree.

    Tracked files are restored to HEAD via ``git checkout`` (NEVER removed —
    removing a tracked file would destroy committed content). Untracked files,
    which ``checkout`` cannot restore, are the ones the proposer newly created,
    so those are removed.
    """
    for p in paths:
        tracked = subprocess.run(
            ["git", "-C", root, "ls-files", "--error-unmatch", p],
            capture_output=True).returncode == 0
        if tracked:
            subprocess.run(["git", "-C", root, "checkout", "--", p],
                           capture_output=True)
        else:
            full = os.path.join(root, p)
            if os.path.exists(full):
                try:
                    os.remove(full)
                except OSError:
                    pass


def _restore_full(root: str, blobs: str, base_full: dict) -> None:
    """Total rollback for the non-git path: delete any file not present at base
    and rewrite every base file from its captured blob. Used in tests / when the
    tree is not a git worktree, so out-of-scope violations are cleaned too."""
    cur = set(T.iter_scope_files(root, ["."]))
    for rel in cur - set(base_full):
        os.remove(os.path.join(root, rel))
    for rel, sha in base_full.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "wb") as f:
            f.write(T.load_blob(blobs, sha))


# --- replay gate ------------------------------------------------------------

def _replay_state_hash(base_scope: dict, blobs: str, postimages: dict,
                       deletes: list[str]) -> str:
    """Reconstruct the post-state in a throwaway dir from base + recorded
    post-images, and hash it. Same content-addressed inputs ⇒ same hash, so a
    mismatch with the live ``state_hash_after`` means the capture was incomplete,
    a blob is corrupt, or the tree drifted after measurement."""
    with tempfile.TemporaryDirectory() as tmp:
        # lay down base in-scope files
        for rel, sha in base_scope.items():
            dest = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "wb") as f:
                f.write(T.load_blob(blobs, sha))
        # apply recorded post-images (writes) and deletes
        for rel in deletes:
            p = os.path.join(tmp, rel)
            if os.path.exists(p):
                os.remove(p)
        for rel, sha in postimages.items():
            dest = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "wb") as f:
                f.write(T.load_blob(blobs, sha))
        rebuilt = T.tree_snapshot(tmp, ["."])
        return T.tree_hash(rebuilt)


# --- the judge --------------------------------------------------------------

def judge(root: str, scope: list[str], intent: str, proposer, *,
          wal_path: str, blobs_dir: str, observed: dict | None = None,
          record: bool = True) -> dict:
    """Run one transition through every gate. Returns a verdict dict; appends to
    the WAL only when accepted and ``record`` is True. ``proposer`` is a callable
    ``proposer(root, scope, intent) -> declared|None`` that mutates the tree."""
    root = os.path.abspath(root)
    blobs_dir = blobs_dir if os.path.isabs(blobs_dir) else os.path.join(root, blobs_dir)
    wal_path = wal_path if os.path.isabs(wal_path) else os.path.join(root, wal_path)

    reasons: list[str] = []
    base_scope = T.tree_snapshot(root, scope)
    input_tree_hash = T.tree_hash(base_scope)
    # capture base images so a rejected proposal can be rolled back
    for rel in list(base_scope):
        T.store_blob(blobs_dir, os.path.join(root, rel))
    git = _is_git(root)
    base_git = _git_snapshot(root) if git else None
    base_full = None if git else T.tree_snapshot(root, ["."])
    if base_full is not None:
        # non-git: blob the whole base so a reject can be totally rolled back
        for rel in base_full:
            T.store_blob(blobs_dir, os.path.join(root, rel))

    # 1. PROPOSE (mutates the tree in place)
    declared = proposer(root, scope, intent)

    # 2. DETECT actual changes — the before/after delta caused by THIS proposal
    actual = (T.changed_set(base_git, _git_snapshot(root)) if git
              else _full_changes(root, base_full))
    actual_paths = actual["writes"] + actual["deletes"]

    # 3. CAPABILITY gate — every changed path must be granted
    cap = capability.check(actual_paths, scope)
    if not cap["ok"]:
        reasons.append(f"capability: out-of-scope paths {cap['violations']}")

    # in-scope diff (for post-images + state hash)
    cur_scope = T.tree_snapshot(root, scope)
    scope_changed = T.changed_set(base_scope, cur_scope)
    postimages = T.capture_postimages(root, blobs_dir, scope_changed["writes"])
    state_hash_after = T.tree_hash(cur_scope)

    # 4. DECLARED-vs-ACTUAL gate (declared None ⇒ trust the filesystem)
    if declared is None:
        declared = actual
    declared = {"writes": sorted(declared.get("writes", [])),
                "deletes": sorted(declared.get("deletes", []))}
    if declared != actual:
        reasons.append(f"declared!=actual: declared={declared} actual={actual}")

    # 5. OBSERVED gate (M3 Frida) — observed writes must be a subset of declared
    if observed is not None:
        extra = sorted(set(observed.get("writes", [])) - set(declared["writes"]))
        if extra:
            reasons.append(f"observed>declared: undeclared writes {extra}")

    # 6. REPLAY gate — base + post-images must reconstruct the recorded state hash
    replayed = _replay_state_hash(base_scope, blobs_dir, postimages,
                                  scope_changed["deletes"])
    if replayed != state_hash_after:
        reasons.append(f"replay unstable: {replayed} != {state_hash_after}")

    accepted = not reasons
    payload = T.build_payload(
        intent=intent, scope=scope, input_tree_hash=input_tree_hash,
        declared=declared, actual=actual, postimages=postimages,
        state_hash_after=state_hash_after, capability_ok=cap["ok"],
        observed=observed)

    entry = None
    if accepted and record:
        with W.EventLog(wal_path, writer=True) as log:
            entry = W.append_transition(log, payload)
    elif not accepted:
        # roll the tree back so a rejected proposal leaves no trace
        if git:
            if cap["violations"]:
                _git_restore(root, cap["violations"])
            _restore_in_scope(root, blobs_dir, base_scope, scope)
        else:
            # non-git: total restore from base (also cleans out-of-scope writes)
            _restore_full(root, blobs_dir, base_full)

    return {"accepted": accepted, "reasons": reasons,
            "state_hash_after": state_hash_after, "replayed_state_hash": replayed,
            "input_tree_hash": input_tree_hash, "capability": cap,
            "declared": declared, "actual": actual, "observed": observed,
            "seq": (entry or {}).get("seq"), "hash": (entry or {}).get("hash"),
            "payload": payload}


# --- CLI --------------------------------------------------------------------

def _proposer_from_args(args):
    if args.proposer == "opencode":
        import proposer as P
        return lambda root, scope, intent: P.opencode_propose(root, intent)
    # stub: --edit rel=srcfile (repeatable); --declare-extra rel marks a declared
    # write not actually performed (for demos of the declared!=actual gate)
    import proposer as P
    edits: dict[str, "str | None"] = {}
    for spec in (args.edit or []):
        rel, _, src = spec.partition("=")
        edits[rel] = None if src == "" else open(src).read()
    declared = None
    if args.declare:
        declared = {"writes": args.declare, "deletes": []}
    return lambda root, scope, intent: P.stub_propose(root, edits, declared)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dogfood-kernel")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("propose", help="run one transition through the judge")
    p.add_argument("--root", default=".")
    p.add_argument("--scope", required=True,
                   help="comma-separated granted path prefixes")
    p.add_argument("--intent", required=True)
    p.add_argument("--proposer", choices=["stub", "opencode"], default="stub")
    p.add_argument("--edit", action="append", help="stub edit rel=srcfile (repeatable)")
    p.add_argument("--declare", action="append", help="stub declared write (repeatable)")
    p.add_argument("--wal", default=DEFAULT_WAL)
    p.add_argument("--blobs", default=DEFAULT_BLOBS)

    for name in ("verify", "log"):
        q = sub.add_parser(name)
        q.add_argument("--root", default=".")
        q.add_argument("--wal", default=DEFAULT_WAL)

    args = ap.parse_args(argv)

    if args.cmd == "propose":
        scope = [s.strip() for s in args.scope.split(",") if s.strip()]
        verdict = judge(args.root, scope, args.intent, _proposer_from_args(args),
                        wal_path=args.wal, blobs_dir=args.blobs)
        print(json.dumps({k: verdict[k] for k in
                          ("accepted", "reasons", "seq", "state_hash_after",
                           "replayed_state_hash", "capability")}, indent=2))
        return 0 if verdict["accepted"] else 1

    wal_path = args.wal if os.path.isabs(args.wal) else os.path.join(args.root, args.wal)
    if args.cmd == "verify":
        try:
            with W.EventLog(wal_path) as log:          # boot tamper-check
                summary = W.replay_summary(log)
            print(json.dumps({"ok": True, "entries": len(log), **summary}, indent=2))
            return 0
        except FileNotFoundError:
            print(json.dumps({"ok": True, "entries": 0, "note": "no WAL yet"}))
            return 0
        except W.TamperError as e:
            print(json.dumps({"ok": False, "tamper": str(e)}))
            return 1

    if args.cmd == "log":
        try:
            with W.EventLog(wal_path) as log:
                for e in log.entries:
                    pl = e.get("payload", {})
                    if pl.get("kind") == T.KIND:
                        print(f"seq={e['seq']} state={pl['state_hash_after'][:12]} "
                              f"intent={pl['intent'][:60]}")
            return 0
        except FileNotFoundError:
            print("no WAL yet")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
