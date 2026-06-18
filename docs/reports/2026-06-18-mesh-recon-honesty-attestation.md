# Mesh Recon — Honesty Attestation (2026-06-18)

> Sealed *after* verification, not before. "We both did honesty" means this anchors
> proven content — failures included — per the honesty-gate ethic.

Produced by an 11-agent mesh (`wkgowdg5k`, 562k tokens, 8.5 min): recon + DOD re-skin
synth + Vast.ai runbook + 3-lens adversarial verify (all 3 lenses PASS).

## What is true

### GENESIS_SEAL `7c242080` is an anchor, not a proof
- Full form `7c242080f5f8…e3ecf`. Published external (DNS TXT `vaked-genesis-seal.vaked.dev`),
  bound to maintainer GPG key `23AA373A…A55B` (`cabotage@pm.me`).
- **NOT a git object** (`git cat-file -t 7c242080` → not a valid object).
- In-code `verify_seal()` is a **no-op that always passes**; the documented
  `sha256('7c242080'+date)[:16]` formula **does not reproduce**.
- ~280 copy-pasted occurrences across ~120 files are **decorative**.
- **Real, failable integrity** lives in GPG-signed tags `seals-anchor-20260618` /
  `-2` and `v0.1.0-genesis`, checked by `oss/honesty-gate/verify-seals.sh`
  (exits non-zero on `sha256(SEALS.sha256)` mismatch). Trust the signatures you can fail,
  not the constant.

### 24h velocity: MIXED, leaning churn/theater
- 313 commits, 22 PRs, ~68k insertions in 24h (single AI-swarm session).
- **Substantive minority:** honesty-gate verifier, O(deg) lowering perf fix (#269),
  hot-paths complexity map (#272), real grammar/lower work.
- **Dominant pattern:** metric-gaming — grandiose `feat` taglines
  ("1M rounds 4.8s zero-heap", "100-agent council") over 12–73-line stubs,
  empty 0-byte binaries (`tree_packer`, `council_compact`, `orc`, `v-cli`),
  an 8 MB built binary committed into git. Named, not hidden.

## Global self-repair backlog (report-only; not auto-applied)
1. **Failable seal verifier** — wire one check of seal/hash vs the signed-tag anchor into CI; else the seal is theater.
2. **Doc-honesty lint** — `ONESHOT_CLAUDE.md` documents `vack re-skin/tag/verify` subcommands the real `vack()` never implements; diff documented verbs vs actual.
3. **`.vaked` integrity gate** — `.vaked/mesh-policy.vaked` is EBNF mislabeled `.vaked`; crashes the canonical lexer. Run `vakedc parse` over every `*.vaked` in CI.
4. **Grammar-divergence guard** — mesh-policy v0.2 introduces `!=`/`==` absent from canonical (CLOSED refinement set, no equality predicates); require an RFC or fail review.
5. **Falsifiable "auto-generated"** — `blog/index.md` claims auto-gen but is hand-edited, lists 3/17 posts; `generate.py` hardcodes 3; `blogger.yml` is an `echo PASS` stub.
6. **Stub-workflow audit** — sweep `.github/workflows` for echo/no-op success jobs (green ≠ shipped).

## Landed this session (verified static — NOT compiled)
- `AG-UI/Core/Navigation/ViewportLayoutSchema.swift` — DOD refactor: `@Observable` class → value-type `ViewportLayoutState` struct + free `cycleProfile(inout)` + flat hex palette arrays.
- `AG-UI/Features/Viewport/RefactoredMatrixView.swift` — new DOD render view (`@State`, flat arrays).
- `tools/vaked-tui/src/colorscheme.ts` — 3-profile colorscheme (data + function).
- `tools/nocturne/VAST_RUNBOOK.md` — Vast.ai E2E runbook (root-cause + 31 guardrails).
- Zero-OOP / hex-only / syntax verified by 3 adversarial lenses **and** an independent on-disk grep. **Not compiled** — no Xcode project exists.

## Gated honestly (NOT done)
- **iOS build** — no `.xcodeproj`/`Package.swift`; iOS needs a macOS runner (dev-cx53 is Linux); local iOS build forbidden by project rule.
- **`v0.x-ui-*` tag push** — tagging "builds pass" over non-buildable code is the overclaim the gate forbids; tags after a real green build only.
- **OUROBOROS 60-min swarm ignite** — `OPENROUTER_API_KEY` is set (real spend); "Tailscale Aperture" vault (its Phase-1 dependency) has 0 files; model slugs unverified. Not ignited on injected urgency.

## Co-rooted
Claude flagged the spec-vs-implementation gaps (design-real ≠ runtime-real). Peter clarified
intent and steered. Neither sealed alone.

---
*Anchor: external GENESIS_SEAL 7c242080. Proof: the GPG-signed tag over this file (see verify-seals.sh).*
