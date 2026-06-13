# Security Policy

## Vaked's Security Model

Vaked operates in a three-layer architecture: **declaration** (Vaked), **materialization** (Nix), and **enforcement** (Zig/eBPF).

### What Vaked Guarantees

Vaked's type system provides **compile-time verification** of the Principle of Least Privilege (POLA):

✅ **Static POLA Verification** — No principal can hold or exercise more authority than delegated to it. The compiler certifies this via:
- **Use Check:** Every capability a principal uses is covered by a capability it was granted
- **Attenuation Check:** Authority only decreases (or stays equal) along delegation paths
- **Partial Order Validity:** Capability domains form well-defined attenuation orders

✅ **Decidable Checking** — Type checking always terminates and reports results deterministically. No halting-problem edge cases.

✅ **Provenance Tracking** — Every artifact carries a source-to-target mapping, enabling auditable traceability from infrastructure back to declarations.

✅ **Deterministic Lowering** — Identical declarations compile to byte-identical artifacts, enabling reproducibility verification.

### What Vaked Does NOT Guarantee

Vaked **does not** handle runtime enforcement. The following are the responsibility of the runtime layers:

❌ **Runtime Authority Enforcement** — Membranes, capability revocation, and actual syscall/network mediation are implemented in Zig daemons and eBPF.

❌ **Secrets Management** — Vaked does not embed secrets; configuration is plaintext (JSON, Nix). Integration with secrets managers (HashiCorp Vault, Sops, etc.) is delegated to the Nix build.

❌ **Compromise of Root Authority** — If a principal holding the root grant-set is compromised, POLA cannot help. Mitigation: principle of least privilege applies to the root itself; keep root authorities minimized and audited.

❌ **Timing / Covert Channels** — Vaked has no model of timing, signal handling, or side-channel attacks.

❌ **OS/Hypervisor Exploits** — Privilege escalation in the kernel or hypervisor is out of scope. Mitigation: regular patching and exploit mitigations (ASLR, CFI, etc.) at the OS level.

---

## Threat Model

See [`docs/language/THREAT_MODEL.md`](docs/language/THREAT_MODEL.md) for a detailed threat model including:

- Formal POLA statement and informal soundness proof
- Attack scenarios and how they're prevented
- Integration with runtime enforcement layers
- Evaluation plan for security claims

---

## Vulnerability Reporting

Vaked is a **research project** under active development. Stability is not guaranteed.

### If You Find a Security Issue

Please report it **privately** by emailing `cabotage@protonmail.com` with the subject `[Vaked] Security Issue`.

Include:
1. A description of the vulnerability
2. Steps to reproduce (if applicable)
3. Proposed mitigation (if you have one)
4. Your affiliation and contact info (optional)

**We will:**
- Acknowledge receipt within 48 hours
- Investigate and confirm/dismiss the report
- Disclose a fix timeline (usually 2–4 weeks for critical issues)
- Credit you in the CHANGELOG unless you prefer anonymity

### Public Issue Reporting

For non-security bugs or feature requests, use the [GitHub Issues](https://github.com/peterlodri-sec/vaked-base/issues) tracker.

---

## Known Limitations

### Type System

1. **Closed Constraint Set** — Only built-in refinements are supported (`in`, `oneof`, `matches`, bounds, `required`/`optional`/`default`). Real-world validation needs that the constraint set cannot express are treated as **language design events** — the language is extended, not the validator.

2. **No Dynamic Predicates** — User-defined predicates would make conformance Turing-equivalent, breaking the totality guarantee. Not supported by design.

3. **No Revocation at Type-Check Time** — The type system does not model revocation (capability removal during execution). Revocation is a **runtime membrane** operation (OTP supervisor's responsibility).

### Compiler

1. **Python Prototype** — vakedc is a reference implementation in Python (stdlib only), not production-hardened. Performance and memory usage are acceptable for typical declarations (~1500 lines) but may not scale to multi-gigabyte configurations.

2. **No Optimization Passes** — Lowering is a straightforward graph-to-text rendering. No code optimization, inlining, or dead-code elimination.

### Integration

1. **Nix Supply Chain** — `flake.lock` pins sources, but assumes integrity of the pinned sources. A compromise in a pinned repository is still a compromise. Mitigation: use cryptographic verification (GPG, keyless signatures) when fetching from untrusted sources.

2. **Zig/eBPF Implementation Gaps** — The runtime daemons (sandboxd, agent-guardd, eventd) are not yet implemented. Until they exist, POLA enforcement is incomplete.

---

## Security Roadmap

| Phase | Priority | Target | Scope |
|-------|----------|--------|-------|
| **v0.1** | High | 2026-07-31 | Type system + deterministic lowering verified; threat model documented |
| **v0.2** | High | 2026-10-31 | Zig daemons (sandboxd, agent-guardd, eventd) implemented with syscall enforcement |
| **v0.3** | High | 2026-12-31 | eBPF policy layer for audit/enforcement |
| **v1.0** | Medium | 2027-03-31 | Production hardening: Rust rewrite, formal verification, security audit |

---

## References

- Miller, M. "Robust Composition: Towards a Unified Approach to Access Control and Concurrency Control." *Ph.D. Thesis*, Johns Hopkins University, 2006.
- Karp, A. H. et al. "A Language for Distributed Applications." *SIGPLAN Notices*, 1994.
- Denning, D. E. "Information Warfare and Security." *Addison-Wesley*, 1999.
- `docs/language/0011-type-system.md` §4 — Formal capability model and POLA checking
- `docs/language/THREAT_MODEL.md` — Detailed threat analysis

---

## Acknowledgments

Security design draws from the object-capability literature (Mark Miller, Alan Karp, Jonathan Rees) and PL research on information flow and access control.
