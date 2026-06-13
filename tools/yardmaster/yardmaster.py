"""yardmaster — a merge-train conductor for the Vaked agent fleet.

The development fleet is fan-out: many agents (Claude sessions + CI/cron agents)
each open a branch/PR, sometimes **stacked** (PR B based on PR A's branch). There
is a runtime supervisor (`agent-supervisord`) and a decision loop (`ralph`), but
nothing sequences the *integration* of those PRs. yardmaster is that missing
piece — the rail-yard role that orders cars into a train and dispatches them:

  each tick → observe open PRs → build the dependency DAG (catch stacked PRs)
            → topologically order the train → act on the head by mergeable_state
            → record the action on a hash-chained ledger → notify.

Design stance (mirrors `pr-review` "advisory, never blocks" + `ralph` "human
ratifies"):

  * **advisory by default** — `--dry-run` plans + ledgers the train but merges
    nothing until `YARDMASTER_ENABLE_MERGE=1`;
  * **opt-in only** — auto-merges a PR only with the `train:auto` label or a
    fleet-author allowlist;
  * **never resolves content conflicts** — a `dirty` PR is flagged for a human,
    not silently merged (content unions need judgment, not a mechanical merge);
  * **one action per tick** — single-writer, auditable, rate-limit-friendly.

Reuse (no new machinery): the hash-chained ledger is `eventd` (the project's
audit spine); pause/slow/step control + ratify-rate are `ralphcore`. Python 3.11+
stdlib only otherwise (urllib for the GitHub REST API; no `gh`, no deps).

CLI (run by path; stdlib-only):
    python3 tools/yardmaster/yardmaster.py plan   [--repo o/r]            # dry-run: print the train
    python3 tools/yardmaster/yardmaster.py tick   [--repo o/r] [--enable] # one action, then stop
    python3 tools/yardmaster/yardmaster.py verify [--log PATH]            # verify the ledger chain
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO_ROOT)                       # eventd (root package)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "ralph"))   # ralphcore

STATE_DIR = os.path.join(HERE, "state")
LOG_PATH = os.path.join(STATE_DIR, "log.jsonl")
CONTROL_PATH = os.path.join(STATE_DIR, "control.json")

# Authors whose PRs the train may auto-advance without the `train:auto` label.
FLEET_AUTHORS = {"ralph-loop", "github-actions[bot]"}
OPT_IN_LABEL = "train:auto"
CONFLICT_LABEL = "train:needs-human"


# --------------------------------------------------------------------------- #
# Pure model — a PR as the train sees it (no network; unit-testable).
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PR:
    number: int
    head_ref: str
    base_ref: str
    mergeable_state: str          # clean|behind|dirty|unstable|blocked|draft|unknown
    ci: str                       # success|failure|pending|none
    draft: bool
    labels: tuple = ()
    author: str = ""

    @property
    def opt_in(self) -> bool:
        return OPT_IN_LABEL in self.labels or self.author in FLEET_AUTHORS


# Action verbs (the total decision set).
MERGE, UPDATE_BRANCH, WAIT, BLOCK_CONFLICT, SKIP = (
    "merge", "update_branch", "wait", "block_conflict", "skip")


def build_dag(prs: list) -> dict:
    """``{pr.number: [base_pr.number, ...]}`` — an edge to every OPEN PR whose
    head branch is this PR's base (a stacked dependency). A PR based on ``main``
    has no edges."""
    by_head = {}
    for p in prs:
        by_head.setdefault(p.head_ref, []).append(p.number)
    deps = {}
    for p in prs:
        deps[p.number] = sorted(n for n in by_head.get(p.base_ref, []) if n != p.number)
    return deps


def topo_order(prs: list) -> list:
    """PR numbers in dependency order (a base before anything stacked on it).
    Kahn's algorithm over :func:`build_dag`; raises ``ValueError`` on a cycle.
    Ties broken by ascending PR number for determinism."""
    deps = build_dag(prs)
    indeg = {n: len(deps[n]) for n in deps}
    ready = sorted(n for n, d in indeg.items() if d == 0)
    out = []
    # children[base] = [dependents]
    children = {n: [] for n in deps}
    for n, ds in deps.items():
        for d in ds:
            children[d].append(n)
    while ready:
        n = ready.pop(0)
        out.append(n)
        for c in sorted(children[n]):
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
        ready.sort()
    if len(out) != len(deps):
        cyclic = sorted(set(deps) - set(out))
        raise ValueError("dependency cycle among PRs %s" % cyclic)
    return out


def decide(pr: PR, base_open: bool, default_branch: str = "main") -> "tuple[str, str]":
    """The train's action for ``pr`` → ``(action, reason)``. ``base_open`` is
    True when a stacked dependency is still an open (unmerged) PR. TOTAL over
    every ``mergeable_state`` (the test asserts this)."""
    if pr.draft:
        return SKIP, "draft"
    if not pr.opt_in:
        return SKIP, "not opt-in (needs %s label or fleet author)" % OPT_IN_LABEL
    if base_open:
        return SKIP, "waiting on an unmerged base PR"
    if pr.base_ref != default_branch:
        # base is neither the default branch nor a still-open PR: an ORPHANED
        # stacked PR — its parent merged/closed but the child was not retargeted.
        # Merging now would integrate into the stale base branch, not the default
        # branch (closing the PR without landing on main). Never act — retarget
        # the PR's base to %s first.
        return SKIP, ("base %r is not the default branch (%s) — retarget before "
                      "merging" % (pr.base_ref, default_branch))
    st = pr.mergeable_state
    if st == "dirty":
        return BLOCK_CONFLICT, "merge conflict — needs human resolution"
    if st == "behind":
        return UPDATE_BRANCH, "base advanced — update branch"
    if st == "clean":
        if pr.ci == "success":
            return MERGE, "clean + CI green"
        if pr.ci == "failure":
            return SKIP, "clean but CI failed"
        return WAIT, "clean; CI pending"
    if st in ("unstable", "blocked"):
        if pr.ci == "failure":
            return SKIP, "CI failed"
        return WAIT, "CI pending / required check"
    # unknown / missing: GitHub is still computing mergeability — wait a tick.
    return WAIT, "mergeability unknown; recompute next tick"


def plan_train(prs: list, default_branch: str = "main") -> list:
    """The full planned train: ``[(number, action, reason), ...]`` in merge
    order. Pure — what ``plan`` prints and ``tick`` consumes (acting on the first
    non-terminal action)."""
    order = topo_order(prs)
    by_num = {p.number: p for p in prs}
    deps = build_dag(prs)
    open_numbers = set(by_num)
    merged_yet: set = set()         # within this plan, assume nothing merged yet
    out = []
    for n in order:
        p = by_num[n]
        base_open = any(d in open_numbers and d not in merged_yet for d in deps[n])
        action, reason = decide(p, base_open, default_branch)
        out.append((n, action, reason))
    return out


# --------------------------------------------------------------------------- #
# GitHub REST client (stdlib urllib) — the only networked part.
# --------------------------------------------------------------------------- #

import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


class GitHub:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo                    # "owner/name"

    def _req(self, method: str, path: str, body=None):
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:200]
            raise RuntimeError("GitHub %s %s -> %s %s" % (method, path, e.code, detail))

    def default_branch(self) -> str:
        return self._req("GET", "/repos/%s" % self.repo).get("default_branch", "main")

    def open_prs(self) -> list:
        return self._req("GET", "/repos/%s/pulls?state=open&per_page=100" % self.repo)

    def pr(self, n: int) -> dict:
        return self._req("GET", "/repos/%s/pulls/%d" % (self.repo, n))

    def ci_state(self, sha: str) -> str:
        runs = self._req("GET", "/repos/%s/commits/%s/check-runs" % (self.repo, sha))
        items = runs.get("check_runs", [])
        if not items:
            return "none"
        if any(c.get("status") != "completed" for c in items):
            return "pending"
        if any(c.get("conclusion") in ("failure", "timed_out", "cancelled")
               for c in items):
            return "failure"
        return "success"

    def update_branch(self, n: int):
        return self._req("PUT", "/repos/%s/pulls/%d/update-branch" % (self.repo, n), {})

    def merge(self, n: int, method: str = "squash"):
        return self._req("PUT", "/repos/%s/pulls/%d/merge" % (self.repo, n),
                         {"merge_method": method})

    def add_label(self, n: int, label: str):
        return self._req("POST", "/repos/%s/issues/%d/labels" % (self.repo, n),
                         {"labels": [label]})

    def comment(self, n: int, body: str):
        return self._req("POST", "/repos/%s/issues/%d/comments" % (self.repo, n),
                         {"body": body})


def fetch_prs(gh: GitHub) -> list:
    """Materialize the open PRs as :class:`PR` (mergeable_state + CI resolved)."""
    out = []
    for raw in gh.open_prs():
        n = raw["number"]
        full = gh.pr(n)                       # list view omits mergeable_state
        head = full["head"]
        out.append(PR(
            number=n,
            head_ref=head["ref"],
            base_ref=full["base"]["ref"],
            mergeable_state=full.get("mergeable_state") or "unknown",
            ci=gh.ci_state(head["sha"]),
            draft=bool(full.get("draft")),
            labels=tuple(l["name"] for l in full.get("labels", [])),
            author=(full.get("user") or {}).get("login", ""),
        ))
    return out


# --------------------------------------------------------------------------- #
# Ledger (eventd) + control (ralphcore).
# --------------------------------------------------------------------------- #

def _ledger_append(payload: dict) -> dict:
    from eventd import EventLog
    os.makedirs(STATE_DIR, exist_ok=True)
    with EventLog(LOG_PATH, writer=True) as log:
        return log.append(payload)


def _read_control():
    import ralphcore
    try:
        d = json.load(open(CONTROL_PATH, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        d = None
    return ralphcore.parse_control(d)


def _clear_step() -> None:
    """Consume the one-shot ``step`` flag after a stepped tick (mirrors ralph's
    ``_clear_step``). Without this a ``{"paused": true, "step": true}`` control
    file would make *every* subsequent tick act while the train looks paused."""
    try:
        d = json.load(open(CONTROL_PATH, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if d.get("step"):
        d["step"] = False
        with open(CONTROL_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)


# --------------------------------------------------------------------------- #
# The tick.
# --------------------------------------------------------------------------- #

def run_tick(gh: GitHub, *, enable_merge: bool) -> dict:
    """One train action. Returns a summary dict (also appended to the ledger).
    Honors the control file (paused ⇒ no-op unless step)."""
    ctrl = _read_control()
    if ctrl.paused and not ctrl.step:
        return {"action": "paused", "reason": "control.json paused"}
    if ctrl.step:
        _clear_step()                       # one-shot: consume it for this tick

    prs = fetch_prs(gh)
    if not prs:
        _ledger_append({"kind": "observed", "open_prs": 0})
        return {"action": "idle", "reason": "no open PRs"}

    planned = plan_train(prs, gh.default_branch())
    by_num = {p.number: p for p in prs}
    _ledger_append({"kind": "observed", "open_prs": len(prs),
                    "train": [[n, a] for n, a, _ in planned]})

    # First actionable (non-terminal) car.
    for n, action, reason in planned:
        if action in (SKIP, WAIT):
            continue
        pr = by_num[n]
        summary = {"pr": n, "action": action, "reason": reason,
                   "mergeable_state": pr.mergeable_state, "ci": pr.ci,
                   "enabled": enable_merge}
        if not enable_merge:
            summary["note"] = "dry-run (set YARDMASTER_ENABLE_MERGE=1 to act)"
            _ledger_append({"kind": "dry_run", **summary})
            return summary
        # live mode
        if action == UPDATE_BRANCH:
            gh.update_branch(n)
            _ledger_append({"kind": "rebased", **summary})
        elif action == MERGE:
            gh.merge(n)
            _ledger_append({"kind": "merged", **summary})
        elif action == BLOCK_CONFLICT:
            gh.add_label(n, CONFLICT_LABEL)
            gh.comment(n, "🚂 yardmaster: this PR has a merge conflict the train "
                          "cannot auto-resolve (content merges need judgment). "
                          "Labeled `%s`; the train will skip it until resolved." % CONFLICT_LABEL)
            _ledger_append({"kind": "blocked_conflict", **summary})
        return summary

    _ledger_append({"kind": "settled", "open_prs": len(prs)})
    return {"action": "settled", "reason": "no actionable car (all waiting/skipped)"}


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #

def _gh_from_env(repo: "str | None") -> GitHub:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        sys.stderr.write("yardmaster: GITHUB_TOKEN and --repo/GITHUB_REPOSITORY "
                         "required (no-op without them)\n")
        sys.exit(0)                          # guard: clean no-op, like the other agents
    return GitHub(token, repo)


def _print_plan(prs: list, default_branch: str = "main"):
    print("== merge train (%d open PRs) ==" % len(prs))
    for n, action, reason in plan_train(prs, default_branch):
        print("  #%-4d  %-14s  %s" % (n, action, reason))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="yardmaster")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "tick"):
        sp = sub.add_parser(name)
        sp.add_argument("--repo")
        if name == "tick":
            sp.add_argument("--enable", action="store_true",
                            help="actually act (else dry-run); also gated by YARDMASTER_ENABLE_MERGE")
    sv = sub.add_parser("verify"); sv.add_argument("--log", default=LOG_PATH)
    args = ap.parse_args(argv)

    if args.cmd == "verify":
        from eventd import EventLog, TamperError
        try:
            log = EventLog(args.log)
            print("ledger OK: %d entries, chain intact" % len(log))
            return 0
        except TamperError as e:
            print("ledger TAMPER:", e); return 1
        except FileNotFoundError:
            print("no ledger yet at", args.log); return 0

    gh = _gh_from_env(args.repo)
    if args.cmd == "plan":
        _print_plan(fetch_prs(gh), gh.default_branch())
        return 0
    if args.cmd == "tick":
        enable = bool(getattr(args, "enable", False)) or \
            os.environ.get("YARDMASTER_ENABLE_MERGE") == "1"
        out = run_tick(gh, enable_merge=enable)
        print(json.dumps(out, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
