# L1 / Frida evidence dev environment (M3)

The L1 layer (LD_PRELOAD / Frida) is **advisory, bypassable, evidence-only** —
per `prompts/carcerd-defense-sandbox-sprint.md`: "LD_PRELOAD is not a security
boundary… use it only as an advisory, bypassable, evidence-emitting L1 layer."
The real boundary is L2 (eBPF/seccomp), owned by the daemon track. This doc sets
up the *dev environment* to produce L1 evidence that feeds the kernel's
**observed** gate (declared ≈ observed). It does not enforce anything.

## Why a container

LD_PRELOAD, `ptrace`/Frida-attach, seccomp, and eBPF are **Linux+glibc**. The M1
host (macOS, `DYLD_INSERT_LIBRARIES`, no eBPF) cannot run them, and the project
rule is **never build/enforce on the developer machine**. So L1 work runs in a
local Linux container via **colima** (Docker engine on a Linux VM on macOS).

> RAM note: colima starts a Linux VM. With Ollama also resident (~6–8GB), watch
> total memory. Stop Ollama (`ollama stop <model>`) before a heavy container
> session, or give colima a small VM (`colima start --memory 4`).

## One-time setup

```bash
brew install colima          # docker CLI already present
colima start --cpu 2 --memory 4 --disk 20      # small VM to respect the host
# build the L1 image (inside the colima Docker engine)
docker build -f tools/dogfood/Dockerfile.l1 -t vaked-dogfood-l1 .
```

## Produce observed effects with Frida

Frida spawns the target and needs to ptrace it, hence `--cap-add=SYS_PTRACE`:

```bash
docker run --rm -it --cap-add=SYS_PTRACE \
  -v "$PWD":/repo -w /repo vaked-dogfood-l1 \
  python3 tools/dogfood/observe_frida.py --out /tmp/observed.json -- \
    <the command that applies the transition>
cat /tmp/observed.json     # {"writes":[...], "deletes":[...]}
```

`observe_frida.py` hooks glibc `open/openat/creat/unlink(at)`, classifies
write-intent opens and deletes, maps them to repo-relative paths, and emits the
`observed_effects` record.

## Wire it into the judge

The kernel's **observed** gate is already implemented and tested: pass the
observed record to `kernel.judge(..., observed=<dict>)`. It rejects any
transition whose Frida-observed writes are **not a subset of** the declared
writes — i.e. the proposer touched a file it did not declare. The end-to-end
integration step (have `kernel.py propose` shell `observe_frida.py` around the
apply inside the container) is the remaining M3 wiring; the gate logic itself
needs no further code.

## Status

- `observe_frida.py` + `Dockerfile.l1` written and committed.
- Kernel-side observed gate: implemented + unit-tested (`test_kernel.py:
  test_reject_observed_exceeds_declared`, `test_observed_subset_accepts`).
- Live container run + propose-around-observer wiring: **deferred** — run when
  the host has RAM headroom (Ollama scare, 2026-06-14). colima not yet installed.
