#!/usr/bin/env python3
"""nocturne driver — runs ON the rented GPU box, inside the vendored harness dir.

The loop (Karpathy autoresearch, automated):
  1. baseline: `uv run train.py` as-is  -> parse `val_bpb`
  2. repeat until wall-clock / max-trials:
       ask OpenRouter for ONE mutated train.py (full file + signature + description)
       -> write it -> `uv run train.py` -> parse val_bpb
       -> KEEP if it beats the running best (persist), else DISCARD (revert)
  3. confirm: re-run the night's best on N seeds (the gate's independent re-run)
  every step appends a row to results.jsonl (the only artifact harvested off the box).

Secrets/env (the port's contract):
  LLM_API_KEY   - OpenRouter key (NOT OPENROUTER_API_KEY on the box)
  LLM_BASE_URL  - default https://openrouter.ai/api/v1
  LLM_MODEL     - default deepseek/deepseek-chat
Config:
  NOCTURNE_WALL_SECS (default 7200)  NOCTURNE_MAX_TRIALS (default 60)
  NOCTURNE_CONFIRM_SEEDS (default 2)  NOCTURNE_DRY_ACT=1 (no LLM, no train; synth a row)
Stdlib only (urllib) so the box needs nothing beyond the harness's own deps.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HARNESS_DIR = os.environ.get("NOCTURNE_HARNESS_DIR", os.getcwd())
RESULTS = os.path.join(HARNESS_DIR, "results.jsonl")
TRAIN = os.path.join(HARNESS_DIR, "train.py")
PROGRAM = os.environ.get("NOCTURNE_PROGRAM", os.path.join(HARNESS_DIR, "program.md"))

WALL_SECS = int(os.environ.get("NOCTURNE_WALL_SECS", "7200"))
MAX_TRIALS = int(os.environ.get("NOCTURNE_MAX_TRIALS", "60"))
CONFIRM_SEEDS = int(os.environ.get("NOCTURNE_CONFIRM_SEEDS", "2"))
DRY_ACT = os.environ.get("NOCTURNE_DRY_ACT") not in (None, "", "0")

LLM_BASE = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek/deepseek-chat")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
PER_TRAIN_TIMEOUT = int(os.environ.get("NOCTURNE_TRAIN_TIMEOUT", "900"))  # 5min budget + slack


def emit(row: dict) -> None:
    with open(RESULTS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[nocturne] {row.get('kind'):<9} "
          + " ".join(f"{k}={v}" for k, v in row.items()
                     if k in ("trial", "val_bpb", "status", "signature", "seed", "note")),
          flush=True)


def run_train(log_name: str = "run.log") -> dict:
    """`uv run train.py`; return parsed metrics. Never raises — crashes become a row."""
    log_path = os.path.join(HARNESS_DIR, log_name)
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.run(
                ["uv", "run", "train.py"], cwd=HARNESS_DIR, stdout=log,
                stderr=subprocess.STDOUT, timeout=PER_TRAIN_TIMEOUT, check=False)
        text = open(log_path, encoding="utf-8", errors="replace").read()
        if proc.returncode != 0:
            return {"crashed": True, "val_bpb": 0.0, "note": f"exit {proc.returncode}",
                    "tail": text[-400:]}
        m = re.search(r"^val_bpb:\s*([0-9.]+)", text, re.MULTILINE)
        vram = re.search(r"^peak_vram_mb:\s*([0-9.]+)", text, re.MULTILINE)
        if not m:
            return {"crashed": True, "val_bpb": 0.0, "note": "no val_bpb in log", "tail": text[-400:]}
        return {"crashed": False, "val_bpb": float(m.group(1)),
                "peak_vram_mb": float(vram.group(1)) if vram else None}
    except subprocess.TimeoutExpired:
        return {"crashed": True, "val_bpb": 0.0, "note": "train timeout"}


def llm_mutation(program: str, train_src: str, history: list[dict]) -> dict | None:
    """Ask OpenRouter for one structured mutation. Returns {signature,description,train_py}."""
    hist = "\n".join(
        f"- {h.get('signature','?')}: val_bpb={h.get('val_bpb')} status={h.get('status')} :: {h.get('description','')}"
        for h in history[-12:]) or "(none yet — this is the first mutation)"
    sys_prompt = (
        "You are nocturne, an autonomous ML researcher. You modify a single-GPU nanochat "
        "training script (train.py) to LOWER val_bpb under a fixed 5-minute training budget. "
        "Only train.py may change; prepare.py and the evaluate_bpb metric are frozen. Reply with "
        "STRICT JSON only: {\"signature\":\"short-kebab-id\",\"description\":\"one line\","
        "\"train_py\":\"<the COMPLETE updated train.py>\"}. The signature must uniquely name the "
        "idea. Make ONE coherent, defensible change; keep it runnable within the time + VRAM budget."
    )
    user = (f"# Objective\n{program}\n\n# Recent trials (avoid repeats)\n{hist}\n\n"
            f"# Current train.py\n```python\n{train_src}\n```\n\n"
            "Return the JSON with the full mutated train.py.")
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        f"{LLM_BASE}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json",
                 "X-Title": "vaked-nocturne"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        obj = json.loads(content[content.find("{"): content.rfind("}") + 1])
        if obj.get("train_py") and obj.get("signature"):
            return obj
    except Exception as e:  # noqa: BLE001 — advisory; a bad mutation just skips a trial
        print(f"[nocturne] llm error: {e}", flush=True)
    return None


def set_seed(src: str, seed: int) -> str:
    """Best-effort seed injection for confirm re-runs (vary determinism if present)."""
    if re.search(r"manual_seed\(\s*\d+\s*\)", src):
        return re.sub(r"manual_seed\(\s*\d+\s*\)", f"manual_seed({seed})", src, count=1)
    return src  # no obvious seed; confirm relies on inherent run-to-run variance


def main() -> int:
    start = time.time()
    open(RESULTS, "w").close()  # fresh per run

    if DRY_ACT:
        # No GPU, no LLM, no train.py needed: synthesize a coherent run so the
        # harvest/gate/ledger path is testable end-to-end on a dev box.
        emit({"kind": "baseline", "val_bpb": 0.997900, "note": "DRY_ACT synthetic"})
        emit({"kind": "trial", "trial": 1, "signature": "dry-wsd", "status": "keep",
              "val_bpb": 0.993100, "description": "DRY_ACT synthetic win", "peak_vram_mb": 46000})
        for s in range(CONFIRM_SEEDS):
            emit({"kind": "confirm", "signature": "dry-wsd", "seed": 1000 + s, "val_bpb": 0.9933 + s * 1e-4})
        print("[nocturne] DRY_ACT complete — synthetic results.jsonl written", flush=True)
        return 0

    if not LLM_KEY:
        print("[nocturne] FATAL: LLM_API_KEY not set on the box", file=sys.stderr)
        return 2

    baseline_src = open(TRAIN, encoding="utf-8").read()

    # 1. Baseline.
    t0 = time.time()
    b = run_train("run.baseline.log")
    base_secs = time.time() - t0
    emit({"kind": "baseline", **{k: b[k] for k in ("val_bpb", "peak_vram_mb", "note") if k in b}})
    if b["crashed"]:
        emit({"kind": "error", "note": "baseline crashed — aborting", "detail": b.get("tail", "")})
        return 1
    best_bpb = b["val_bpb"]
    best_src = baseline_src
    best_sig = None
    history: list[dict] = []

    # Reserve wall-clock for the confirm phase so a long search can't starve it — the gate needs
    # CONFIRM_SEEDS confirm rows, and without a reserve a full-length search leaves zero, silently
    # discarding a real win. Budget ~1.2x the measured baseline per seed, capped at 30% of the wall.
    confirm_reserve = min(CONFIRM_SEEDS * base_secs * 1.2, WALL_SECS * 0.30)
    search_deadline = WALL_SECS - confirm_reserve

    # 2. Search.
    trial = 0
    while time.time() - start < search_deadline and trial < MAX_TRIALS:
        trial += 1
        cur_src = open(TRAIN, encoding="utf-8").read()
        mut = llm_mutation(open(PROGRAM, encoding="utf-8").read() if os.path.exists(PROGRAM) else "",
                           cur_src, history)
        if not mut:
            emit({"kind": "trial", "trial": trial, "status": "skip", "note": "no mutation"})
            continue
        open(TRAIN, "w", encoding="utf-8").write(mut["train_py"])
        r = run_train()
        keep = (not r["crashed"]) and r["val_bpb"] > 0 and (best_bpb - r["val_bpb"]) > 0
        status = "crash" if r["crashed"] else ("keep" if keep else "discard")
        row = {"kind": "trial", "trial": trial, "signature": mut["signature"],
               "description": mut.get("description", ""), "status": status,
               "val_bpb": r["val_bpb"], "peak_vram_mb": r.get("peak_vram_mb")}
        if r.get("note"):
            row["note"] = r["note"]
        emit(row)
        history.append(row)
        if keep:
            best_bpb, best_src, best_sig = r["val_bpb"], mut["train_py"], mut["signature"]
        else:
            open(TRAIN, "w", encoding="utf-8").write(best_src)  # revert to running best

    # 3. Confirm the night's best on independent seeds (the gate's re-run evidence).
    if best_sig is not None:
        open(TRAIN, "w", encoding="utf-8").write(best_src)
        for i in range(CONFIRM_SEEDS):
            if time.time() - start >= WALL_SECS:
                break
            open(TRAIN, "w", encoding="utf-8").write(set_seed(best_src, 1000 + i))
            r = run_train(f"run.confirm{i}.log")
            emit({"kind": "confirm", "signature": best_sig, "seed": 1000 + i,
                  "val_bpb": r["val_bpb"], "crashed": r["crashed"]})
        open(TRAIN, "w", encoding="utf-8").write(best_src)

    emit({"kind": "summary", "trials": trial, "best_bpb": best_bpb, "best_signature": best_sig,
          "elapsed_s": round(time.time() - start, 1)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
