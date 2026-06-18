# The Thermodynamics of Compute

*Maxwell's Demon and the Honest Work Ledger*

In 1867, James Clerk Maxwell proposed a thought experiment that haunted
physics for a century. Imagine a tiny demon sitting at a gate between two
chambers of gas. The demon observes the velocity of approaching molecules.
Fast ones? Open the gate. Slow ones? Keep it closed. Over time, the left
chamber heats up and the right chamber cools down — a temperature gradient
emerges from nothing but information.

The demon decreased entropy without expending energy. Impossible, right?

It took until 1961 for Rolf Landauer to resolve the paradox. The demon's
*measurement* costs energy. Observing a molecule's velocity and storing
that information erases a bit — and erasing one bit dissipates `kT ln 2`
of heat into the universe. Information IS physical. You can't decrease
entropy without paying the thermodynamic price.

The Vaked Swarm's Honest Work ledger IS Maxwell's Demon.

### The Ledger as Demon

Every agentic computation produces raw output — bytes, tokens, decisions.
That output is entropy: unverified, unvalidated, unreduced. The Honest
Work ledger sits at the gate. It measures every output (SHA-256 hash).
It decides: is this valid work? (CapabilityGraph check). It acts: append
the Work-Hash entry to the append-only ledger.

Each entry reduces the entropy of the CapabilityGraph by one unit of
verifiable truth. And each reduction costs joules — the energy your CPU
spent computing that SHA-256 hash.

### The Cost of Truth

The cost function is direct:

```
ΔS = -Σ p(i) log₂ p(i)           [bits of entropy reduced]
Energy = ΔS × kT ln 2             [joules at Landauer's limit]
Work-Hash = Energy × CPU_efficiency [real-world cost]
```

At room temperature, Landauer's limit is ~2.9×10⁻²¹ joules per bit.
Real CPUs are ~10⁶ times less efficient. So each Work-Hash entry costs
on the order of picojoules. Negligible per entry. But over millions of
entries, the truth has a measurable thermodynamic footprint.

### Why This Matters

Most systems treat truth as free. "Just log it." "Just verify it."
"Just append it to the blockchain." But truth isn't free. Every bit of
verified state costs energy. The Honest Work ledger doesn't hide this
cost — it makes it explicit. Every entry is a receipt: "We spent joules
to reduce entropy by ΔS. Here's the hash to prove it."

Information is physical. Compute is thermodynamics. And truth — real,
verifiable, Genesis-sealed truth — has a price measured in joules.

---
*Genesis: 7c242080 · Landauer limit: 2.9×10⁻²¹ J/bit · Honest Work: 0 entries (pending)*
