# Self-hosted runners for the agent fleet

Run the Vaked agent fleet on owner-controlled GCP runners for speed and
headroom, while keeping GitHub-hosted runners as the safe default. Opt in by
setting one repository variable; opt out by clearing it.

## The `AGENT_RUNNER` variable

Each agent workflow selects its runner with:

```yaml
runs-on: ${{ vars.AGENT_RUNNER || 'ubuntu-latest' }}
```

- **Opt in:** Settings -> Secrets and variables -> Actions -> Variables ->
  set `AGENT_RUNNER` to your runner's label (e.g. `self-hosted`, or a custom
  label like `gke-arc`). Every agent job then targets that label.
- **Opt out / default:** unset or clear `AGENT_RUNNER`. Jobs fall back to
  GitHub-hosted `ubuntu-latest`. This is the default, behavior-safe state.

The variable is a repository **variable**, not a secret — it holds only a
runner label, nothing sensitive.

## Fallback semantics

GitHub has **no native auto-offline fallback** for `runs-on`. If
`AGENT_RUNNER` points at a label with no online runner, matching jobs simply
**queue** until a runner appears (or the run times out) — they do not silently
fall back to GitHub-hosted.

The practical control is the variable itself: flip `AGENT_RUNNER` back to
unset (or to a label backed by online runners) to restore GitHub-hosted
execution. Treat it as a manual switch, not an automatic failover.

## Provisioning (Path A — GitHub Actions runners on GCP)

Recommended approaches:

- **Actions Runner Controller (ARC) on GKE** — Kubernetes-native, scales
  runner pods on demand. Preferred for fleet-scale.
- **GCE managed instance group** — simpler; a pool of VMs each running the
  GitHub Actions runner agent.

Guidance:

- **Use ephemeral runners** (fresh runner per job). Avoids state leaking
  between agent runs and reduces the blast radius of a compromised job.
- Tag runners with the label you put in `AGENT_RUNNER`.

This path does **not** use the owner's existing GCP Cloud Build worker pools.
Cloud Build is a separate CI system; reusing it would require net-new
`cloudbuild.yaml` plus Workload Identity Federation (WIF) — deferred, not part
of this setup.

## Auth note

WIF (GitHub -> GCP federation) is **not required** for Path A. Self-hosted
runners dial **out** to GitHub and register via a GitHub App or a runner
registration token — GitHub never needs inbound access to GCP. WIF only
matters if an **agent itself** calls GCP APIs from within a job; for plain
runner provisioning it is unnecessary.

## Security hygiene

- **Private repo lowers the fork-PR RCE risk.** Untrusted fork PRs are the
  classic self-hosted-runner attack vector; a private repo materially reduces
  that exposure.
- **Prefer ephemeral runners** — one job per runner, then discard.
- **Avoid mounting the Docker socket.** Mounting `/var/run/docker.sock` into a
  job effectively grants root-on-host if that job is compromised. Note that
  `appleboy/telegram-action` mounts the Docker socket — keep such actions on
  GitHub-hosted runners, or replace them, when running self-hosted.
- **Constrain egress** with the repo's own `agent_guardd` deny-by-default
  network policy on the runner hosts.

## Coverage

**Covered (21 agent-fleet workflows):**
`fleet-introspect`, `docs-keeper`, `swe-af`, `ralph-tracks`, `cleanup`,
`pr-review`, `merge-train`, `optitron-crawl`, `vaked-ci-respond`, `nocturne`,
`label-tagger`, `pr-review-audit`, `provost-build`, `provost`,
`pr-review-build`, `label-tagger-build`, `claude`, `swe-af-build`,
`swe-af-orchestrator-build`, `landing-guru`, `pr-self-checkin`.

**Intentionally excluded (stay on `ubuntu-latest`):**

- Nix / Zig CI: `ci-gate`, `spec-tests`, `vakedz-ci`, `diagrams`.
- Social: `social-post`, `telegram-post`, `telebot`.
