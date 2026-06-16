# vakedc E-EGRESS-USE + W-EGRESS-UNREFINED (design)

**Date:** 2026-06-16
**Status:** approved (brainstorm) — ready for plan
**Base:** `origin/main` @ `ec06b3f`

## One-liner

Add a vakedc checker pass that makes network egress POLA-sound at the **language** level: a
`networkMembrane` may not authorize egress beyond its principal's held `network` grant
(**E-EGRESS-USE**, error), and a node holding `network.egress`/`lan` with no refining membrane
is flagged as unbounded (**W-EGRESS-UNREFINED**, advisory). The network-domain dual of
`E-CAP-USE` (error) + `W-POLA-EXCESS` (warning); completes thread-1's tool-local egress check
as a real language pass.

## Why / context

`network` is a builtin capability domain (`none < loopback < lan < egress`) and
`networkMembrane` refines a grant into `allow = [egress(host, port)]` rules. Today (verified):
- a node with bare `network.egress` and no membrane → checks clean (unbounded egress, no flag);
- a node holding only `network.loopback` with a membrane allowing `egress("203.0.113.10",443)`
  → **checks clean** — the membrane authorizes egress the capability graph never granted. Unsound.

`E-CAP-USE` already enforces `used ⊑ granted` for `needs`. This pass extends the same POLA
discipline to the network membrane.

## Blast radius (verified)

9 example files use `network.egress`/`lan` **without** a membrane (`editorial-pipeline`,
`hcp-litany-dev-loop`, `issue-driver-team`, `ralph-dogfood-loop`, `redteam-swarm`,
`session-drive-loop`, `supply-chain-pipeline`, `swe-swarm-100k/1m`). So the **error** is framed
as *membrane-over-reach* (which no corpus example does → zero new errors), NOT *membrane-required*
(which would break all 9). The unrefined-egress smell is the **warning** (advisory; those 9 nodes
get a non-blocking `W-EGRESS-UNREFINED`). `oracle-team.vaked` stays clean (egress grant covers its
cordons). The `cap-use-*` type fixtures hold egress but no membrane → they gain a
`W-EGRESS-UNREFINED` warning; their existing `E-CAP-USE` assertions are unaffected (warnings are a
separate code) — the egress-use test cases must account for the added warning where it co-occurs.

## Rules

### E-EGRESS-USE (error)
For each `network <name>` membrane decl (runtime-level, sibling of the mesh):
1. resolve `principal` → a mesh node; if it names no node in the mesh → error.
2. `held` = the node's strongest `network` grant (`max` under the lattice; `none`/absent if no
   network grant).
3. for each `allow = [egress(host, port)]` rule, classify `host` → required grant via
   `_required_grant` (stdlib `ipaddress`): loopback host/IP (or `"localhost"`) → `loopback`;
   private IP (`is_private`) → `lan`; any other IP or a DNS name → `egress`. `required` = the
   strongest across all rules.
4. if `held` does **not** dominate `required` (`not _leq(cap, required, held)`) → emit
   **E-EGRESS-USE** (error): ``membrane `<name>` allows egress at level `<required>` for principal
   `<node>` which holds `network.<held>` — a membrane cannot authorize egress beyond the
   principal's granted network capability (0026)``.

One error per offending membrane; deterministic (membranes sorted by name).

### W-EGRESS-UNREFINED (warning)
For each mesh node holding `network.egress` or `network.lan` with **no** membrane whose
`principal` == the node name → emit **W-EGRESS-UNREFINED** (warning): ``node `<n>` holds
`network.<g>` but no networkMembrane refines it — egress is unbounded (least-authority advisory;
add a `network` membrane with an `allow` set)``. `loopback`/`none` need no membrane. Non-blocking.

## Components / files

### `vakedc/check.py` (MODIFY)
- `_check_mesh(...)` (~1640) — accept a new `network_decls` arg (dict `{name: Decl}` of sibling
  `kind=="network"` decls); thread it to a new `_check_egress_use(...)` call placed right after
  `_check_capability_reachability` (~1725).
- `_check_decl_tree` (~1654) — build `child_networks = {st.name: st for st in decl.body if
  isinstance(st, P.Decl) and st.kind == "network"}` and pass to `_check_mesh`.
- new `_check_egress_use(mesh_decl, node_decls, node_grants, network_decls, registry, smap, file,
  diags)` — implements both rules; `_required_grant(host)` helper (stdlib `ipaddress`);
  `_membrane_bindings(decl)` reads `principal`/`allow` (reuse the `_node_bindings`/value-prop
  pattern); `_egress_rule(entry)` → `(host, port)` from an `egress(...)` app-call (`ref=="egress"`,
  `args=[str, int]`); skips malformed rules (fail-soft).
- emit via `_emit(..., severity="error"|"warning")`; lattice via `_leq(registry.caps["network"],
  required, held)`.

### Fixtures `vaked/examples/types/` (NEW)
- `egress-use-exceeds.vaked` — node holds `network.loopback`, a membrane allows
  `egress("203.0.113.10",443)` → **E-EGRESS-USE**.
- `egress-use-ok.vaked` — node holds `network.egress`, membrane allows `egress("203.0.113.10",443)`
  → clean (no egress-use error; no unrefined warning since refined).
- `egress-unrefined.vaked` — node holds `network.egress`, no membrane → **W-EGRESS-UNREFINED** only.
- `egress-use-bad-principal.vaked` — membrane principal names a non-node → **E-EGRESS-USE**.
- (loopback membrane on a loopback-grant node → clean; covered by `egress-use-ok` variant or an
  inline case.)

### Tests `tests/spec/test_vakedc_check.py` (MODIFY)
Add a group mirroring the E-CAP-USE block: a `_EGRESS_CASES` list mapping each fixture →
expected codes; assert exact code set, severities (`E-EGRESS-USE`=error, `W-EGRESS-UNREFINED`
=warning), message contains the principal/node name + a `(0026)` ref, and source-mapped span
(`!= (0,0)`). Plus a corpus guard: checking `vaked/examples/oracle-team.vaked` yields **no**
`E-EGRESS-USE` (its cordons match its grants).

### Docs
`docs/language/` — a short note (or extend the POLA/0026/0027 reference) documenting
E-EGRESS-USE + W-EGRESS-UNREFINED as the network-domain dual. `.DEV.TODO` — item done; link to
the thread-1 tool-local `check_roster_egress` it promotes.

## Error handling / determinism
- No clocks/randomness (pure). Sorted iteration (membranes by name, nodes by name).
- Malformed `allow` entries / non-IP non-DNS hosts → `_required_grant` returns `egress`
  (conservative); a totally malformed rule is skipped (the `networkMembrane` schema conformance
  owns type errors).
- A membrane whose principal node exists but holds no `network` grant → `held = none` → any
  non-`none` required → error (membrane refines a grant the node lacks).

## Out of scope (follow-ups)
- Per-rule (vs per-membrane) error granularity.
- An RFC formalizing the network-domain POLA dual (note it; RFC like 0027 for E-CAP-USE).
- Porting the check to `vakedz` (Zig front-end) — separate cycle.

## Constraints
Pure stdlib (incl. `ipaddress`); M3-safe (`vakedc check` is pure Python, no compile); in-lane
(vakedc is ours; E-CAP-USE precedent); must not add ERRORS to the existing example corpus (only
the advisory warning); Snyk OFF.
