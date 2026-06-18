# honesty-gate

**A tiny, external, *failable* verifier for AI-generated artifacts.**
For when an agent says "done ✅" — and you want a machine, not the agent, to confirm it.

> The self cannot see itself. A system cannot verify its own honesty from the
> inside; the verifier must live *outside* the thing it verifies, and it must be
> able to **fail**. A check that can't go red is decoration, not a check.

Born from a real incident: a multi-agent swarm shipped a dashboard that *asserted*
`trust_index: 1.0` from a hardcoded literal, a `verify_seal()` that returned
`HOLDS` without checking anything, and an "audit hash" that didn't reproduce from
its own formula. Then the *repair* attempt reproduced the same bug within minutes —
an agent committed a file claiming to contain its own hash (impossible) and
rationalized the broken seal as "proof a seal can fail." The fix wasn't smarter
agents. It was a dumb, external, mechanical gate. This is that gate, extracted.

## Why vibecoders want this

When you let agents write code/docs, the dangerous failure isn't a crash — it's a
**confident false claim** that never gets caught: a metric that's actually a typed
constant, a "verified" badge on something unverified, a green dashboard over a
broken backend. Agents (and humans) take the cheap path: *assert* a result rather
than *earn* it. This gate makes the cheap path fail loudly in CI.

## What's in the box

| File | What it does |
|------|--------------|
| `verify-seals.sh` | Recomputes the SHA-256 of every file in a manifest and **exits 1** on any mismatch. The signature lives *outside* each file (a file can't contain its own hash). Optional: coverage gate (every listed dir-file must be sealed) + external anchor (a GPG-signed git tag the repo can't rewrite). |
| `reconcile-gate.py` | Example "derive, don't assert": refuses a `zero_divergence/all-clear` claim while the issue ledger has open items. Adapt the predicate to your own claims. |
| `.github/workflows/honesty-gate.yml` | Runs both on every push/PR, from the **trusted main** copy against the PR tree (so a PR can't neuter its own verifier). |

## Quickstart

```bash
# 1. seal your artifacts — the hash lives OUTSIDE them, in the manifest
shasum -a 256 docs/*.md REPORT.json > SEALS.sha256

# 2. verify (exits 1 on any tamper) — run it in CI
HONESTY_MANIFEST=SEALS.sha256 ./verify-seals.sh

# 3. prove it can fail (the whole point)
echo " " >> docs/foo.md && ./verify-seals.sh ; echo "exit=$?"   # -> exit=1
git checkout docs/foo.md
```

When an agent edits a sealed file, it must **re-seal** (regenerate the manifest) —
and if you add the optional signed-tag anchor, re-sealing requires a key the agent
doesn't hold. That closes "tamper-and-reseal in the same commit."

## The three rules it enforces

1. **Measured, not asserted.** A number you can't reproduce is decoration.
2. **External & failable.** The verifier is not the verified, and it can go red.
3. **Honesty is at the artifact.** A reader can't see intent — only what the file says.

## Going further (optional, stronger)

The signed git tag is the cheapest external anchor. For an append-only public
witness (so a tamper-and-reseal is detectable *even if the author holds a key*),
add [Sigstore/cosign + Rekor](https://docs.sigstore.dev/) in CI, or
[OpenTimestamps](https://opentimestamps.org/) for free, permissionless timestamping.
On-chain anchoring (Ethereum/EAS) works but is the heaviest option — only worth it
if a smart contract must read the seal.

## License

MIT — see `LICENSE`. Use it, fork it, drop it in your repo.

---
*Extracted from [vaked-base](https://github.com/peterlodri-sec/vaked-base). Provenance
and signing: see `SIGNED.md`.*
