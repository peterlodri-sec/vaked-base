# Nocturne GPU Run — $6-Budget Runbook (no-SSH-burn edition)

Grounds: `tools/nocturne/provision.sh`, `tools/nocturne/nocturne.py`, `tools/nocturne/onstart.sh`, `tools/nocturne/{prepare.py,train.py}` (harness). This runbook keeps the nocturne RENT→SSH→TRAIN→TEARDOWN flow but inserts the **sshd-readiness gate** and a **survivable teardown** that the current code is missing. Last week burned ~$10 because the box was rented, SSH was fired before sshd was listening, and the only thing that could kill a leaked box (`( sleep; vastai destroy ) &`) does not survive a runner SIGKILL.

> Golden rule: **a box is never rented without an `EXIT` trap already armed that destroys it.** The trap is set BEFORE `vastai create`, so even a crash between create and the poll loop still tears down.

---

## 0. Budget math (do this first — total MUST be < $6 with margin)

The nocturne default targets an `H100_SXM @ ≤$3/hr` for `MAX_MINUTES=180` → ceiling **$9.00**. That is over budget and is what burned last week. For a $6-capped fine-tune you do NOT need an H100. The autoresearch harness (`train.py`, nanoGPT-scale, single GPU) fits a **single RTX 4090 / 3090** comfortably.

| Knob (env) | Last-week default | $6-safe value | Why |
|---|---|---|---|
| `GPU_NAME` | `H100_SXM` | `RTX_4090` (or `RTX_3090`) | 4090 ≈ $0.30–0.45/hr vs H100 ≈ $2–3/hr; single-GPU nanoGPT fits 24GB |
| `MAX_DPH` | `3.0` | `0.55` | hard search filter — no offer above this is even considered |
| `MAX_MINUTES` | `180` | `75` | watchdog hard cap; bootstrap(~10m)+wall+harvest fits |
| `NOCTURNE_WALL_SECS` | `9000` (150m) | `3000` (50m) | driver self-stops with confirm-reserve before watchdog |
| `NOCTURNE_MAX_TRIALS` | `60` | `15` | fewer mutate→train cycles |
| `NOCTURNE_CONFIRM_SEEDS` | `2` | `2` | keep — confirmation is the whole point |

**Estimate:** `0.55/hr × 75min = $0.69` worst case at the cap. Realistic 4090 at `$0.40/hr × ~60min ≈ $0.40`. Even three full nights stay under $6. The watchdog (`MAX_MINUTES`) is the absolute ceiling — billing CANNOT exceed `MAX_DPH × MAX_MINUTES/60`.

```bash
# print the ceiling before you spend anything:
python3 -c "print('ceiling $', round(0.55*75/60, 2))"   # -> $0.69
```

---

## 1. Pre-flight checklist (PREVENTS the burn — do every item)

```bash
# 1.1 — Vast CLI + auth present
which vastai && vastai --version
export VAST_API_KEY=…            # from vast.ai/account ; nocturne's need_key() exits 2 if unset
vastai set api-key "$VAST_API_KEY"

# 1.2 — SSH key REGISTERED ON THE VAST ACCOUNT *before* any create (Vast requires this).
#        nocturne's ensure_ssh_key() does this idempotently, but verify it landed:
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C nocturne@vaked
vastai create ssh-key "$(cat ~/.ssh/id_ed25519.pub)" 2>/dev/null || true
vastai show ssh-keys | grep -q "$(awk '{print $2}' ~/.ssh/id_ed25519.pub | cut -c1-40)" \
  && echo "OK: key registered" || { echo "ABORT: key not registered"; exit 1; }

# 1.3 — Pick the cheapest VIABLE GPU sized for the model (single 24GB card).
export GPU_NAME=RTX_4090 MAX_DPH=0.55 NUM_GPUS=1 DISK_GB=64 MIN_RELIABILITY=0.95
bash tools/nocturne/provision.sh search        # prints cheapest offers under the cap; abort if none
#  -> require: rentable=true, direct_port_count>=1, cuda_max_good>=12.8, dph_total<=0.55

# 1.4 — Confirm you are NOT on-demand-vs-spot by accident. nocturne `create` has no --bid,
#        so it defaults to ON-DEMAND (correct — spot can be reclaimed mid-run and leak cost). Keep it.

# 1.5 — OpenRouter key present (driver refuses to rent without it — nocturne.py:60):
[ -n "$OPENROUTER_API_KEY" ] || { echo "ABORT: OPENROUTER_API_KEY unset"; exit 1; }

# 1.6 — Confirm no leaked boxes are ALREADY billing from a prior failed night:
vastai show instances --raw | python3 -c 'import json,sys; [print("LEAK:",i["id"],i["actual_status"],i.get("dph_total")) for i in json.load(sys.stdin)]'
#  -> destroy any survivors: vastai destroy instance <id> -y
```

If 1.6 shows ANY instance, destroy it before renting a new one — that is exactly the $10 leak from last week still on the clock.

---

## 2. The smoke test (<$0.50) — validate SSH + TEARDOWN before the real run

Two layers. Do BOTH before spending real training time.

### 2a. Zero-cost dry-run (no GPU at all — exercises the whole pipeline)

```bash
# provision.sh --dry-run prints the plan + ceiling, rents nothing, exits 0:
bash tools/nocturne/provision.sh --dry-run rent

# NOCTURNE_DRY_ACT=1 runs the FULL nocturne pipeline with no GPU/no spend
# (driver synthesizes results.jsonl locally; harvest->gate->ledger all run):
NOCTURNE_DRY_ACT=1 python3 tools/nocturne/nocturne.py run --once
```

### 2b. Real cheapest-box smoke ($0.50 cap) — proves SSH readiness + trap teardown

Rent the cheapest box, prove SSH actually connects (the thing that failed last week), then destroy. Use the **corrected connect sequence in §3** — do NOT use the current bare `provision.sh rent` poll, which breaks the moment `actual_status==running` and fires SSH into a not-yet-listening sshd.

```bash
export GPU_NAME=RTX_3090 MAX_DPH=0.30 MAX_MINUTES=10   # tiny, cheap, short
# Run the hardened rent+probe+teardown wrapper below (§3 + §5).
# Success criterion: "SSH READY" prints, `uptime` returns over ssh, box is destroyed,
# and §1.6 shows zero survivors afterwards. Cost: a few cents.
```

If 2b does not print `SSH READY` and end with zero survivors, STOP — fix the connect/teardown path before committing the real run.

---

## 3. The CORRECT connect sequence (fixes the primary + secondary root cause)

The current `provision.sh` poll (lines 85–91) breaks on `actual_status==running && -n ssh_host` and `nocturne.py` immediately `ssh mkdir`s. On Vast, `running` only means the container started — **sshd is not yet accepting**, and `--direct` coords arrive AFTER `running` (Vast often returns a transient proxy `ssh5.vast.ai` first). Replace the wait with a **re-reading sshd-readiness probe** that uses `nc -z` on the **mapped port** (not 22) and a real `ssh true` with `ConnectTimeout`.

```bash
# ---- hardened wait: poll for running, THEN re-read coords and probe sshd ----
wait_running_and_ssh() {        # $1 = instance id
  local ID="$1" HOST PORT STATUS i
  # phase A: wait for actual_status=running (up to 10 min)
  for i in $(seq 1 60); do
    STATUS=$(vastai show instance "$ID" --raw | python3 -c 'import json,sys;print(json.load(sys.stdin).get("actual_status"))')
    [ "$STATUS" = "running" ] && break
    sleep 10
  done
  [ "$STATUS" = "running" ] || { echo "never running"; return 1; }

  # phase B: RE-READ coords every loop (do NOT freeze them at first-running) and
  #          probe that sshd actually accepts on the MAPPED port. Up to ~5 min.
  for i in $(seq 1 30); do
    read -r HOST PORT <<<"$(vastai show instance "$ID" --raw | \
      python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("ssh_host") or "", d.get("ssh_port") or "")')"
    if [ -z "$HOST" ] || [ -z "$PORT" ]; then sleep 10; continue; fi
    # --direct sanity: reject the transient proxy host; wait for the direct forward
    case "$HOST" in ssh*.vast.ai) echo "proxy coords ($HOST) — waiting for direct"; sleep 10; continue;; esac
    # TCP probe on the MAPPED port (NOT 22):
    nc -z -w 5 "$HOST" "$PORT" 2>/dev/null || { sleep 10; continue; }
    # real sshd handshake with a bounded timeout:
    if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
           -o ServerAliveInterval=30 -o ServerAliveCountMax=4 -o BatchMode=yes \
           -p "$PORT" "root@$HOST" true 2>/dev/null; then
      echo "SSH READY $HOST $PORT"
      printf '%s %s %s\n' "$ID" "$HOST" "$PORT" > tools/nocturne/state/.instance
      return 0
    fi
    sleep 10
  done
  echo "sshd never accepted"; return 1
}
```

Key differences from the burned version:
- TCP-probe the **mapped `ssh_port`**, never hardcode 22.
- **Re-read** `ssh_host`/`ssh_port` each loop — never freeze the first (often proxy) value.
- Reject `ssh*.vast.ai` proxy host when `--direct` was requested.
- Real `ssh … true` with `-o ConnectTimeout=15` so a pre-sshd port can't hang the call.
- `-o StrictHostKeyChecking=accept-new` (accept new host key once, no churn, no interactive hang). nocturne's existing `StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null` also works for throwaway boxes; `accept-new` is the safer default if you want any host-key continuity.

Only after `SSH READY` prints does any `scp`/`ssh mkdir`/driver step run.

---

## 4. The fine-tune step (nanoGPT-scale, matches the autoresearch loop)

The harness IS the fine-tune: `prepare.py` downloads shards + trains the BPE tokenizer once; `train.py` is a single-GPU nanoGPT-scale run that emits `val_bpb`; `driver.py` runs the mutate→train→keep/discard loop, reserving wall for the confirm phase, then re-confirms the best on `NOCTURNE_CONFIRM_SEEDS` seeds. This fits 24GB and the $6 budget — no model download, no LoRA plumbing needed; it's already nanoGPT-class.

```bash
# on the box (driven by nocturne.py provision_run_real, but here explicit for clarity):
ssh … "mkdir -p /workspace/nocturne"
scp … harness/ driver.py program.md onstart.sh nocturne.env  -> /workspace/nocturne/
ssh … "NOCTURNE_HARNESS_DIR=/workspace/nocturne/harness bash /workspace/nocturne/onstart.sh"
#   onstart.sh: build-essential (torch.compile C compiler), libcuda.so symlink + cuda stubs,
#               install uv, `uv sync`, one-time `uv run prepare.py`.
ssh … "set -a; . /workspace/nocturne/nocturne.env; set +a; cd harness && python3 driver.py"
```

Budget-sized env file (`state/.nocturne.env`, 0600 — scp'd up, sourced on the box, never on argv):

```
LLM_API_KEY=$OPENROUTER_API_KEY
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-chat
NOCTURNE_WALL_SECS=3000
NOCTURNE_MAX_TRIALS=15
NOCTURNE_CONFIRM_SEEDS=2
```

### Checkpoint / result pull-back BEFORE teardown (non-negotiable)

```bash
scp … root@$HOST:/workspace/nocturne/harness/results.jsonl  tools/nocturne/state/results.jsonl
scp … root@$HOST:/workspace/nocturne/harness/train.py       tools/nocturne/state/candidate-train.py
# if train.py writes a checkpoint, pull it too BEFORE the trap fires:
scp … root@$HOST:/workspace/nocturne/harness/ckpt/best.pt   tools/nocturne/state/best.pt  || true
```

The harvest runs INSIDE the `try:` block; teardown is in `finally:` — so harvest always precedes destroy on the happy path. The smoke test in §2 proves the harvest+destroy ordering before you spend real training time.

---

## 5. HARD teardown guarantee (the actual fix for the catastrophic path)

The current watchdog `( sleep MAX_MINUTES*60; vastai destroy ) &` has **no nohup/disown/setsid** — on a GHA runner it dies with the job process group (job end, cancel, or the 360-min `timeout-minutes` SIGKILL). If the orchestrator is SIGKILLed, `finally:` never runs AND the watchdog is already dead → unbounded billing. Three independent layers fix this:

### Layer 1 — EXIT trap armed BEFORE create (kills any local-exit path)

```bash
ID=""
cleanup() {
  [ -z "$ID" ] && return
  vastai set api-key "$VAST_API_KEY" >/dev/null 2>&1
  for n in 1 2 3 4 5; do                     # retry — Vast 5xx/auth blips must not leak the box
    vastai destroy instance "$ID" -y >/dev/null 2>&1
    st=$(vastai show instance "$ID" --raw 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("actual_status","gone"))' 2>/dev/null || echo gone)
    case "$st" in gone|""|None) echo "[cleanup] $ID destroyed"; return;; esac
    sleep $((n*5))
  done
  echo "[cleanup] WARNING: $ID may still be billing — check vastai show instances"
}
trap cleanup EXIT INT TERM
# ...only now do you create:
ID=$(vastai create instance "$OID" --image "$IMAGE" --disk "$DISK_GB" --ssh --direct --raw \
     | python3 -c 'import json,sys;print(json.load(sys.stdin)["new_contract"])')
echo "$ID" > tools/nocturne/state/.instance     # persist id IMMEDIATELY after create
```

Note: this is the same shape as nocturne's `nocturne.py` `try/finally` (which already destroys on most paths) — the trap just guarantees it at the shell layer too, and the **retry + post-destroy confirm** fixes the silent-failure gotcha (`check=False` + no verification).

### Layer 2 — local `timeout` on the whole driver (bounds the active run)

```bash
timeout --signal=TERM $((MAX_MINUTES*60 - 300)) \
  ssh … "set -a; . nocturne.env; set +a; cd harness && python3 driver.py" || true
# TERM (not KILL) so the trap's cleanup still runs after the driver is stopped.
```

### Layer 3 — server-side self-destruct (survives runner death — the real catastrophe fix)

The only layer that survives the orchestrator/runner being SIGKILLed is one that runs **on the box itself**. Bake a self-destruct into the box so it dies even if nothing on your side is alive to kill it. Add to `onstart.sh` (or pass via `--onstart-cmd`):

```bash
# runs ON the box, detached, survives loss of all SSH/orchestrator/runner:
setsid bash -c 'sleep '"$((MAX_MINUTES*60))"'; \
  vastai set api-key "'"$VAST_API_KEY"'" 2>/dev/null; \
  vastai destroy instance $VAST_CONTAINERLABEL -y 2>/dev/null' </dev/null >/dev/null 2>&1 &
# (or use Vast's scheduled destroy / --onstart self-kill if available on the account)
```

This is the layer last week did NOT have. With it, even a 6-h GHA SIGKILL leaves the box self-destructing at `MAX_MINUTES`. Billing cap = `MAX_DPH × MAX_MINUTES/60` no matter what.

### Layer 4 — billing cap as backstop

Set an account-level spend alert / cap in the Vast dashboard at **$6**. It is the last net if all three code layers somehow fail.

---

## 6. Run it (real)

```bash
# all envs from §0/§1 exported, smoke test (§2) passed, leak check (§1.6) clean:
python3 tools/nocturne/nocturne.py run --once
# nocturne.py: provision -> upload -> bootstrap -> drive -> harvest -> finally:destroy -> ledger -> gate
# Verify after:
vastai show instances --raw | python3 -c 'import json,sys;print("survivors:",len(json.load(sys.stdin)))'  # MUST be 0
tail -1 tools/nocturne/state/events.jsonl   # MUST show a teardown event
```

After the run, gate.py judges results vs the committed baseline `val_bpb` with confirm-seed re-confirmation + novelty; ESCALATE drafts a swe_af hand-off, else ledgers an abstain.

---

## 7. Failure-mode table (each past failure → guardrail)

| Past failure (last week) | Root cause | Guardrail in this runbook |
|---|---|---|
| SSH fired before sshd up → `Connection refused` | poll breaks on `running` only; no readiness probe | §3 phase-B: `nc -z` on mapped port + `ssh … true -o ConnectTimeout=15` until exit 0 before any scp/ssh |
| `ssh` hung on TCP connect to pre-sshd port | no `ConnectTimeout`/`ConnectionAttempts` in SSHOPT | §3: `-o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=4` |
| Coords pointed at proxy `ssh5.vast.ai`, direct path never accepted key | `--direct` coords arrive after `running`; loop froze early/proxy value | §3 phase-B: re-read coords each loop + reject `ssh*.vast.ai` host |
| Wrong port (tried 22) | — (already handled, but verify) | §3 uses Vast's mapped `ssh_port` for both `nc` and `ssh -p` |
| Interactive host-key prompt hung non-TTY ssh | host-key churn | `-o StrictHostKeyChecking=accept-new` (or nocturne's `=no -o UserKnownHostsFile=/dev/null`) |
| Box leaked + billed unbounded after runner SIGKILL | watchdog subshell dies with the runner; `finally` skipped on SIGKILL | §5 Layer 3 server-side `setsid` self-destruct (survives runner death) + Layer 1 EXIT trap armed before create |
| Teardown "succeeded" but box stayed up | destroy `check=False`, no retry, no post-destroy verify | §5 Layer 1: retry ×5 + post-destroy `show instance` confirm |
| Instance id lost between create and `.instance` write | `set -e` abort after create, before line 92 | §5: write id to `.instance` IMMEDIATELY after create; trap uses `$ID` captured at create |
| H100 × 180 min = $9 over budget | oversized GPU + clock | §0: `RTX_4090`, `MAX_DPH=0.55`, `MAX_MINUTES=75` → $0.69 ceiling |
| Spot/interruptible reclaimed mid-night, leaked | implicit on-demand (no `--bid`) | §1.4: keep on-demand explicitly; never add `--bid` |
| Old leaked box still billing into the new night | no pre-run leak check | §1.6: list + destroy survivors before renting |
| Spent before validating SSH/teardown path | no smoke gate | §2: zero-cost dry-run + <$0.50 real smoke that must end with 0 survivors |
