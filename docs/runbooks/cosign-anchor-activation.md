# Runbook — Activate the cosign/Rekor deploy anchor (no log-reading required)

You said you're not great with logs. This is written so you never have to read one.
Goal: after the `honesty-anchor` workflow runs for the first time, tell `verify-seals.sh`
*who* signed the manifest, by setting one repository variable: `COSIGN_IDENTITY`.

You do **not** need to understand the run output. The identity is **deterministic** — it's
just a fixed string built from the repo name and the workflow path. You can set it blind.

## The one value you need

```
https://github.com/peterlodri-sec/vaked-base/.github/workflows/honesty-anchor.yml@refs/heads/main
```

That is the `COSIGN_IDENTITY`. It does not change between runs (only if you rename the repo,
move the workflow file, or run it from a non-`main` branch).

## Set it (one command, no logs)

```
gh variable set COSIGN_IDENTITY \
  --repo peterlodri-sec/vaked-base \
  --body "https://github.com/peterlodri-sec/vaked-base/.github/workflows/honesty-anchor.yml@refs/heads/main"
```

Or in the browser: **Repo → Settings → Secrets and variables → Actions → Variables tab →
New repository variable** → Name `COSIGN_IDENTITY`, Value = the URL above.

## Confirm it took (still no logs)

```
gh variable list --repo peterlodri-sec/vaked-base | grep COSIGN_IDENTITY
```

## How to know the first run actually worked (one glance, not logs)

```
gh run list --repo peterlodri-sec/vaked-base --workflow honesty-anchor.yml --limit 1
```

Look at the first column only: a green **completed/success** = it signed and logged to Rekor.
A red **failure** = it didn't (most likely cosign permissions). You don't need the log body —
just the green/red.

## If you ever want to prove an artifact is anchored (optional, advanced)

The bundle is committed to the repo at
`the-honest-swarm-researcher/SEALS.sha256.cosign.bundle` by the `honesty-anchor`
workflow after each successful signing run, so it is present in any checkout of
`main`. No manual download step is required.

```
cosign verify-blob \
  --bundle the-honest-swarm-researcher/SEALS.sha256.cosign.bundle \
  --certificate-identity "https://github.com/peterlodri-sec/vaked-base/.github/workflows/honesty-anchor.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  the-honest-swarm-researcher/SEALS.sha256
```

Output `Verified OK` = the live manifest matches what was signed and logged. Anything else =
it doesn't. (Note: the CI OIDC issuer is `https://token.actions.githubusercontent.com` for
GitHub-Actions identities — different from a human browser login's issuer.)

## What this buys you

`verify-seals.sh` (Anchor 2) stays a no-op until `COSIGN_IDENTITY` is set. Once set, it will
verify the cosign bundle against the Rekor transparency log on every run — so a manifest
re-sealed without re-anchoring fails the build, witnessed by an append-only log you don't own.
The GPG-signed tag (Anchor 1) already gives you this today; cosign adds the external witness.
