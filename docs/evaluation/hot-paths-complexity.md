# Vaked — core hot-paths: data structures, algorithms & complexity

A reference map of the **performance-sensitive / critical** code paths across the
Vaked subsystems, with the data structure + algorithm/technique each uses and its
**time** and **space** complexity (Big-O; *space* = auxiliary/total memory as a
function of input size).

**Methodology.** Complexities are grounded in the actual loop/recursion structure
of the code (not guessed). Where a path was empirically measured, that measurement
is cited (see `scalability-analysis-v0.1.md`). Source links are repo-relative.

**Provenance caveats.**
- ✅ **trunk** = on `origin/main`.
- 🌿 **branch** = on a feature branch not yet merged (named inline).
- 📄 **SPEC ONLY** = normative RFC prose, no implementation yet.

**Variable legend (per subsystem):** `N` = declarations/graph nodes · `E` = graph
edges · `B` = output bytes · `T` = tokens · `G` = capability grants in a domain ·
`P` = principals · `L` = ledger lines/bytes · `R` = membrane rules.

---

## 1. `vakedc` — Python compiler ✅ trunk (`vakedc/`)

Pipeline: lex → resolve (`build_graph`) → check → lower. A controlled GHA sweep
(`scalability-analysis-v0.1.md`) measured **parse, check, and lower all O(N)
linear** after the #268 fix (empirical slope ≈ 1.0).

| Path | Source | DS · Technique | Time | Space |
|---|---|---|---|---|
| Lexer scan | `vakedc/lexer.py` | char array · single-pass scan + bounded lookahead | O(N), N = src bytes | O(T) |
| Parser | `vakedc/parser.py` | recursive descent + soft-keyword lookahead | O(N) | O(AST) + O(depth) stack |
| resolve / `build_graph` | `vakedc/resolve.py:78` | dict-keyed lexical scopes + deferred-ref worklist | O(N) (dict ops O(1)) | O(N) nodes+edges |
| `_resolve_ref` | `vakedc/resolve.py:224` | scope dict chain | O(1) per ref (depth-bounded) | O(1) |
| `_transitive_closure` (capability `≤`) | `vakedc/check.py:323` | reachability DFS + antisymmetry over **grants** | O(G²+E·G), G small per domain | O(G²) closure |
| POLA use-check (`E-CAP-USE`) | `vakedc/check.py:1757` | per-principal grant↦need dominance via precomputed `_leq` | ~O(P·g·n) — worst-case quadratic in decl size (not hit by flat archs) | O(P) |
| `enrich_graph` | `vakedc/lower.py:1571` | `#<chain>`→node **suffix index** (one O(N) pass) | **O(N)** — was O(N²) before #268 | O(N) index |
| `_children_of` | `vakedc/lower.py:206` | `contains` edge scan → adjacency index (PR #269) | O(E)·~6 today → **O(deg)** with #269 | O(E) index (with #269) |
| `lower` (emit) | `vakedc/lower.py:1233` | `_runtime_view`×~6 (`nodes_sorted`) + per-fiber emit + provenance sort | O(N log N) | O(N) |
| canonical-JSON + region hash | `vakedc/lower.py:162` | recursive sorted-key serialize + SHA-256 | O(B) | O(B) |

> 🌿 `lang/execution-semantics` (unmerged) adds `overlay.py`/`schedule.py`: a static
> **wavefront schedule via Kahn topological sort** O(V+E) and a memoized
> critical-path DFS O(V+E).

## 2. `vakedz` — Zig front-end ✅ trunk (`vakedz/`, cache-native port)

| Path | Source | DS · Technique | Time | Space |
|---|---|---|---|---|
| Lexer | `vakedz/lexer.zig:109` | `ArrayList(Token)` · single-pass switch dispatch | O(N) bytes | O(T) |
| Parser edge lookahead | `vakedz/parser.zig:331` | token array · forward scan to `->` | O(N) parse; O(k)/lookahead | O(AST) |
| Graph build (index + build) | `vakedz/graph.zig:65,86` | `StringHashMap` name/kind index | O(D), O(1)/insert | O(D) |
| Ref resolution | `vakedz/graph.zig:234` | 2× HashMap lookup | O(1) expected/ref | O(1) |
| Graph emit | `vakedz/graph.zig:350` | pdqsort nodes+edges + canonical write | O(N log N + E log E + B) | O(N+E) |
| Canonical JSON | `vakedz/json.zig:37,70` | tagged-union recursive descent + in-place key pdqsort | O(B) write; O(T log T) sort | O(1) streamed |
| Span lookup | `vakedz/check.zig:75` | sorted token-starts · **binary search** | O(log T)/lookup | O(1) |
| Transitive closure | `vakedz/check.zig:288` | Floyd-style over grants | O(G²+E·G) | O(G²) |
| ⚠️ Cache lookup | `vakedz/cache.zig:102` | append-only ledger · **linear scan** + JSON parse | O(L) ledger lines | O(K)/entry |
| ⚠️ Cache append | `vakedz/cache.zig:139` | **whole-ledger rewrite** + SHA-256 hash-chain | **O(L)/append** (→ O(L²)/session; capped at 64 MB) | O(L) buffer |

> The two ⚠️ cache paths are the only super-linear spots — same shape as ralph's
> former #58 bug. Bounded by the 64 MB ledger cap, so acceptable today; an index or
> tail-append would make them O(1) if the cache grows.

## 3. `eventd` + `tools/ralph` — event log & autonomous loop ✅ trunk

| Path | Source | DS · Technique | Time | Space |
|---|---|---|---|---|
| `EventLog.append` | `eventd/log.py:205` (Py) | `flock` single-writer · SHA-256 hash-chain · fsync | O(payload) | O(payload) |
| ralph `append_event` | `tools/ralph/ralph.py` | single-writer head cache, primed once | **O(1) amortized** — was O(N²) before #58 | O(1) state |
| `verify_chain` / `longest_valid_prefix` (boot) | `tools/ralph/ralphcore.py:489,504` | linear re-hash + torn-tail recovery | O(N) entries at boot | O(1) |
| `window_log` (flat-cost context) | `tools/ralph/ralphcore.py:365` | regex split · keep-last-K + collapse older | O(N) scan, O(K) out | O(K) — **flat (#57)** |
| `replay_events` (state fold) | `tools/ralph/ralph.py` | single-pass fold | O(N) | O(S) subjects |
| `_next_in_ring` (round-robin) | `tools/ralph/ralphcore.py:181` | list + skip-set · modular step | O(S) | O(1) |

## 4. `agent_guardd` + `protocol` — egress membrane & wire

| Path | Source | DS · Technique | Time | Space |
|---|---|---|---|---|
| eBPF egress verdict ✅ | `agent_guardd/bpf.py:~60` | 2-insn `CGROUP_SKB` · deny-by-default posture | **O(1)/packet** | O(1) |
| `policy.decide` ✅ (userspace ref) | `agent_guardd/policy.py:~90` | rule list · linear scan (no IP trie) | O(R) rules/conn | O(R) |
| `enforce` + `testify` ✅ | `agent_guardd/enforce.py:~30` | connect + hash-chain to eventd | O(R) + connect latency | O(1) |
| Litany varint framing 📄 | `protocol/rfcs/0003-litany-wire.md` §4 | LEB128 + overlong-reject | O(k≤3)/frame | O(1) |
| Flow-control credit 📄 | `protocol/rfcs/0003-litany-wire.md` §8 | per-stream credit map + control-frame bypass | O(1)/frame | O(streams) |
| Frame-header codec 📄 | `protocol/rfcs/0002-hcplang.md` §4 | tagged `hcpbin` fixed header | O(1)/frame | O(1) |
| Schema-digest negotiate 📄 | `protocol/rfcs/0003-litany-wire.md` §5.4 | set intersection at handshake | O(d₁·d₂), d ≤ ~10 | O(d₁+d₂) |

## 5. `tools/optitron` (Go) + `tools/dogfood` kernel (Python)

🌿 dogfood kernel lives on `feat/local-dogfood-kernel` (pushed, unmerged).

| Path | Source | DS · Technique | Time | Space |
|---|---|---|---|---|
| `Ledger.Append` | `tools/optitron/internal/ledger/ledger.go:162` (Go) | `sync.Mutex` single-writer · SHA-256 chain · fsync | O(1) under lock | O(N) in-mem |
| `VerifyChain` (boot) | `tools/optitron/internal/ledger/ledger.go:64` | linear re-hash from genesis | O(N·payload) | O(1) |
| Deterministic gate | `tools/optitron/internal/gate/gate.go:24` | map-set source-dedup · regex bench · fail-closed | O(text)+O(sources) | O(sources) |
| Git change-detect | `tools/dogfood/kernel.py:63` | `git status --porcelain` ×2 + dict-diff (leans on git mtime/index) | **O(tracked·stat + changed·bytes)** — was O(repo²) full-hash | O(tracked) |
| `tree_snapshot`/`tree_hash` | `tools/dogfood/transition.py:62` | per-file SHA + sorted-canonical hash | O(scope·bytes + scope log scope) | O(scope) |
| Capability gate (POLA) | `tools/dogfood/capability.py:23` | segment-aware prefix match · all-or-nothing | O(paths·scope) | O(violations) |
| `scope_from_vaked` | `tools/dogfood/scope_from_vaked.py:43` | LPG `graph.json` traversal | O(nodes·caps) (graph small) | O(caps) |
| LD_PRELOAD fold | `tools/dogfood/observe_preload.py:26` (C+Py) | set-dedup of W/D log lines | O(syscalls) | O(observed) |

---

## Cross-cutting techniques

- **Hash-chained append-only ledgers** — `eventd`, ralph, optitron, and the vakedz
  cache all share `sha256(prev_hex ‖ canonical_json(payload))` links for tamper
  evidence and deterministic replay.
- **Canonical JSON** (sorted keys, compact separators) — byte-identical output
  across runs/machines; the foundation of the determinism oracle and the hash chain.
- **Single-writer + `fsync`/`flock`** — durability + a serial chain invariant.
- **Capability attenuation as a partial order `≤`** — transitive closure over the
  grant lattice; the basis of `E-CAP-ATTENUATION` / `E-CAP-USE`.

## Notable non-linear spots (the things to watch)

1. **vakedz cache append** — O(L) per call (whole-ledger rewrite); bounded by the
   64 MB cap. Index/tail-append would fix it.
2. **POLA use-check** (`check.py:1757`) — worst-case ~quadratic in declaration size;
   not exercised by flat architectures, flagged in the paper's Future Work.
3. **`enrich_graph`** — was the dominant O(N²) (full `graph.nodes` scan per decl);
   fixed to O(N) in #268. `_children_of` is the remaining constant-factor scan,
   addressed in PR #269.
