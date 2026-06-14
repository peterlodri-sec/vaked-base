# cargo-workspace — Root Cargo workspace + nix devShell wiring

- **Status:** Draft (planning artifact; the consuming work — WP3-S1 — is future/dependency-blocked, see §7)
- **Created:** 2026-06-14
- **Track:** WP3 (HCP wire protocol — `docs/superpowers/plans/2026-06-14-wp3-kickoff.md`)
- **Gate:** WP3 pre-start gate, due **Jun 21 2026** (kickoff plan, "Pre-start gates" section, line 41: `[ ] Cargo.toml workspace wired into dev shell (nix develop)`)
- **Owner:** WP3 engineer (Engineer A, Rust/async networking) or scaffold maintainer
- **Code home:** repo root (`/Cargo.toml`, `/flake.nix`, `/Taskfile.yml`)

## 0. Citation correction (read first)

The WP3 kickoff (`docs/superpowers/plans/2026-06-14-wp3-kickoff.md`, "First task"
section, line ~43) and the issue text say golden vectors come from
"**RFC 0002 §4 / Appendix A**". **That wording is stale and wrong** and is carried
verbatim into several WP3 docs; it does not affect this gate's *deliverable* (a
workspace + dev-shell wiring) but is corrected here so this spec is internally
consistent with the crate it scaffolds:

- The byte encoding lives in **RFC 0002 §6** ("`hcpbin` encoding rules",
  `protocol/rfcs/0002-hcplang.md` line 439), **not §4**.
- The frame header (`kind`/`corr`/`stream`/`seq`/`end`) is declared in **RFC 0002
  §4.2** (line 226) but is **part of the WIRE layer**, with its byte encoding
  normative in **RFC 0003** — RFC 0002 §4.2 and the §6 scope note (line ~446)
  explicitly place it **outside `hcpbin`'s payload scope**.
- There is **no Appendix A** in RFC 0002. The golden vectors are the worked
  examples in RFC 0002 **§6.1.1** (primitives, line 473), **§6.3.1** (default
  omission, line 622), **§6.6.1** (lists/maps, line 825), **§6.7.1** (unions/enums,
  line 774), and **§10** (line 1009).

The crate this gate scaffolds (`protocol/hcp/hcpbin/`) already cites the correct
sections: `src/lib.rs` header reads "canonical binary codec for HCP values
(RFC 0002 §6)", and `tests/golden.rs` derives expectations from §6.1.1 and §6.5.

## 1. Objective

Stand up a **root Cargo workspace** at the repo root and **wire it into the nix
devShell** so that `protocol/hcp/*` crates (today `hcpbin`; tomorrow `litany`)
build and test under `nix develop` on the WP3 build target `dev-cx53`.

Concretely, after this gate closes:

1. A `/Cargo.toml` `[workspace]` exists, with `hcpbin` as a member and a single
   root `Cargo.lock`.
2. The nix devShell (`flake.nix`) provides a Rust toolchain that satisfies the
   **highest** Rust floor of any crate built inside that shell (set by `swe-af`,
   not `hcpbin` — see §4.4), plus `rustfmt` and `clippy`.
3. A `Taskfile.yml` task runs `cargo` against the workspace through
   `nix develop --command`, mirroring the existing `swe-af` precedent.
4. The future `litany` crate (WP3-S2) is auto-absorbed by the workspace glob with
   **no further edit to `/Cargo.toml`**.

This is a **scaffolding** gate. It does **not** implement the codec (WP3-S1) and
its acceptance criterion is **structural resolution**, not test-pass (§8).

### 1.1 What this gate is NOT (scope boundary)

| Out of scope | Owner |
|---|---|
| Implementing `encode`/`decode` per RFC 0002 §6 | WP3-S1 (`protocol/hcp/hcpbin/src/lib.rs`) |
| Creating the `litany` crate | WP3-S2 (`protocol/hcp/litany/`) |
| Pulling `swe-af` into the workspace | never — it is a deliberately standalone crate (§4.4) |
| Adding a `rust-toolchain.toml` / rustup pin | rejected by decision D3 (§4.3) |
| Binary-cache / attic substituter setup | pre-existing infra (Taskfile header, lines 4–8) |

## 2. Inputs / oracles

### 2.1 Inputs (existing repo state, all verified by reading)

| Path | Relevant fact |
|---|---|
| `protocol/hcp/hcpbin/Cargo.toml` | `name = "hcpbin"`, `version = "0.1.0"`, `edition = "2021"`, `[lib] name = "hcpbin"`, **zero dependencies**. The workspace member. |
| `protocol/hcp/hcpbin/Cargo.lock` | Member-local lockfile (single package `hcpbin`). **Must be deleted** — the workspace lockfile lives at root. |
| `protocol/hcp/hcpbin/src/lib.rs` | Compiling stub exposing the full `encode_*`/`decode_*` API surface (verified: `cargo check` clean). |
| `protocol/hcp/hcpbin/tests/golden.rs` | Independent golden + round-trip suite, RFC-derived. Verified: currently **compiles and runs** under the host toolchain. |
| `protocol/hcp/README.md` | Declares the intended layout: `hcpbin/` (RFC 0002, WP3-S1) and `litany/` (frame+routing, WP3-S2+); "Build target: `dev-cx53` via `nix develop`." |
| `vaked-agents/ci/swe-af/Cargo.toml` | Standalone crate: `edition = "2024"`, `rust-version = "1.94"`, **empty `[workspace]` table** + comment "do not join a parent Cargo workspace (there is none at repo root)." Built inside the same nix shell (Taskfile line 143). **Sets the toolchain floor.** |
| `flake.nix` | `devShells.default` provides `rustc` + `cargo` (nixpkgs), no `rustfmt`/`clippy`, no rust-overlay, no toolchain pin. |
| `flake.lock` | `nixpkgs` pinned to rev `9ae611a455b90cf061d8f332b977e387bda8e1ca` (ref `nixos-unstable`, `lastModified 1781074563`). |
| `Taskfile.yml` | All tasks run via `RUN: nix develop {{.DEVSHELL}} --command`. The `swe-af` task (lines 141–144) is the cargo precedent: `cargo test`/`cargo build --release --manifest-path …`, flagged `REMOTE-ONLY`. |
| repo root | **No `/Cargo.toml` exists** (verified: `find . -name Cargo.toml` returns only the two crate manifests). |

### 2.2 Oracles (how correctness is judged)

| Oracle | Command | Expected | Where it runs |
|---|---|---|---|
| O1 Workspace resolves, correct members | `cargo metadata --format-version 1 --no-deps` | packages list contains `hcpbin`, **not** `vaked-swe-af`; `workspace_root` = repo root | M1 (host cargo) + dev-cx53 |
| O2 Workspace compiles | `cargo check --workspace` | exit 0, "Checking hcpbin" | M1 (host) + `nix develop` |
| O3 Single root lockfile | `ls Cargo.lock protocol/hcp/hcpbin/Cargo.lock` | root present; member absent | M1 |
| O4 Glob auto-absorbs `litany` | add stub `protocol/hcp/litany/Cargo.toml`, re-run O1 | members become `[hcpbin, litany]` with **no `/Cargo.toml` edit** | M1 (simulated) |
| O5 **Gate toolchain floor** | `nix develop . --command rustc --version` | `rustc` ≥ **1.94**, supports edition 2024 | `nix develop` (gate-relevant) |
| O6 Lint tools present in shell | `nix develop . --command bash -c 'cargo fmt --version && cargo clippy --version'` | both resolve | `nix develop` |

**Verified during authoring (host toolchain, `/Users/lodripeter/.cargo/bin`):** O1–O4
all pass; `cargo check --manifest-path …/hcpbin/Cargo.toml` is clean;
`cargo test --no-run` builds both the lib and `golden.rs` test executables. Host
`cargo`/`rustc` = **1.95.0**.

**Verified during authoring (nix devShell — gate-relevant):**
`nix develop /tmp/vaked-base --command` resolves `rustc` to
`/nix/store/…-rustc-wrapper-1.95.0/bin/rustc` → **rustc 1.95.0 / cargo 1.95.0**.
So the pinned nixpkgs (`9ae611a4…`) **already satisfies O5** (≥1.94, edition 2024).
The crabcc 6.2.0 banner also confirms the shell is the expected one. This converts
the toolchain-floor claim from assumption to fact. (Note the two toolchains are
distinct: host 1.95.0 was used for structural O1–O4; the nix 1.95.0 is the gate
oracle. They coincide today but the spec keeps them separate so the test plan is
honest about which environment produced which result.)

## 3. File layout (paths to create / modify / delete)

```
/Cargo.toml                              CREATE  — workspace root (§4.1)
/Cargo.lock                              CREATE  — generated by first `cargo` invocation (commit it; bin/lib workspace)
/protocol/hcp/hcpbin/Cargo.lock          DELETE  — member-local lock; superseded by root lock (§4.2)
/protocol/hcp/hcpbin/Cargo.toml          UNCHANGED — member; no edit required (§4.5)
/flake.nix                               EDIT    — add rustfmt + clippy to devShells.default.packages (§4.6)
/Taskfile.yml                            EDIT    — add `hcp` task: cargo against the workspace via {{.RUN}} (§4.7)
/.gitignore                              VERIFY  — ensure `target/` is ignored (it is repo-wide; confirm, do not duplicate)
```

No new directories. `litany/` is created later by WP3-S2, not by this gate.

## 4. Design

### 4.1 Root `/Cargo.toml`

```toml
# Root Cargo workspace for vaked-base.
# Members: the protocol/hcp/* Rust crates (RFC 0002+ wire stack).
# Built inside `nix develop` on dev-cx53 (protocol/hcp/README.md).
[workspace]
resolver = "2"
members  = ["protocol/hcp/*"]
exclude  = ["vaked-agents/ci/swe-af"]
```

Design points, each with rationale:

- **`resolver = "2"` is stated explicitly.** A freshly created workspace defaults
  to resolver **1** even when its members declare `edition = "2021"` (the
  edition→resolver inference applies only to a *package* manifest's own edition,
  not to a virtual workspace root). Resolver 2 is what every member's own
  edition-2021/2024 expectations assume, so we pin it rather than inherit a
  surprising default.
- **`members = ["protocol/hcp/*"]` (glob).** Includes `hcpbin` today and
  **auto-absorbs `litany`** the moment WP3-S2 adds `protocol/hcp/litany/Cargo.toml`
  — verified in O4: members went `[hcpbin]` → `[hcpbin, litany]` with no edit to
  this file. This is the explicit hand-off to WP3-S2 (§7).
- **`exclude = ["vaked-agents/ci/swe-af"]` (defensive).** `swe-af` already
  self-isolates via its own empty `[workspace]` table, so the glob would not reach
  it regardless (it is not under `protocol/hcp/`). The `exclude` is **belt-and-suspenders
  documentation of intent** and guards against a future member glob being widened.
  Decision D2 (§4.4) records the rationale; either keeping or dropping this line is
  defensible, but it is cheap and self-documenting.
- This is a **virtual manifest** (no `[package]` at root) — the root is not itself a
  crate, only an aggregation point.
- `[workspace.package]` / `[workspace.dependencies]` inheritance is **intentionally
  omitted**. `hcpbin` has zero dependencies and the only other current member-to-be
  (`litany`) will depend on `hcpbin` by path. Adding shared-table inheritance now is
  speculative (CLAUDE.md §2 "Simplicity First"); it can be introduced when ≥2 members
  share a real dependency.

### 4.2 Lockfile relocation

A Cargo workspace has exactly **one** `Cargo.lock`, at the workspace root. The
existing `protocol/hcp/hcpbin/Cargo.lock` becomes dead once the root exists and
**must be deleted** (O3). The root `Cargo.lock` is produced by the first `cargo`
invocation after `/Cargo.toml` is created and **must be committed** (the workspace
contains buildable lib/bin crates; per Cargo convention applications/workspaces
commit their lockfile — and `eventd`'s hash-chain reproducibility story, RFC 0002
§6 scope note, benefits from a pinned dependency graph).

### 4.3 Decision D3 — no `rust-toolchain.toml`

We deliberately **do not** add a `rust-toolchain.toml`. The devShell provides
`rustc`/`cargo` from the pinned nixpkgs; there is **no rustup** in the shell, so a
`rust-toolchain.toml` would either be ignored or fight the nix-provided toolchain.
**Reproducibility comes from the `flake.lock` nixpkgs pin** (rev `9ae611a4…`), which
is the single source of truth for the toolchain version (O5). This keeps one pinning
mechanism, not two.

### 4.4 Decision D2 — `swe-af` stays out; the toolchain floor is `swe-af`'s

Two related facts:

1. **`swe-af` is NOT a workspace member.** Its `Cargo.toml` declares an empty
   `[workspace]` table (making it its own workspace root) and comments that there is
   no parent workspace. We honour that: the root glob does not reach it, and
   `exclude` reinforces it (§4.1). Verified in O1 (`vaked-swe-af` absent from
   `cargo metadata`).
2. **But `swe-af` still sets the devShell's Rust floor.** Taskfile line 143 builds
   `swe-af` *inside the same `nix develop` shell* (`cargo … --manifest-path
   vaked-agents/ci/swe-af/Cargo.toml`). `swe-af` is `edition = "2024"`,
   `rust-version = "1.94"`. `hcpbin` is only edition 2021. **Therefore the devShell
   rustc must satisfy 1.94 / edition 2024**, even though our workspace member needs
   less. The gate must **not** spec a lower floor. O5 confirms the pinned nixpkgs
   already delivers rustc 1.95.0 → floor satisfied.

### 4.5 `hcpbin/Cargo.toml` — unchanged (surgical)

No edit. It is already a valid member (`[package]` + `[lib]`, no conflicting
`[workspace]` table). Per CLAUDE.md §3 "Surgical Changes", we do not retrofit
`edition.workspace = true` or other inheritance.

### 4.6 `flake.nix` devShell edit

Add `rustfmt` and `clippy` to `devShells.default.packages` (they are not present
today; O6 would fail without them). Surgical addition next to the existing `rustc`
/ `cargo` lines:

```nix
            rustc                 # CrabCC indexes — toolchain to build crabcc-labs/crabcc
            cargo
            rustfmt               # workspace fmt — protocol/hcp/* (WP3 cargo-workspace gate)
            clippy                # workspace lint — protocol/hcp/* (WP3 cargo-workspace gate)
```

No change to `inputs`, `systems`, `shellHook`, packages, or the NixOS bits.
nixpkgs ships `rustfmt`/`clippy` as separate top-level attrs matching the pinned
`rustc`, so no rust-overlay is needed (consistent with D3). The `nix develop`
build for the pinned shell was exercised during authoring (O5/O6 environment).

### 4.7 `Taskfile.yml` task

Add a workspace-aware task mirroring the `swe-af` precedent, **REMOTE-ONLY** for
the heavy `build --release` per the NEVER-BUILD-ON-DEV-MACHINE rule (CLAUDE.md,
Taskfile comment lines 138–140), while exposing cheap structural/check targets
that are M1-safe:

```yaml
  # --- HCP wire stack: the protocol/hcp/* cargo workspace -----------------------
  hcp:
    desc: 'Check + test the protocol/hcp/* cargo workspace (hcpbin; litany once WP3-S2 lands).'
    cmds:
      - '{{.RUN}} cargo metadata --format-version 1 --no-deps'   # O1: structure resolves (M1-safe)
      - '{{.RUN}} cargo check --workspace'                       # O2: compiles
      - '{{.RUN}} cargo test  --workspace'                       # WP3-S1+: golden vectors (test-pass is later work)
```

Notes:
- Once the root workspace exists, cargo commands use `--workspace`, **not**
  `--manifest-path` (the `--manifest-path` form in the `swe-af` task is required
  only because `swe-af` is a separate root).
- `cargo metadata` and `cargo check` are seconds-long and **M1-safe** (verified);
  `cargo test --workspace` is included for WP3-S1+ but is *not* this gate's
  acceptance criterion (§8).

## 5. Algorithm / step sequence (implementation order)

```
1. Create /Cargo.toml (§4.1)                    -> verify: O1 lists hcpbin, excludes swe-af
2. Delete protocol/hcp/hcpbin/Cargo.lock        -> verify: O3 (member lock gone)
3. Run `cargo metadata` / `cargo check`         -> verify: O2 green; root Cargo.lock generated
4. Commit root Cargo.lock                        -> verify: git status shows /Cargo.lock tracked
5. Edit flake.nix: add rustfmt + clippy (§4.6)  -> verify: O6 under `nix develop`
6. Edit Taskfile.yml: add `hcp` task (§4.7)     -> verify: `task hcp` runs O1+O2 green
7. Confirm gate toolchain (§4.4)                 -> verify: O5 (`nix develop -c rustc --version` >= 1.94)
8. Simulate litany member, re-run O1, revert    -> verify: O4 (glob auto-absorb)
```

Each step's verify is independently runnable; steps 1–4 and 8 are M1-local.

## 6. Test plan — local (M1) vs dev-cx53/Linux

**Build-policy note:** dev-cx53 is OFF-LIMITS for 6h during authoring (autoresearcher).
This gate's local checks are deliberately structural and cheap so the gate can be
*authored and self-verified entirely on M1*; only the full release build and the
canonical "gate green in CI" run belong on dev-cx53.

| Check | Command | M1 (local) | dev-cx53 / `nix develop` | Notes |
|---|---|---|---|---|
| O1 members/exclude | `cargo metadata --format-version 1 --no-deps` | YES (verified) | YES | host cargo 1.95.0 used locally; resolution is toolchain-agnostic |
| O2 workspace compiles | `cargo check --workspace` | YES (verified) | YES | seconds; M1-safe |
| O3 single root lock | `ls Cargo.lock protocol/hcp/hcpbin/Cargo.lock` | YES (verified) | n/a | pure FS check |
| O4 litany auto-absorb | add stub manifest, re-run O1, revert | YES (verified, simulated) | YES | proves WP3-S2 hand-off |
| hcpbin tests compile+run | `cargo test --workspace` | YES (compiles+runs today; verified `--no-run`) | YES | **bonus signal, not gate** (§8) |
| O5 gate toolchain floor | `nix develop . --command rustc --version` | YES (verified: rustc 1.95.0 ≥ 1.94) | YES (same flake; authoritative there) | the gate-relevant toolchain |
| O6 fmt/clippy in shell | `nix develop . -c 'cargo fmt --version && cargo clippy --version'` | YES (after §4.6 edit; nix available on M1) | YES | requires the flake edit |
| `swe-af` still builds in shell | `cargo build --manifest-path vaked-agents/ci/swe-af/Cargo.toml` | NO — REMOTE-ONLY (heavy, network deps) | **dev-cx53 only** | confirms the floor decision didn't break the other in-shell crate |

**Local vs remote split, summarized:**
- **Local on M1 (now):** the entire structural acceptance set (O1–O4, O6) plus the
  gate toolchain oracle O5 — all verified during authoring. `nix` is present on M1,
  so even the dev-shell oracles run locally.
- **dev-cx53 / Linux only:** the heavy `swe-af` release build (REMOTE-ONLY policy),
  and the canonical CI run that records the gate as closed. Nothing in this gate
  *requires* Linux syscalls (unlike the Zig daemons), so dev-cx53 is needed for
  policy/heaviness reasons, not capability.

## 7. Dependencies on other sprints

| Direction | Sprint / component | Relationship |
|---|---|---|
| **This gate blocks** | **WP3-S1** (Jun 24, `hcpbin` codec) | WP3-S1's "First task" is to fill in `protocol/hcp/hcpbin/src/lib.rs` and have golden tests pass *on dev-cx53 via `nix develop`*. That requires a workspace wired into the shell — this gate. Listed as a pre-start gate due **Jun 21**, 3 days before WP3-S1 starts. |
| **This gate enables (no later edit)** | **WP3-S2** (Jul 9, `litany` crate) | When WP3-S2 creates `protocol/hcp/litany/Cargo.toml`, the `protocol/hcp/*` glob absorbs it automatically (O4). WP3-S2 must **not** add a `[workspace]` table to `litany` (that would self-isolate it, like `swe-af`). |
| **Sibling pre-start gates** (kickoff) | RFC 0002 format freeze (Jun 21); WP3 engineer nominated | Independent of this gate; all three must close before Jun 24. RFC 0002 freeze is a *content* precondition for WP3-S1, not for this structural gate. |
| **Unaffected** | `vaked-agents/ci/swe-af` | Stays a standalone crate (D2). This gate must not regress its in-shell build (test row 8). |
| **Downstream consumers** | `eventd` (WP3-S5), daemon fleet | Consume the eventual `litany` crate; no dependency on the workspace scaffolding itself. |

## 8. Acceptance criteria

The gate is **structural**: it closes when the workspace *resolves and compiles*
in the dev shell — **not** when `hcpbin`'s codec tests pass. Test-pass is WP3-S1's
deliverable; importing it into a pre-start gate would couple a Jun-21 gate to
Jun-24+ work.

**MUST (gate-closing):**

1. `/Cargo.toml` exists; `cargo metadata --format-version 1 --no-deps` lists
   `hcpbin` as a member and does **not** list `vaked-swe-af` (O1).
2. `nix develop . --command cargo check --workspace` exits 0 (O2 under the gate
   toolchain).
3. Exactly one `Cargo.lock`, at the repo root; `protocol/hcp/hcpbin/Cargo.lock`
   removed; root lock committed (O3).
4. `nix develop . --command rustc --version` reports ≥ **1.94** with edition-2024
   support (O5) — satisfies the `swe-af` floor (D2).
5. `nix develop . -c 'cargo fmt --version && cargo clippy --version'` both resolve
   (O6) — devShell carries the lint toolchain.
6. `task hcp` (Taskfile) runs steps O1+O2 green.
7. Adding a stub `protocol/hcp/litany/Cargo.toml` makes it a member with **no edit**
   to `/Cargo.toml` (O4) — WP3-S2 hand-off proven.
8. `swe-af` still builds inside the shell on dev-cx53 (no regression from the
   floor/exclude decisions) — test plan row 8, run on dev-cx53.

**SHOULD (bonus signal, explicitly NOT gate-closing):**

- `nix develop . --command cargo test --workspace` compiles and runs the `hcpbin`
  lib + `golden.rs` executables. As of authoring these **already compile and run**
  on the host toolchain; whether every golden vector *passes* is WP3-S1's
  responsibility, so a red `cargo test` does **not** fail this gate.

**MUST NOT:**

- Add a `rust-toolchain.toml` (D3).
- Add `swe-af` to the workspace (D2).
- Edit `hcpbin/Cargo.toml` (surgical; §4.5).
- Make `cargo test --workspace` green a gate criterion (§8 rationale).
