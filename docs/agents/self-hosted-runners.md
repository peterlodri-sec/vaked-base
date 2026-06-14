# Self-hosted runners & Cloud Build for the agent fleet

The Vaked agent fleet runs on the same infrastructure as the rest of the
`peterlodri-sec` fleet (crabcc, agentfield-os, rag-stack, …): **Hetzner
self-hosted GitHub Actions runners** for the agent/build jobs, with **GCP Cloud
Build** as a separate path for cached Nix builds. A few light/external jobs stay
on GitHub-hosted runners.

## Status

> **Not yet enabled.** The agent/build workflows currently run on
> `ubuntu-latest`. They were flipped to `[self-hosted, linux, hetzner]` once but
> the jobs sat queued with no runner picking them up, so they were reverted.
> Flip them back to the fleet label below once a Hetzner runner is confirmed
> online and registered for `vaked-base`.

## Runner label convention (fleet standard)

Agent and build jobs target the fleet-standard label array:

```yaml
runs-on: [self-hosted, linux, hetzner]
```

This matches crabcc and the rest of the fleet (see
`crabcc-labs/crabcc/.github/workflows/README.md`). Other labels in fleet use:

- `[self-hosted, linux, hetzner, gh-runner]` — pin to specific runner boxes.
- `[self-hosted, linux, light]` — light/fast jobs.
- `[self-hosted, <repo-slug>]` — per-repo dedicated runners.
- `[self-hosted, nix, ARM64]` — the Nix module's auto OS/arch labels.

## Provisioning (Hetzner, not GCP)

Runners are provisioned two ways in the fleet — either is fine:

- **`peterlodri-sec/nix-base` → `modules/github-runners.nix`** (canonical):
  nix-aware self-hosted runners, **auth via the GitHub App through
  `gh-app-broker` (no PAT on disk)**. The runner auto-applies its OS/arch
  default labels at runtime, so jobs target e.g.
  `runs-on: [self-hosted, nix, ARM64]` correctly on x86 or ARM. Enabled on the
  Hetzner host.
- **`peterlodri-sec/hetzner-server` → `docker-compose.yml`**: per-repo runner
  containers (~50 MB idle each; ~3 per repo), labelled with a per-repo slug.

Runner operations are themselves workflows in the fleet (cf. crabcc):
`runner-gc`, `runner-health`, `provision-runner-volume`, and ephemeral
single-job runners (`bench.yml`) that self-deregister after one job. Prefer
ephemeral runners where practical — one job per runner reduces the blast radius
of a compromised job.

## Coverage in this repo

**On `[self-hosted, linux, hetzner]` (19 agent/build workflows):**
`fleet-introspect`, `docs-keeper`, `swe-af`, `ralph-tracks`, `cleanup`,
`pr-review`, `merge-train`, `optitron-crawl`, `vaked-ci-respond`, `nocturne`,
`label-tagger`, `pr-review-audit`, `provost-build`, `provost`,
`pr-review-build`, `label-tagger-build`, `swe-af-build`,
`swe-af-orchestrator-build`, `landing-guru`.

**On `ubuntu-latest` (deliberately GitHub-hosted):**

- `claude` — matches crabcc; the OAuth-token assistant stays on hosted runners.
- `pr-self-checkin` — the watchdog must stay reliable even if the Hetzner fleet
  is offline.
- Nix / Zig CI: `ci-gate`, `spec-tests`, `vakedz-ci`, `diagrams`.
- Social: `social-post`, `telegram-post`, `telebot`.

## GCP Cloud Build (Nix build + attic cache)

GCP is **not** used as a GitHub runner; it is a separate path for fast, cached
Nix builds, mirroring `peterlodri-sec/nix-base/cloudbuild.yaml`:

- **Private pool:** `nix-fleet-c3-pool` (c3-standard-8, europe-west2).
- **Project:** `datapy-spider`. Secrets in Secret Manager (same project).
- **Trigger:** push to `main` / `feat/*` (configured in the Cloud Build console).
- **What it does:** `nix build` the flake outputs (incl. the `vakedos` NixOS
  host) and push the closure to the attic binary cache.

See `cloudbuild.yaml` at the repo root. Confirm the attic cache name and Secret
Manager secret names against `nix-base/cloudbuild.yaml` before enabling the
trigger — they are marked as `TODO(confirm)` in the file.

## Security hygiene

- **Private repo lowers the fork-PR RCE risk** — untrusted fork PRs are the
  classic self-hosted-runner attack vector; a private repo materially reduces it.
- **Prefer ephemeral runners** — one job per runner, then discard.
- **Avoid mounting the Docker socket.** Mounting `/var/run/docker.sock` grants
  root-on-host if a job is compromised; `appleboy/telegram-action` mounts it, so
  those jobs stay on GitHub-hosted runners (the social workflows above).
- **Constrain egress** with the repo's own `agent_guardd` deny-by-default
  network policy on the runner hosts.
