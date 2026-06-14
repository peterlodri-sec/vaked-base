# Dogfood verification kernel v0 — proposer/judge (M2)

A local, zero-cloud kernel that makes one agent-proposed code transition
**typed-by-policy, capability-scoped, recorded, and replay-stable** before it is
accepted. The creative half (opencode + local Ollama) proposes; the deterministic
half (this kernel) decides. It dogfoods Vaked's three theories — immutable
(eventd WAL), control (accept/reject/rollback), and capability (POLA scope) —
on the M1, with no Linux kernel features.

Code: `tools/dogfood/` (see its README for the file map and CLI).

## Why this shape

The publication-credibility review flagged that trunk has **no implemented
`used(p) ⊑ granted(p)` use-check** and **no negative-POLA test suite**
(`E-CAP-USE`). This kernel implements that check at the file-path layer — the one
layer that runs without eBPF — and ships the negative tests. It is not the
runtime boundary (that is L2, eBPF/seccomp, on the daemon track); it is the
runnable proof of the *principle*.

## The transition (one WAL entry)

A transition is captured as a deterministic function of `(base tree, post-image
set)`. The payload (`transition.build_payload`):

```
kind=dogfood_transition, v=1
intent, capability_scope[]
input_tree_hash            # hash of in-scope tree before
patch_hash                 # hash of the captured post-image set
postimages {rel: sha}      # content-addressed exact bytes of changed files
declared_effects {writes,deletes}
actual_effects   {writes,deletes}   # filesystem reality
observed_effects {writes,deletes}|null   # Frida (M3), else null
capability_ok
state_hash_after           # hash of in-scope tree after
```

## The pipeline (`kernel.judge`)

```
snapshot base → proposer mutates tree → detect actual delta →
CAPABILITY (delta ⊆ scope) → DECLARED==ACTUAL → [OBSERVED ⊆ DECLARED] →
capture post-images → REPLAY (base+post-images ⇒ state_hash_after) →
accept ⇒ append to eventd WAL ; reject ⇒ roll tree back, record nothing
```

- **Change detection** is a before/after snapshot delta over the git file
  universe (`git ls-files --cached --others --exclude-standard`), so a dirty
  worktree's existing edits never masquerade as the proposal. Non-git roots
  (tests) use a full content-snapshot delta.
- **Replay** rebuilds the post-state in a throwaway dir from base + post-image
  blobs and re-hashes. It catches incomplete capture, blob corruption, and
  post-record drift. (Proposer-internal nondeterminism is *bounded* by capturing
  exact bytes — the kernel records what happened, byte-for-byte.)
- **Rollback** on reject: git worktree → restore in-scope from base blobs +
  `git checkout`/remove the out-of-scope violations; non-git → total restore
  from base.

## Validation (2026-06-14)

- `python3 tools/dogfood/test_kernel.py` → **11 passed, 0 failed**, covering all
  four gates, WAL tamper detection, rollback, and the hashing primitives.
- CLI in the live git worktree: in-scope edit **accepted** (seq 0, WAL appended);
  out-of-scope write **rejected** by the capability gate and rolled back (no
  stray file); `verify` confirms the chain; `log` lists the transition.

## Capability scope lowered from Vaked (M2.5)

The kernel's write-scope is no longer hand-typed — it is **lowered from a Vaked
capability declaration** (`vaked/examples/dogfood-kernel.vaked`), so the declared
POLA and the enforced scope cannot drift:

```
dogfood-kernel.vaked  --(vakedc|vakedz parse)-->  .vaked/graph.json
                                                       |
                              scope_from_vaked.py (reads the LPG)
                                                       |
                       kernel.py propose --from-vaked … --principal proposer
```

`scope_from_vaked.py` returns a principal's `writeScope` **only** if its `fs`
grant is write-capable (`repo_rw`/`host_rw`); a read-only principal (`fs.repo_ro`,
e.g. the judge) gets `[]` and the kernel refuses to propose as it. It reads the
parsed **LPG artifact**, not the source, so it is engine-agnostic — it survives
the planned `vakedc`(Python)→`vakedz`(Zig) cutover since both emit the LPG.

**Known gap (follow-up):** `filesystem` is currently a *schema-less* kind — there
is no path-allow-set membrane that *checks* the `writeScope` (the way
`networkMembrane` refines a `network` grant into host:port rules). Until that
membrane schema lands, `writeScope` rides as a descriptive open field on the
(open) `meshNode` schema — carried, not yet checked. Add a real `filesystem`
membrane kind so the path allow-set is a compile-time fact.

## Not in scope (deliberately)

- **No AIL-0 / ARP parser** — neutral JSON records; the ARP IR is a separate
  workstream. A seam exists to adopt it later.
- **No enforcement** — capability here is advisory path-scoping, not a kernel
  boundary. L2 (eBPF/seccomp) is the real boundary.

## Next (M3)

Wire `observe_frida.py` (Linux container) into the **observed** gate so
declared-vs-observed is checked against real syscalls, not just the filesystem
diff. See `l1-frida-evidence.md`. The kernel-side observed gate is already
implemented and tested (via the stub); only the live Frida observation needs the
Linux substrate.
