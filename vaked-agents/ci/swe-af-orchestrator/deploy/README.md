# swe-af-orchestrator — deploy runbook (worker host: bench-node)

The orchestrator runs **off cx53** on a worker host (bench-node primary). Execution
needs the worker to reach **Aperture** (tailnet-only) and **crabcc-nats**, so the
host must be on the tailnet. Apply these in order. Steps P1-P4 are the infra
prerequisites; they are gated on P1 (tailnet) and are operator-run where noted.

## P1 — join the worker to the tailnet (operator; interactive auth)

```sh
ssh bench-node 'curl -fsSL https://tailscale.com/install.sh | sh && \
  sudo tailscale up --advertise-tags=tag:agents'
```

Approve the node + `tag:agents` in the Tailscale admin console. Verify from the box:

```sh
ssh bench-node 'tailscale status | head; \
  curl -sS -o /dev/null -w "aperture=%{http_code}\n" \
    https://nixai-base.tail2870dc.ts.net/aperture/openapi.json; \
  (echo > /dev/tcp/100.73.72.35/4222) 2>/dev/null && echo nats4222=open'
```

The ACL already grants `tag:agents -> nixai-base:443` (Aperture) and
`tag:agents -> tag:server:4222` (NATS).

## P2 — Aperture grant for tag:agents (operator; Visual editor)

In the Aperture Visual editor (`https://nixai-base.tail2870dc.ts.net/ui/settings`),
add to `grants` and click Test -> Save (do NOT round-trip the config via the API —
GET redacts the provider key):

```hujson
{ "src": ["tag:agents"],
  "app": { "tailscale.com/cap/aperture": [ { "role": "user" }, { "models": "**" } ] } }
```

(Scope `models` tighter if preferred, e.g. `["anthropic/*","deepseek/*","openai/gpt-5.3-codex","qwen/*"]`.)

## P3 — tooling + binaries on the worker

```sh
# gh (broker step) — official apt repo
ssh bench-node 'sudo apt-get update && sudo apt-get install -y gh'
# vaked-swe-af agent (prebuilt; no rust toolchain on the box)
ssh bench-node 'gh release download swe-af-bin -R peterlodri-sec/vaked-base \
  -p vaked-swe-af-linux-x86_64 -O /tmp/vaked-swe-af && \
  sudo install -m755 /tmp/vaked-swe-af /usr/local/bin/vaked-swe-af'
# orchestrator + enqueue (from the swe-af-orchestrator-bin rolling release)
ssh bench-node 'for b in orchestrator enqueue; do \
  gh release download swe-af-orchestrator-bin -R peterlodri-sec/vaked-base \
    -p vaked-swe-af-$b-linux-x86_64 -O /tmp/$b && \
  sudo install -m755 /tmp/$b /usr/local/bin/swe-af-$b; done'
```

Note: `python3 -m eventd` audit only resolves when the task repo carries the
`eventd` module (i.e. vaked-base). For other target repos the audit append/verify
degrades gracefully (non-fatal). Install eventd globally on the worker if you want
audit for all repos: `pip install -e <vaked-base>/eventd` (or set `PYTHONPATH`).

## P4 — disk reclaim + scratch

```sh
ssh bench-node 'docker image prune -f; docker builder prune -f; df -h /'
# scratch dir is created by systemd StateDirectory=swe-af (/var/lib/swe-af)
```

## Install the units

```sh
ORCH=vaked-agents/ci/swe-af-orchestrator/deploy
scp $ORCH/swe-af.slice $ORCH/swe-af-orchestrator.service bench-node:/tmp/
ssh bench-node 'sudo mv /tmp/swe-af.slice /tmp/swe-af-orchestrator.service /etc/systemd/system/ && \
  sudo mkdir -p /etc/swe-af'
scp $ORCH/swe-af-orchestrator.env.example bench-node:/tmp/orchestrator.env
# edit /etc/swe-af/orchestrator.env: set GH_TOKEN (read) + SWE_AF_GH_WRITE_TOKEN (write)
ssh bench-node 'sudo mv /tmp/orchestrator.env /etc/swe-af/orchestrator.env && \
  sudo chmod 600 /etc/swe-af/orchestrator.env && \
  sudo systemctl daemon-reload && sudo systemctl enable --now swe-af-orchestrator'
```

## Smoke test

```sh
# enqueue one task (run where NATS is reachable; e.g. on the worker or via tailnet)
NATS_URL=nats://100.73.72.35:4222 swe-af-enqueue \
  --repo peterlodri-sec/vaked-base --issue <N>
# watch
ssh bench-node 'journalctl -u swe-af-orchestrator -f'
```

Expect: a draft PR from `swe-af/issue-<N>`, `swe.af.status.<task>.*` frames on the
bus (visible in the Sentinel Console once it subscribes `swe.af.>`), and — for
vaked-base targets — a clean `eventd verify`.

## Fan-out / load

`SWE_AF_POOL` bounds concurrency; the disk guard pauses intake when free space
< `SWE_AF_MIN_FREE_GB` or scratch > `SWE_AF_SCRATCH_CAP_GB`. Raise `SWE_AF_POOL`
once Aperture/OpenRouter rate limits are characterized (watch for 429s).
