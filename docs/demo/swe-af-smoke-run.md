# swe-af fan-out batch — live smoke run record (2026-06-14)

First live end-to-end run of the [swe-af fan-out batch orchestrator](../../vaked-agents/ci/swe-af-orchestrator).
For debug, demo, and publication.

## What it proves

A task enqueued on a NATS work-queue was drained by the orchestrator on a worker
host, which cloned the repo, ran the existing `vaked-swe-af` agent (plan + code)
with **all model calls through the tailnet Aperture gateway**, applied the change,
pushed a branch, and **opened a draft PR** — with an eventd hash-chain audit and
live `swe.af.status.*` events. POLA held: draft only, never merged; no secrets
persisted (gh keyring + `HOME`); cost-tracked.

## Evidence

- **Draft PR:** [peterlodri-sec/vaked-base#193](https://github.com/peterlodri-sec/vaked-base/pull/193)
  — `swe_af: docs: add swe-af smoke marker file`
- **Branch:** `swe-af/issue-192` (`0becc57`); **issue:** #192
- **Diff produced (exact):**
  ```diff
  +++ b/docs/SWE_AF_SMOKE.md
  @@ -0,0 +1 @@
  +swe-af smoke run OK
  ```
- **eventd:** `chain OK (3 entries, tail d98d136f5aedb629…)`
- **Task:** `8954bf2f-fb02-44ea-820d-3bab2f446df0` → `task done` in ~12s after lease.

## Environment

| | |
|---|---|
| Worker | bench-node (Ubuntu 26.04, tailnet `tag:agents`, 8 vCPU/15 GB) |
| Orchestrator | `swe-af-orchestrator 0.1.0+e9bdfe5`, `systemd-run` transient unit, pool=3 |
| Model gateway | Aperture `https://nixai-base.tail2870dc.ts.net/v1` (Tailscale identity, no key) |
| Models | plan + code = `deepseek/deepseek-v4-flash` (smoke; cheap) |
| Queue | throwaway JetStream `nats:latest -js` on `:4223` (self-contained) |
| GitHub auth | gh keyring (read: issue view; write: broker PR) — no token persisted |

## Replay the recording

`docs/demo/swe-af-smoke.cast` is an [asciinema](https://asciinema.org) v2 cast
(deterministic, regenerate with `scripts/demo/gen-cast.py`).

```bash
asciinema play docs/demo/swe-af-smoke.cast          # local replay
asciinema upload docs/demo/swe-af-smoke.cast        # shareable URL (publication)
agg docs/demo/swe-af-smoke.cast swe-af-smoke.gif    # -> GIF for READMEs/slides
```

Embed (asciinema-player) in docs/sites:
```html
<script src="https://cdn.jsdelivr.net/npm/asciinema-player@3/dist/bundle/asciinema-player.min.js"></script>
<div id="cast"></div>
<script>AsciinemaPlayer.create('swe-af-smoke.cast', document.getElementById('cast'));</script>
```

## Re-run live (debug / demo)

`scripts/demo/swe-af-smoke.sh` drives the deployed orchestrator (enqueue → watch →
print the draft PR). Deploy prereqs: `vaked-agents/ci/swe-af-orchestrator/deploy/README.md`.

```bash
NATS_URL=nats://127.0.0.1:4223 REPO=peterlodri-sec/vaked-base \
  scripts/demo/swe-af-smoke.sh            # creates a fresh smoke issue, or pass an ISSUE#
# record it:
asciinema rec -c 'NATS_URL=... scripts/demo/swe-af-smoke.sh' run.cast
```

> Each live run opens a real (draft) PR. Close the smoke issue + PR after.
