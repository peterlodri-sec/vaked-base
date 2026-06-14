#!/usr/bin/env python3
"""nocturne orchestrator — the clock, the wallet, and the scribe. NEVER trains.

Runs on a GHA runner or a dev box (no GPU). One night:
  provision (vast) -> upload harness+driver -> bootstrap -> run driver on the box
  -> harvest results.jsonl -> ALWAYS destroy (try/finally + the watchdog) -> ledger
  -> gate -> escalate to swe_af (if a confirmed win) or abstain -> announce.

Commands:
  run [--once] [--dry-run]   one night. --dry-run: provision plan only, $0.
  events                     verify + print the hash-chained ledger.

NOCTURNE_DRY_ACT=1 runs the WHOLE pipeline with NO GPU and NO spend: the driver
synthesizes a results.jsonl locally, so harvest -> gate -> ledger -> (drafted) escalate
are all exercised end-to-end. This is the safe "first manual trigger".
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state")
LEDGER = os.path.join(STATE, "events.jsonl")
RESULTS = os.path.join(STATE, "results.jsonl")
BASELINE_BPB_FILE = os.path.join(STATE, "baseline", "val_bpb")
PROVISION = os.path.join(HERE, "provision.sh")
REMOTE = "/workspace/nocturne"

DRY_ACT = os.environ.get("NOCTURNE_DRY_ACT") not in (None, "", "0")

sys.path.insert(0, HERE)
import gate as gate_mod  # noqa: E402
import ledger as ledger_mod  # noqa: E402


def committed_baseline() -> float | None:
    if os.path.exists(BASELINE_BPB_FILE):
        try:
            return float(open(BASELINE_BPB_FILE).read().strip())
        except ValueError:
            return None
    return None


def sh(*args: str, check: bool = True) -> int:
    print("[nocturne] $ " + " ".join(args), flush=True)
    return subprocess.run(args, check=check).returncode


def provision_run_real(dry: bool) -> None:
    """Rent -> upload -> bootstrap -> drive -> harvest -> ALWAYS destroy."""
    if dry:
        sh("bash", PROVISION, "--dry-run", "rent", check=False)
        print("[nocturne] --dry-run: no GPU rented, $0", flush=True)
        return

    forwarded_env = (
        f'LLM_API_KEY="{os.environ.get("OPENROUTER_API_KEY","")}" '
        f'LLM_BASE_URL="{os.environ.get("LLM_BASE_URL","https://openrouter.ai/api/v1")}" '
        f'LLM_MODEL="{os.environ.get("LLM_MODEL","deepseek/deepseek-chat")}" '
        f'NOCTURNE_HARNESS_DIR="{REMOTE}/harness" '
        f'NOCTURNE_WALL_SECS="{os.environ.get("NOCTURNE_WALL_SECS","6600")}" '
        f'NOCTURNE_MAX_TRIALS="{os.environ.get("NOCTURNE_MAX_TRIALS","60")}" '
        f'NOCTURNE_CONFIRM_SEEDS="{os.environ.get("NOCTURNE_CONFIRM_SEEDS","2")}"'
    )
    try:
        sh("bash", PROVISION, "rent")
        ledger_mod.append(LEDGER, {"event": "provision", "ts": int(time.time())})
        sh("bash", PROVISION, "ssh", f"mkdir -p {REMOTE}")
        sh("bash", PROVISION, "put", os.path.join(HERE, "harness"), f"{REMOTE}/harness")
        sh("bash", PROVISION, "put", os.path.join(HERE, "driver.py"), f"{REMOTE}/driver.py")
        sh("bash", PROVISION, "put", os.path.join(HERE, "program.md"), f"{REMOTE}/harness/program.md", check=False)
        sh("bash", PROVISION, "put", os.path.join(HERE, "onstart.sh"), f"{REMOTE}/onstart.sh")
        sh("bash", PROVISION, "ssh", f"NOCTURNE_HARNESS_DIR={REMOTE}/harness bash {REMOTE}/onstart.sh")
        # the loop (driver runs in the harness dir; train.py invoked via `uv run`)
        sh("bash", PROVISION, "ssh",
           f"cd {REMOTE}/harness && {forwarded_env} python3 {REMOTE}/driver.py", check=False)
        sh("bash", PROVISION, "get", f"{REMOTE}/harness/results.jsonl", RESULTS)
        # harvest the winning train.py too (for the swe_af diff), best-effort
        sh("bash", PROVISION, "get", f"{REMOTE}/harness/train.py", os.path.join(STATE, "candidate-train.py"), check=False)
    finally:
        sh("bash", PROVISION, "destroy", check=False)
        ledger_mod.append(LEDGER, {"event": "teardown", "ts": int(time.time())})


def harvest_and_judge() -> None:
    """Read results.jsonl -> ledger the trials -> gate -> escalate or abstain."""
    if not os.path.exists(RESULTS):
        ledger_mod.append(LEDGER, {"event": "none", "reason": "no results harvested"})
        print("[nocturne] no results.jsonl — abstain", flush=True)
        return

    import json
    rows = [json.loads(l) for l in open(RESULTS, encoding="utf-8") if l.strip()]
    for r in rows:
        if r.get("kind") == "trial":
            ledger_mod.append(LEDGER, {"event": r.get("status", "trial"),
                                       "signature": r.get("signature"), "val_bpb": r.get("val_bpb")})

    known = ledger_mod.signatures(ledger_mod.load(LEDGER))
    verdict = gate_mod.evaluate(RESULTS, committed_baseline(), known_signatures=known)
    print(f"[nocturne] GATE: {'ESCALATE' if verdict.escalate else 'ABSTAIN'} — {verdict.reason}", flush=True)

    if verdict.escalate and verdict.best:
        sig = verdict.best.get("signature")
        ledger_mod.append(LEDGER, {"event": "found", "signature": sig,
                                   "val_bpb": verdict.best.get("val_bpb"),
                                   "baseline": verdict.baseline_bpb})
        escalate(verdict)
    else:
        ledger_mod.append(LEDGER, {"event": "none", "reason": verdict.reason})


def escalate(verdict) -> None:
    """Draft the swe_af issue + the announce. Real dispatch/post is the GHA workflow's job;
    here (or under DRY_ACT) we only draft, so a dev-box run never fires side effects."""
    best = verdict.best
    title = f"nocturne: promote train.py mutation '{best.get('signature')}' (val_bpb {best.get('val_bpb'):.6f})"
    body = (f"Confirmed BPB win from a nocturne night.\n\n"
            f"- signature: `{best.get('signature')}`\n"
            f"- val_bpb: **{best.get('val_bpb'):.6f}** vs baseline {verdict.baseline_bpb:.6f} "
            f"(delta {verdict.baseline_bpb - best.get('val_bpb'):+.6f})\n"
            f"- confirm seeds: {', '.join(f'{v:.6f}' for v in verdict.confirm)}\n"
            f"- description: {best.get('description','')}\n\n"
            f"Promote `tools/nocturne/state/candidate-train.py` to "
            f"`tools/nocturne/state/baseline/train.py`. Ledger: `tools/nocturne/state/events.jsonl`.")
    draft = os.path.join(STATE, "escalation-draft.md")
    open(draft, "w", encoding="utf-8").write(f"# {title}\n\n{body}\n")
    toot = (f"🌙 nocturne found a win: {best.get('signature')} → val_bpb "
            f"{best.get('val_bpb'):.4f} (−{verdict.baseline_bpb - best.get('val_bpb'):.4f}). swe_af ↗")
    open(os.path.join(STATE, "toot-draft.txt"), "w", encoding="utf-8").write(toot + "\n")
    print(f"[nocturne] drafted escalation + toot under state/ "
          f"({'DRY_ACT — not sent' if DRY_ACT else 'GHA workflow dispatches swe_af + posts'})", flush=True)


def cmd_run(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    if DRY_ACT:
        print("[nocturne] DRY_ACT — no GPU, synthesizing results via driver", flush=True)
        env = dict(os.environ, NOCTURNE_HARNESS_DIR=STATE)  # driver writes results.jsonl into STATE
        subprocess.run([sys.executable, os.path.join(HERE, "driver.py")], env=env, check=False)
        # driver writes results.jsonl next to HARNESS_DIR; move into STATE if needed
        harvest_and_judge()
        return 0
    provision_run_real(dry)
    if not dry:
        harvest_and_judge()
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "events":
        return subprocess.run([sys.executable, os.path.join(HERE, "ledger.py"), "replay"],
                              env=dict(os.environ, NOCTURNE_LEDGER=LEDGER)).returncode
    if cmd == "run":
        return cmd_run(sys.argv[2:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
