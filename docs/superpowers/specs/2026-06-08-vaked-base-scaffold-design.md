# vaked-base scaffold — design record

- **Date:** 2026-06-08
- **Status:** Approved & implemented (initial scaffold)

## Goal

Lay down `vaked-base` as the **foundation monorepo** for the Vaked ecosystem,
wrapping the real "language track v2" content in a monorepo shape with indexed
stubs for the runtime and protocol subsystems. Then `/init`, configure minimal
project skills, and publish a private remote.

## Decisions

| Question | Decision |
|----------|----------|
| Fidelity | Use the **real** `vaked-language-track-v2.zip` contents (user supplied), not a reconstruction. |
| Scope | **Monorepo base**: language (real) + runtime/protocol (stubs) as sibling subtrees. |
| Git/remote | `git init` + local commit, then **private** `peterlodri-sec/vaked-base` via `gh`, pushed. |
| Skills | **Two**: `vaked-language-author`, `hcp-rfc-author`. No subagents (minimal). |
| Snyk | **Off** for this project/session (explicit user override of the global directive). |
| MCP | Project `.mcp.json`: github, context7, repowise, workspace-fs, playwright (+ crabcc, added when its index is built). |

## Layout

- **Real (from zip):** `vaked/` (grammar, schema, examples), `docs/language/` (0001/0003/0008/0009 + README + references), `docs/context/PROJECT_CONTEXT.md`, `prompts/dedicated-language-session.md`.
- **New (authored):** `README.md`, `flake.nix`, `.gitignore`, `.mcp.json`, `CLAUDE.md`, `docs/runtime/README.md`, `docs/protocol/README.md`, `docs/language/0010-mirageos-unikernel-surface.md`, `docs/language/references/session-2026-06-08-sparks.md`, `daemons/README.md`, `protocol/README.md`, `protocol/rfcs/0001-hcp.md`, `.claude/skills/{vaked-language-author,hcp-rfc-author}/SKILL.md`.

## Out of scope (each gets its own spec → plan → implementation)

Implementing any daemon, the HCP wire format, a Vaked parser/evaluator, CrabCC
internals, the MirageOS spike.

## Session setup performed alongside the scaffold

- **MemPalace** Stop/PreCompact hooks rewritten to mine the transcript **async in the background** (non-blocking). Lives in the version-pinned plugin cache — see CLAUDE.md patch-doctor.
- **CrabCC** updated 5.0.0 → **6.2.0** (`cargo install --git crabcc-labs/crabcc --tag v6.2.0 crabcc-cli`).

## Reference sparks folded in

MirageOS (unikernel materialization surface, note 0010), libxev (Zig event loop for the daemons), codedb (Zig code-intel/MCP, CrabCC lineage), oxwm (Zig native surface) — captured in `docs/language/references/session-2026-06-08-sparks.md`.
