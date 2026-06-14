# Spec — `ci-gate-build-extension`: build + test Rust and Zig in the CI gate

**Date:** 2026-06-14
**Status:** Planning artifact (work is dependency-blocked; not codeable now — see §7)
**Target file:** `.github/workflows/ci-gate.yml` (+ `.github/scripts/ci_classify.py`)
**Repo:** `peterlodri-sec/vaked-base`
**Related:** issue #7 (false-green / vacuous-green), WP3-S1 (`protocol/hcp/hcpbin`), WP4-S1 (`daemons/sandboxd`)

---

## 1. Objective

`ci-gate` is the only **REQUIRED** check (`.github/workflows/ci-gate.yml:20-21, 258-262`). Today it runs **only Python + Nix**: the `smoke` / `standard` / `full` jobs invoke `tests/smoke.py` and `tests/spec/run_all.py` (lines 117-118, 142-143, 161-164), and `nix-parse` / `nix-check` run `nix-instantiate` / `nix flake check`. **No job ever compiles Rust or Zig.**

The result is a verified vacuous-green for the two code subtrees that are about to receive the most work (WP3 Rust under `protocol/hcp/**`, WP4 Zig under `daemons/**`): a PR that touches only that code passes `ci-gate` without the code ever being built or tested. This is precisely the false-green issue #7 warns about.

**Empirically confirmed** (running `.github/scripts/ci_classify.py` helpers against current `HEAD`, see §3.1):

| Changed file | `changed_groups` | `is_non_src` | auto tier (≤20 LOC) | What actually runs |
|---|---|---|---|---|
| `protocol/hcp/hcpbin/src/lib.rs` | `{docs}` | `True` | **smoke** | grammar + doc tests only |
| `protocol/hcp/litany/src/lib.rs` (future) | `{docs}` | `True` | **smoke** | grammar + doc tests only |
| `daemons/sandboxd/src/main.zig` | `{other}` | `False` | **standard** | Python core compiler tests only |

So a small Rust hcpbin change classifies as **smoke** (because `protocol/` is in both `NON_SRC_PREFIXES` and the `docs` path-group), and a Zig daemon change classifies at most as **standard/full** — in every case the Rust/Zig code is never compiled.

**Goal:** make `ci-gate` fail when Rust under `protocol/hcp/**` fails to `cargo test`, or Zig under `daemons/**` fails to `zig build`, on the PRs that touch that code — without slowing down PRs that don't.

### Success in one sentence
A PR touching only `protocol/hcp/hcpbin/src/lib.rs` (any size) must produce `run_rust=true`, run `cargo test`, and the result must flow into the `ci-gate` aggregator's pass/fail decision; likewise a PR touching `daemons/sandboxd/**` must produce `run_zig=true` and run `zig build`.

---

## 2. Inputs / oracles

### 2.1 Code under gate (discovered, not hardcoded — see §4.4)
- **Rust:** every `Cargo.toml` under `protocol/hcp/` (today: `protocol/hcp/hcpbin/Cargo.toml`; WP3-S2 adds `protocol/hcp/litany/`). Each crate is **standalone** — it carries its own empty `[workspace]` table to detach from any parent (pattern seen in `vaked-agents/ci/provost/Cargo.toml`), and there is **no root `Cargo.toml` workspace**. So the gate invokes `cargo` per manifest, not once at the root.
- **Zig:** every `build.zig` under `daemons/` (today: `daemons/sandboxd/build.zig`). WP4 adds `daemons/agent-supervisord/`, `daemons/eventd/` (`docs/superpowers/plans/2026-06-14-wp4-kickoff.md:18`).

### 2.2 Test oracles (already in-repo, blind/adversarial — do not author new ones here)
- **hcpbin Rust:** `protocol/hcp/hcpbin/tests/golden.rs` — 50 tests across 3 suites; golden vectors derived **only** from RFC 0002. The file header and per-section comments cite the authoritative sections explicitly:
  - **§6.1** strict varint decode (`golden.rs:6, 317-318`)
  - **§6.1.1** worked examples / primitive types (`golden.rs:6, 22-24, 73-81, 139-142, 182-185`)
  - **§6.5** `hash` encoding (`golden.rs:6, 245-251`)
  - These are the byte-level oracles. The codec lives in `protocol/hcp/hcpbin/src/lib.rs`.
- **Zig daemons:** `zig build test` runs the in-source `test {}` blocks (`daemons/sandboxd/build.zig:20-26`; same pattern as `vakedz/build.zig:34-43`). `daemons/sandboxd/src/main.zig` is currently a stub with no tests, so the daemon gate's first job is **compile** (`zig build`), with `zig build test` added as those tests land (WP4-S1+).

### 2.3 RFC authority for the byte format (for reviewers reading the spec)
Per the corrected RFC layout (`protocol/rfcs/0002-hcplang.md`): the hcpbin byte encoding is **§6 ("hcpbin encoding rules")**, with worked golden vectors in **§6.1.1, §6.3.1, §6.6.1, §6.7.1, §10**. The frame header fields (kind/corr/stream/seq/end) are the **WIRE** layer (**RFC 0003**), explicitly **not** in hcpbin (RFC 0002 §4.2 + the §6 scope note). **There is no Appendix A.**

> Note: `docs/superpowers/plans/2026-06-14-wp3-kickoff.md:41-43` says "RFC 0002 §4 / Appendix A" and "varint, frame header, payload framing" in one crate — that wording is **stale**. This spec does **not** propagate it. The frame header is RFC 0003 (litany layer); hcpbin is primitives/§6 only. The gate cares about *building+testing* the crate, not about which RFC section the bytes come from, but the oracle citations above are the correct ones.

### 2.4 Existing CI machinery this extends
- `ci_classify.py` emits `GITHUB_OUTPUT` vars consumed by job `if:` guards. The **`run_nix_parse`** mechanism (`ci_classify.py:134`, `ci-gate.yml:181-184`) is the exact pattern to mirror for `run_rust` / `run_zig`.
- Hosted runner: **`ubuntu-latest`** (every job; e.g. `ci-gate.yml:45, 108, 133`). The "build target `dev-cx53`" in the kickoff docs is the *engineering* devshell, **not** the CI runner — see §7.

---

## 3. Design

### 3.1 Part A — `ci_classify.py` changes (the root-cause fix)

Two bugs cause the vacuous-green; both are in path classification.

**Bug 1 — Rust code is classified as `docs` and as non-src.**
`protocol/` is a prefix in **both** `NON_SRC_PREFIXES` (`ci_classify.py:43-47`) and the `docs` entry of `PATH_GROUPS` (`ci_classify.py:53`). `classify_paths` is first-match-wins over `PATH_GROUPS` (the `break` at line 67), and `language` (`vaked/ vakedc/ vakedz/`) does not match `protocol/`, so `protocol/hcp/hcpbin/src/lib.rs` falls to `docs`. Independently `is_non_src` returns `True`, so `auto_tier` returns `smoke` for a small change.

**Bug 2 — Zig daemons match no group.**
`daemons/` is in no `PATH_GROUPS` entry, so it falls to `"other"` and never triggers a build.

**Fix (surgical, mirrors existing style):**

1. Add two **code** groups to `PATH_GROUPS`, placed **before** `docs` so first-match-wins routes code correctly. `dict` preserves insertion order in Python 3.7+; the runner uses 3.12 (`ci-gate.yml:115`):

   ```python
   PATH_GROUPS = {
       "language": ("vaked/", "vakedc/", "vakedz/", "daemons/"),  # zig front-end + daemons are compiled code
       "rust":     ("protocol/hcp/",),       # Rust crates under protocol/hcp  ── MUST precede "docs"
       "nix":      ("nix/", "hosts/", "flake.nix", "flake.lock"),
       "docs":     ("docs/", "protocol/", "prompts/", "examples/evaluation/"),
       "agents":   ("vaked-agents/",),
       "tools":    ("tools/",),
       "tests":    ("tests/",),
       "ci":       (".github/",),
   }
   ```

   Rationale for placement:
   - `"rust"` before `"docs"` so `protocol/hcp/**` routes to `rust`, while `protocol/rfcs/**` and other `protocol/` paths still route to `docs` (longer, more specific prefix wins by ordering).
   - `daemons/` folded into `"language"` (the existing "compiled language code" group) rather than a new `"zig"` group, to minimise new vocabulary; the build trigger is derived separately (step 3). **Decision point for the implementer:** if a distinct `"zig"` group reads cleaner alongside `"rust"`, add `"zig": ("daemons/",)` before `docs` instead and trigger off `"zig" in changed_groups`. Either is acceptable; pick one and be consistent in the YAML guards.

2. Narrow `NON_SRC_PREFIXES` so Rust code is not treated as non-source. Replace the bare `"protocol/"` with the doc subtree only:

   ```python
   NON_SRC_PREFIXES = (
       "docs/", "protocol/rfcs/", "prompts/", ".github/", "CLAUDE.md",
       # ... unchanged tail ...
   )
   ```

   This stops `protocol/hcp/**` from forcing `only_non_src=True` → smoke. (`protocol/rfcs/**` and `protocol/hcp/README.md` are still doc-ish; if a `protocol/`-wide doc carve-out is desired, list the specific doc subdirs — do **not** restore the bare `protocol/` prefix, or Bug 1 returns.)

3. Compute the build triggers from `changed_groups`, **tier-independent** (a 5-line change can break compilation), and emit them. This mirrors `run_nix_parse` but **without** the `or tier in (full,extended)` clause — that clause is wrong for builds (a tiny PR must still compile):

   ```python
   run_rust = "rust" in changed_groups
   run_zig  = "language" in changed_groups and any(f.startswith("daemons/") for f in files)
   # (or, if a dedicated "zig" group was added in step 1:  run_zig = "zig" in changed_groups)
   ```

   Add to the `lines` list written to `GITHUB_OUTPUT` (`ci_classify.py:139-145`) and to the stdout summary (lines 151-158):

   ```python
       f"run_rust={'true' if run_rust else 'false'}",
       f"run_zig={'true' if run_zig else 'false'}",
   ```

4. **Inline test vectors** (add to `ci_classify.py` under `if __name__ == "__main__"` guard, or a sibling `tests/` entry — match how the repo currently tests this script; if none exists, a `--selftest` flag run in CI step is acceptable). Minimum assertions:
   - `classify_paths(["protocol/hcp/hcpbin/src/lib.rs"]) == {"rust"}`
   - `is_non_src("protocol/hcp/hcpbin/src/lib.rs") is False`
   - `auto_tier(10, ["protocol/hcp/hcpbin/src/lib.rs"]) != "smoke"`
   - `classify_paths(["daemons/sandboxd/src/main.zig"]) == {"language"}` (or `{"zig"}`)
   - `classify_paths(["protocol/rfcs/0002-hcplang.md"]) == {"docs"}` (regression: RFCs still docs)

### 3.2 Part B — new `classify` job outputs

Add to the `classify` job's `outputs:` block (`ci-gate.yml:47-52`):

```yaml
      run_rust:        ${{ steps.run.outputs.run_rust }}
      run_zig:         ${{ steps.run.outputs.run_zig }}
```

### 3.3 Part C — new `rust-build` job

```yaml
  # ─── Rust build+test (protocol/hcp/**) ───────────────────────────────────
  rust-build:
    name: rust-build
    needs: classify
    if: |
      needs.classify.outputs.ping_owner != 'true' &&
      needs.classify.outputs.run_rust == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v6

      - name: Install Rust toolchain
        run: rustup show active-toolchain || rustup toolchain install stable --profile minimal
        # ubuntu-latest ships rustup; hcpbin pins edition 2021. litany (WP3-S2) is
        # edition 2024 / rust-version 1.94 (cf. vaked-agents/ci/provost/Cargo.toml) —
        # if a discovered crate sets a higher rust-version, install that channel.

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: protocol/hcp/hcpbin   # extend per discovered crate (§4.4)

      - name: cargo test each protocol/hcp crate
        run: |
          set -euo pipefail
          shopt -s globstar nullglob
          found=0
          for manifest in protocol/hcp/**/Cargo.toml; do
            # skip target/ vendored manifests
            case "$manifest" in */target/*) continue;; esac
            found=1
            echo "::group::cargo test $manifest"
            # hcpbin is zero-dependency with a committed Cargo.lock → --locked --offline.
            # Future crates (litany) may need crates.io: detect deps and drop --offline.
            if grep -qE '^\s*[A-Za-z0-9_-]+\s*=' "$(dirname "$manifest")/Cargo.toml" \
               && grep -q '\[dependencies\]' "$manifest" \
               && ! grep -A2 '\[dependencies\]' "$manifest" | grep -qE '^\s*$'; then
              cargo test --manifest-path "$manifest" --locked
            else
              cargo test --manifest-path "$manifest" --locked --offline
            fi
            echo "::endgroup::"
          done
          [ "$found" = 1 ] || { echo "::error::run_rust=true but no Cargo.toml found under protocol/hcp/"; exit 1; }
```

> The dependency-detection heuristic is intentionally conservative. **Simpler acceptable alternative:** always run `cargo test --manifest-path "$manifest" --locked` (no `--offline`). `--offline` is a hardening optimization for the current zero-dep `hcpbin`; if it complicates the script, drop it and rely on `--locked` + `rust-cache`. The non-negotiable parts are: (a) one `cargo test` per discovered manifest, (b) `--locked` so a stale `Cargo.lock` fails the gate, (c) the `found==0 → exit 1` guard so "trigger fired but nothing built" is a failure, not a silent pass.

### 3.4 Part D — new `zig-build` job

```yaml
  # ─── Zig build (daemons/**) ──────────────────────────────────────────────
  zig-build:
    name: zig-build
    needs: classify
    if: |
      needs.classify.outputs.ping_owner != 'true' &&
      needs.classify.outputs.run_zig == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6

      - uses: mlugg/setup-zig@v2
        with:
          version: 0.16.0   # matches build.zig.zon minimum_zig_version (sandboxd, vakedz)

      - name: zig build each daemon
        run: |
          set -euo pipefail
          shopt -s globstar nullglob
          found=0
          for bz in daemons/**/build.zig; do
            case "$bz" in */.zig-cache/*|*/zig-cache/*) continue;; esac
            dir="$(dirname "$bz")"
            found=1
            echo "::group::zig build $dir"
            ( cd "$dir" && zig build )                 # compile gate
            if grep -q 'b.step("test"' build.zig; then # run unit tests when defined
              ( cd "$dir" && zig build test )
            fi
            echo "::endgroup::"
          done
          [ "$found" = 1 ] || { echo "::error::run_zig=true but no build.zig found under daemons/"; exit 1; }
```

> On `ubuntu-latest` (x86_64) `zig build` builds natively; no `-Dtarget` needed in CI. sandboxd's syscall code (`unshare(CLONE_NEW*)`, `execvpe`) compiles on Linux. The **runtime** namespace tests need privileged Linux → §7. sandboxd's manifest currently **fails to parse** (see §6) — that is the first thing this job will (correctly) catch.

### 3.5 Part E — wire BOTH jobs into the aggregator (the meta-trap — do not skip)

The `ci-gate` aggregator only gates jobs that appear in **all three** of: its `needs:` list, its `env:` block, and the `FAIL` loop (`ci-gate.yml:261, 268-275, 292`). A job that runs but is omitted from these is *informational* — green-when-failing, i.e. the exact bug we are killing. All three edits are mandatory:

1. `needs:` (line 261):
   ```yaml
   needs: [classify, smoke, standard, full, nix-parse, nix-check, agent-guard, rust-build, zig-build]
   ```
2. `env:` (after line 275):
   ```yaml
          RUST_BUILD:   ${{ needs.rust-build.result }}
          ZIG_BUILD:    ${{ needs.zig-build.result }}
   ```
3. `FAIL` loop (line 292):
   ```bash
          for job_result in "$SMOKE" "$STANDARD" "$FULL" "$NIX_PARSE" "$NIX_CHECK" "$AGENT_GUARD" "$RUST_BUILD" "$ZIG_BUILD"; do
   ```
4. Step-summary table (after line 312) — add `rust-build` and `zig-build` rows (cosmetic but expected by the existing pattern).

`result == 'skipped'` is neutral (the loop only fails on `"failure"`), so PRs that don't touch Rust/Zig stay green — same semantics as `nix-check`.

---

## 4. File layout (paths to create / modify)

| Path | Action | What |
|---|---|---|
| `.github/scripts/ci_classify.py` | **modify** | `PATH_GROUPS` (+`rust`, `daemons`→language), narrow `NON_SRC_PREFIXES`, emit `run_rust`/`run_zig`, inline self-test vectors (§3.1) |
| `.github/workflows/ci-gate.yml` | **modify** | `classify.outputs` (+2), new `rust-build` + `zig-build` jobs, aggregator `needs`/`env`/`FAIL`/summary (§3.2-3.5) |
| `docs/superpowers/specs/2026-06-14-ci-gate-build-extension.md` | **create** | this spec |

No new source dirs. No changes to `protocol/hcp/**` or `daemons/**` source (the sandboxd manifest fix is a separate blocker — §6).

### 4.4 Discovery, not hardcoding
The build steps glob `protocol/hcp/**/Cargo.toml` and `daemons/**/build.zig` so the gate auto-covers `protocol/hcp/litany/` (WP3-S2) and `daemons/agent-supervisord/`, `daemons/eventd/` (WP4) the day they land — preventing a re-vacuous-green. The only per-crate maintenance is the optional `rust-cache` `workspaces:` list (§3.3); a missed entry degrades cache hit-rate, not correctness.

---

## 5. Algorithm / control flow

```
pull_request → classify (ubuntu-latest, py3.12)
  ci_classify.py:
    files          = git diff --name-only base head
    changed_groups = classify_paths(files)         # rust / language(daemons) / docs / …
    run_rust       = "rust" in changed_groups                       # tier-independent
    run_zig        = daemons/ touched                               # tier-independent
    run_nix_parse  = (unchanged)
  → outputs: tier, changed_groups, ping_owner, run_nix_parse, run_nix_check, run_rust, run_zig

fan-out (all need classify, all skip when ping_owner):
  smoke / standard / full / nix-parse / nix-check        (unchanged)
  rust-build   if run_rust=='true'  → for each protocol/hcp/**/Cargo.toml: cargo test --locked
  zig-build    if run_zig =='true'  → for each daemons/**/build.zig:       zig build [+ test]
  agent-guard                                              (unchanged)

ci-gate (needs ALL above, if: always()):
  FAIL = any(result == "failure" for job in
             {smoke,standard,full,nix-parse,nix-check,agent-guard,rust-build,zig-build})
  exit 1 if FAIL          # ← rust-build / zig-build now genuinely gate
```

---

## 6. Dependencies on other sprints / blockers

1. **`daemons/sandboxd/build.zig.zon` is broken (blocker for `zig-build` going green).** It uses `.name = "sandboxd"` (a string), which **Zig 0.16 rejects** at manifest parse:
   ```
   build.zig.zon:2:13: error: expected enum literal
       .name = "sandboxd",
   ```
   The correct form is an enum literal, as `vakedz/build.zig.zon` uses (`.name = .vakedz`). **Verified locally** (`zig version` 0.16.0; `zig build` in `daemons/sandboxd/` fails on this line, while `vakedz` builds clean). This is *evidence the gate has value* — it catches a live error today. **Do not fix it in this sprint** (out of scope per surgical-changes rule); file/track it as a precondition. Until fixed, `zig-build` will (correctly) red any PR touching `daemons/sandboxd/**`.
2. **WP3-S2 litany crate** (`protocol/hcp/litany/`, Jul 9–23): when it lands, the `protocol/hcp/**` glob auto-covers it. If litany pulls crates.io deps, the `--offline` heuristic must yield to a networked `cargo test` (§3.3) and `rust-cache` `workspaces:` should add `protocol/hcp/litany`.
3. **WP4 daemons** (`agent-supervisord`, `eventd`, Aug+): auto-covered by the `daemons/**` glob; each must ship a parseable `build.zig.zon` (cf. blocker 1).
4. **RFC 0002 freeze** (WP3 pre-start gate, by Jun 21): the hcpbin golden vectors in `golden.rs` assume a frozen §6 byte format. Not a blocker for the *gate* (the gate runs whatever tests exist), but a churning RFC means churning red — informational.
5. **No root Cargo workspace exists.** This spec relies on per-manifest `cargo test`; if a future sprint introduces a root workspace, collapse the loop into a single `cargo test --workspace` (simpler) — revisit then.

---

## 7. Test plan — what is verifiable on M1 now vs. what needs Linux/dev-cx53

**Clarification:** "dev-cx53 is the build target" in the kickoff docs refers to the *engineering devshell* (`nix develop`), not the CI runner. `ci-gate` runs on **`ubuntu-latest`** hosted runners. dev-cx53 being off-limits to the author does **not** affect this gate. Three tiers:

### 7.1 Verified locally on this M1 now (author evidence)
- `cd protocol/hcp/hcpbin && cargo test --offline` → **50 passed (3 suites)**, exit 0 (cargo 1.95.0). Proves the Rust oracle is real and the crate is offline/`--locked`-buildable.
- `cd vakedz && zig build` and `zig build -Dtarget=x86_64-linux` → both exit 0 (zig 0.16.0). Proves the Zig toolchain + cross-compile gate works on M1.
- `cd daemons/sandboxd && zig build` → **fails** at `build.zig.zon:2` (the §6 blocker). Proves the zig gate catches the live error.
- `python3 .github/scripts/ci_classify.py` helpers against `HEAD` → reproduces the §1 vacuous-green table. After the §3.1 fix, the inline self-test vectors (§3.1 step 4) must pass: run `python3 .github/scripts/ci_classify.py --selftest` (or equivalent) → exit 0.

**M1 acceptance dry-run (no GitHub needed):**
```bash
# Rust side
for m in protocol/hcp/**/Cargo.toml; do [[ "$m" == */target/* ]] && continue; cargo test --manifest-path "$m" --locked; done
# Zig side (compile-only is portable; runtime tests are Linux — see 7.3)
for b in daemons/**/build.zig; do (cd "$(dirname "$b")" && zig build); done
# classify self-test
python3 .github/scripts/ci_classify.py --selftest
```

### 7.2 Verified on ubuntu-latest in CI (the gate itself)
- `rust-build`: `cargo test --manifest-path … --locked` per discovered crate. Native x86_64 build; identical to the M1 run modulo arch.
- `zig-build`: `zig build` (compile) + `zig build test` (when a `test` step exists) per discovered daemon. Native x86_64 Linux — sandboxd's `unshare`/`execvpe` syscall code **compiles** here (it doesn't on macOS for the namespace path, hence CI is the compile oracle for Linux-only syscalls).
- Aggregator wiring: open a throwaway PR touching `protocol/hcp/hcpbin/src/lib.rs` with a deliberately broken test → confirm `ci-gate` goes **red** (proves §3.5 wiring). Then a green change → `ci-gate` green. Same for a `daemons/**` change.

### 7.3 Needs privileged Linux (NOT M1, NOT plain ubuntu-latest container) — out of scope for this gate
- sandboxd **runtime** namespace tests: actually calling `unshare(CLONE_NEWUSER|CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWNET)` + `execvpe` and asserting isolation (WP4-S1/S2, `docs/superpowers/plans/2026-06-14-wp4-kickoff.md:54-61`). These *compile* portably (covered by `zig build`) but their execution needs unprivileged-userns or a privileged runner. The `zig-build` gate covers **compile + any pure-logic `zig build test`**; full syscall-runtime tests are a later, separate CI lane (self-hosted/privileged or `dev-cx53`), explicitly **not** part of this required gate.

---

## 8. Acceptance criteria

1. **Classifier root-cause fixed (verified by self-test):**
   - `classify_paths(["protocol/hcp/hcpbin/src/lib.rs"])` returns `{"rust"}` (not `{"docs"}`).
   - `is_non_src("protocol/hcp/hcpbin/src/lib.rs")` is `False`.
   - `auto_tier(10, ["protocol/hcp/hcpbin/src/lib.rs"])` is **not** `smoke`.
   - `classify_paths(["daemons/sandboxd/src/main.zig"])` returns the code group (`language` or `zig`), not `other`.
   - Regression: `classify_paths(["protocol/rfcs/0002-hcplang.md"])` still `{"docs"}`; `is_non_src` still `True`.
   - `run_rust`/`run_zig` emitted to `GITHUB_OUTPUT`, tier-independent.
2. **Jobs exist and trigger correctly:** `rust-build` runs iff `run_rust=='true'`; `zig-build` runs iff `run_zig=='true'`; both skip on `ping-owner`; both skip (neutral) on unrelated PRs.
3. **Builds invoke the real oracles:** `rust-build` runs `cargo test --locked` for **every** non-`target/` `Cargo.toml` under `protocol/hcp/` (and errors if the trigger fired but none found); `zig-build` runs `zig build` (+ `zig build test` when present) for every `build.zig` under `daemons/` (same empty-set guard).
4. **Aggregator gates them (meta-trap closed):** `rust-build` and `zig-build` appear in `ci-gate`'s `needs:`, `env:`, AND the `FAIL` loop. A PR with a failing hcpbin test makes the **required** `ci-gate` check go **red** (demonstrated on a throwaway PR); a failing/parse-erroring daemon build does the same.
5. **No regression for non-code PRs:** a docs-only / RFC-only PR still classifies as `smoke`/`standard` and `ci-gate` stays green with `rust-build`/`zig-build` skipped.
6. **Discovery, not hardcoding:** adding a new crate under `protocol/hcp/` or daemon under `daemons/` is covered with no `ci-gate.yml` edit (other than optional `rust-cache` `workspaces:`).
7. **Scope discipline:** the only files changed are `.github/scripts/ci_classify.py`, `.github/workflows/ci-gate.yml`, and this spec. The `daemons/sandboxd/build.zig.zon` parse bug is documented as a blocker (§6), **not** fixed here.
