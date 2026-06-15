# vaked-oracle slice 4b · thread 1 — team-in-vaked (design)

**Date:** 2026-06-15
**Status:** approved (brainstorm) — ready for plan
**Branch / worktree:** `feat/oracle-team-in-vaked` / `.worktrees/oracle-4b-team-vaked` (off `origin/main` @ `3288f04`, slice-4a merged)

## One-liner

The slice-4a reverser team becomes a **Vaked declaration**. Its roster (panelists +
judge), budget, and OpenRouter **egress membrane** are *lowered from the graph* — so
declaration and enforcement cannot drift. Full dogfood symmetry with the aegis kernel
(`dogfood-kernel.vaked` → `scope_from_vaked.py`) and the slice-1 loop
(`oracle-re-loop.vaked`), now extended to an agent that **leaves the box**.

## Why (context)

- Slice 4a shipped the team (`tools/oracle/{panel,team,memory}.py`, PR #277, `3288f04`):
  a multi-model debate panel + a deterministic coordinator (brett-shaw) + the-dossier.
  Roster lives in **hand-written** `panel.example.json`; budget is a CLI flag; the
  OpenRouter reach is implicit. Three things that can drift from any declaration.
- `oracle-re-loop.vaked` already declares the *slice-1 single loop* and is lowered to a
  write-scope via `tools/dogfood/scope_from_vaked.py` — but it predates the team and
  explicitly forbids egress ("cannot egress"). The team **does** egress (OpenRouter).
- `networkMembrane` is a **real schema** (`vaked/schema/parallel-types.md` §563): a
  deny-by-default egress membrane over the lattice `none < loopback < lan < egress`,
  with `allow = [egress(host, port)]` rules. `agent_guardd` already lowers exactly this
  shape (`gen/ebpf.policy.json`) to a real cgroup/connect BPF program + `decide()`.

So the team's egress models **principally** (real membrane), not via a `writeScope`-style
open-field stopgap. This thread closes the roster/budget/egress drift and exercises the
genuinely new problem: *declaring controlled egress for an agent that leaves the box.*

## Decisions (locked in brainstorm)

1. **Egress modelled via `networkMembrane`** (real schema), not an open field. Local
   panelists keep `network.loopback`; cordon nodes get `network.egress` + a membrane.
2. **Checked POLA + agent_guardd manifest emission.** (a) graph → team config replaces
   hand-written `panel.example.json`; (b) a static check rejects a roster whose endpoint
   reaches a host outside its declared membrane allow-set; (c) the graph also lowers
   (existing vakedc 0012) to `gen/ebpf.policy.json` — the manifest agent_guardd consumes.
   **Live eBPF enforcement stays deferred** (revdev is unprivileged; root-watcher only).
3. **The check is oracle-tool-local** (symmetric with `scope_from_vaked.py`). Promoting it
   to a reusable `vakedc` `E-EGRESS-USE` checker pass (mirroring `E-CAP-USE` / RFC 0027)
   is a **follow-up**, not this thread.
4. **DNS-vs-IP gap → tool-check + flag.** `agent_guardd.decide()` attests **IP literals
   only** ("a non-IP destination is denied as un-attestable"). OpenRouter is reached by
   hostname (Cloudflare, rotating IPs). So: the tool-local check validates endpoint host ∈
   declared cordon allow-set (works on hostnames, the real drift check); the emitted
   manifest enforces loopback as IP rules and carries `openrouter.ai` **marked
   non-attestable**, with a **local egress proxy** noted as the path to full packet
   attestation (follow-up).

## Architecture

```
oracle-team.vaked ──[vakedc parse]──▶ graph.json (LPG)
        │                                  │  nodes: model, endpoint, keyEnv,
        │                                  │  temperature, reasoningEffort, role,
        │                                  │  budgetCalls + per-node networkMembrane
        └──[vakedc lower 0012]──▶ gen/ebpf.policy.json  ──▶ agent_guardd.policy.load_policy
                                                              decide(): loopback=allow,
                                                              openrouter.ai=deny (DNS gap)

graph.json ──▶ roster_from_vaked.load_roster_from_graph ──▶ (panelists, judge, budget)
           └─▶ roster_from_vaked.check_roster_egress ──▶ [] (clean) | [violations] → REJECT
                                                                │
oracle team --from-vaked graph.json ──▶ (4a) team.run_team ────┘  (graph-derived roster)
```

`roster_from_vaked` is **engine-agnostic**: it reads the lowered `graph.json` artifact, so
it survives the planned vakedc(Python)→vakedz(Zig) cutover (both front-ends emit the LPG).

## Components / files

### `vaked/examples/oracle-team.vaked` (NEW)

The team's capability graph. `runtime "oracle-team"`, `systems = ["aarch64-darwin",
"x86_64-linux"]`. One `mesh oracleTeam`:

- `operator` — control-plane superset: `capabilities = [fs.repo_rw, network.egress, mem.admin]`
- `coordinator` (brett-shaw) — `role = "coordinate"`, `capabilities = [fs.repo_rw,
  network.loopback, mem.admin]`, open field `budgetCalls = 30`
- `infra-light` — `model = "qwen2.5-coder-3b-instruct"`, `capabilities = [network.loopback,
  mem.recall]`, open fields `endpoint = "http://127.0.0.1:8091/v1/chat/completions"`,
  `temperature = 0`
- `static-armor` — `model = "llm4decompile"`, `network.loopback`, `endpoint = ":8090..."`,
  `temperature = 0`
- `feketecs` — `model = "deepseek/deepseek-v4-flash"`, `capabilities = [network.egress,
  mem.recall]`, open fields `endpoint = "https://openrouter.ai/api/v1/chat/completions"`,
  `keyEnv = "OPENROUTER_API_KEY"`, `temperature = 1.0`
- `anstetten` — `role = "judge"`, `model = "deepseek/deepseek-v4-pro"`, `network.egress`,
  `endpoint = openrouter`, `keyEnv = "OPENROUTER_API_KEY"`, `temperature = 1.0`,
  `reasoningEffort = "high"`
- edges `operator -> coordinator`, `coordinator -> {infra-light, static-armor, feketecs,
  anstetten}`

Two per-node egress membranes (top-level `network` blocks inside the runtime, syntax per
`vaked/examples/membrane/agent-egress.vaked`):

```
network feketecsCordon  { principal = "feketecs"  default = "deny" allow = [ egress("openrouter.ai", 443) ] }
network anstettenCordon { principal = "anstetten" default = "deny" allow = [ egress("openrouter.ai", 443) ] }
```

Open fields (`endpoint`, `keyEnv`, `temperature`, `reasoningEffort`, `budgetCalls`) ride the
**open** `meshNode` schema — same documented stopgap as `writeScope` in
`dogfood-kernel.vaked` / `oracle-re-loop.vaked`. A header comment states this + the
follow-up (a roster-field schema, like the filesystem-membrane follow-up).

**Acceptance for this file:** `vakedc parse oracle-team.vaked` (→ graph.json), `vakedc
check` (no escalation), `vakedc lower` (→ graph.json + `gen/ebpf.policy.json`). Exact lower
invocation/output path is an impl detail to confirm (the 0012 emitter set).

### `tools/oracle/roster_from_vaked.py` (NEW · pure stdlib · engine-agnostic)

- `load_graph(path) -> dict` — read the lowered LPG JSON. (Mirror the ~10-line helper from
  `tools/dogfood/scope_from_vaked.py` so oracle stays self-contained — no cross-tool import.)
- `_node_props(graph, name) -> dict` — locate a mesh node, return its `props`.
- `load_roster_from_graph(graph) -> (panelists, judge, budget)`:
  - for each non-operator, non-coordinator node with an `endpoint`: build a
    `panel.OpenAIChatClient(endpoint, model, key, temperature=, reasoning_effort=)` where
    `key = os.environ.get(keyEnv, "")`. Reuse 4a's **keyEnv-absent drop + stderr log**
    (a node whose `keyEnv` is set-but-absent is dropped from the panel).
  - node with `role == "judge"` → the judge client; others → `panel.Panelist`.
  - `budget` = coordinator's `budgetCalls` (default 30 if absent).
  - keyless judge falls back to the first panelist (same as `panel.load_roster`).
- `membrane_allow(graph, principal) -> set[(host, port)]` — the node's `networkMembrane`
  allow rules from the graph (empty set if none → deny-all).
- `check_roster_egress(graph) -> list[dict]` — for every node carrying an `endpoint`,
  parse `host:port`; a node is **clean** iff its host is loopback (`127.0.0.1`/`localhost`)
  OR `(host, port) ∈ membrane_allow(graph, node)`. Return one violation dict per offender
  `{node, host, port, reason}`. **This is the drift-closing POLA check** (the tool-local
  `E-EGRESS-USE` analog). No secrets in violation output.

### `tools/oracle/oracle.py` (MODIFY)

`team` subparser: add `--from-vaked <graph.json>` (mutually exclusive with `--panel`).
When set, `cmd_team`:
1. `graph = roster_from_vaked.load_graph(path)`
2. `violations = check_roster_egress(graph)`; if non-empty → print each + **exit non-zero**
   (reject — declaration/enforcement drift).
3. `panelists, judge, budget = load_roster_from_graph(graph)`; use `budget` as
   `--budget-calls` default (explicit flag still overrides).
4. proceed into the existing `run_team` path unchanged.

### `tools/oracle/Taskfile.yml` (MODIFY)

`team:vaked` task: `vakedc parse + lower vaked/examples/oracle-team.vaked` → `graph.json` +
`gen/ebpf.policy.json` (vakedc is Python stdlib → M3-safe, no compile), then `oracle team
--from-vaked <graph.json>` (auto-sources the OpenRouter key env, like the 4a `team` task).
The heavy team run still lands on dev-cx53.

### `tools/oracle/test_oracle.py` (MODIFY — "slice 4b thread 1" block)

Pure-stdlib unittest, M3-runnable:
- `load_roster_from_graph` extracts the right panelists/judge/budget from a **fixture**
  `graph.json` (inline dict written to a tmp file — no live vakedc dependency in tests).
- keyEnv-absent node is dropped (monkeypatch `os.environ`).
- `check_roster_egress`: a clean graph → `[]`; a graph with a node whose endpoint host ∉
  its membrane allow-set → one violation; loopback endpoint with no membrane → clean.
- **manifest test:** a fixture `ebpf.policy.json` (the shape from `agent_guardd/policy.py`)
  loads via `agent_guardd.policy.load_policy`; `decide()` **allows** `127.0.0.1:8090`,
  **denies** an undeclared `(ip, port)`, **denies** a non-IP host (attesting the documented
  DNS gap). (Imports `agent_guardd` read-only — call-only, per constraints.)
- `oracle.py` `parse_args`: `--from-vaked` parses; `--from-vaked` + `--panel` together →
  argparse error (mutually exclusive).

### Docs

- `docs/oracle/v0.md` — a "team-in-vaked (slice 4b · thread 1)" section: the dogfood
  symmetry, the graph→roster/budget/egress lowering, the DNS/IP attestation gap, and the
  two follow-ups (vakedc `E-EGRESS-USE` pass; local egress proxy).
- `.DEV.TODO` — mark thread 1 active; record the follow-ups.
- Cross-link `oracle-team.vaked` wherever `oracle-re-loop.vaked` is referenced.

## Error handling

- keyEnv set-but-absent → drop that panelist (reuse 4a behaviour); keyless judge falls back.
- egress-check violation → reject the run, non-zero exit, print offending `node/host:port`
  (never the key or any secret).
- an egress node with **no** membrane in the graph → `membrane_allow` empty → deny-all →
  violation if it has a non-loopback endpoint (fails closed).
- `vakedc lower` not emitting `ebpf.policy.json` (pipeline detail) → the manifest test uses
  a **fixture**, so unit tests never depend on a live lower; the Taskfile path surfaces a
  clear error if the artifact is missing.

## Testing

- Unit: the block above, pure stdlib, **M3-runnable (no compile)**. Target: existing 72 +
  the new cases, all green on M3.
- On-box acceptance (dev-cx53, revdev): produce `graph.json` from `oracle-team.vaked`, run
  `oracle team --from-vaked` with the **diverse** panel (OpenRouter key staged) → reproduce
  the 4a judge-adjudication evidence, now with roster/budget/egress **graph-derived**, the
  egress check **green**, and `gen/ebpf.policy.json` loading in `agent_guardd.policy`.

## Out of scope (explicit — own cycles)

- **vakedc `E-EGRESS-USE` checker pass** (promote the tool-local check to a language pass;
  RFC like 0027). Touches shared `vakedc/check.py` — its own design cycle.
- **Local egress proxy** for full packet-attestation of OpenRouter (pinned loopback IP).
- **Live eBPF egress enforcement** on the box (revdev unprivileged).
- **Thread 2 — RE-vakedz** (recursive self-RE of the vakedz Zig ELF) — next, own cycle.
- **Thread 3 — ARP-emission** — deferred (touches another dev's execution-ARP-IR lane).

## Constraints (always)

Never build/compile on the M3 (gate to dev-cx53; 3-gate protocol) · revdev unprivileged
(eBPF only via root watcher socket) · Snyk OFF · reuse `tools/ralph` + `eventd` +
`agent_guardd` **read/call-only** · don't touch the execution ARP IR or L2 eBPF-LSM (other
dev's lanes) · never print/echo the OpenRouter key (or hunt for other secrets) · codenames
ASCII-only.
