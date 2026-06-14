# 1M Worker Scalability Test — Hardware Specification

**Document:** Infrastructure planning for extreme-scale compiler benchmarking  
**Status:** Planning (2026-06-13)  
**Target:** 1,000,000 parallel agents + 2,000,000 delegation edges

---

## Executive Summary

Benchmarking the Vaked compiler on a 1M-agent system requires a **compute-optimized bare-metal host** with significant memory and CPU resources. This document specifies hardware, estimated costs, and procurement timeline.

**Bottom line:** $50K–$150K hardware investment (one-time); ~2–3 weeks procurement lead time.

---

## Workload Characteristics

### Memory Usage (Estimated)

Based on 100k worker test extrapolation:

| Component | Per-Agent | Total (1M) | Notes |
|-----------|-----------|-----------|-------|
| Graph nodes | ~2–4 KB | 2–4 GB | AST nodes, type constraints |
| Delegation edges | ~0.5–1 KB | 500MB–1GB | Edge metadata (source, dest, capabilities) |
| Type annotations | ~0.5 KB | 500MB | POLA capability sets |
| Parse tables | ~10 KB | 10 GB | Lexer/parser intern tables (fixed cost) |
| **Total working set** | — | **13–16 GB** | — |
| **Peak heap (with GC)** | — | **40–64 GB** | 2.5–4× working set (Python GC fragmentation) |

**Conservative estimate:** 64 GB RAM minimum; 128 GB recommended.

### CPU Usage

- **Parse stage:** CPU-bound (tokenization, tree building)
- **Check stage:** CPU-bound (constraint solving, POLA verification)
- **Lower stage:** I/O-heavy (artifact writing) + CPU (code gen)

**Parallelism opportunity:** All three stages are CPU-intensive and could benefit from parallelization (future optimization).

---

## Hardware Options

### Option 1: Bare-Metal EPYC 7002 (Recommended for Research)

**Vendor:** Vultr, Hetzner, OVH  
**CPU:** AMD EPYC 7002 (Rome) — 192 cores (2× 96-core CPUs)  
**Memory:** 512 GB DDR4 ECC  
**Storage:** 2× 1.92 TB NVMe (RAID 1)  
**Network:** 10 Gbps  

**Cost:** $3,500–$4,500/month (Vultr); ~$42K–$54K/year  
**Setup time:** 24 hours (Vultr dedicated server)  

**Pros:**
- ✅ Extreme headroom (192 cores, 512 GB RAM)
- ✅ RAID for reliability
- ✅ ECC RAM for stability
- ✅ Proven performance (Vaked already runs on EPYC; vakedos uses EPYC 4345P)

**Cons:**
- ❌ Expensive for one-time benchmark
- ❌ Overkill (100k test only needs 8 cores, 64 GB)

**Recommendation:** Use existing vakedos EPYC 4345P host if available; otherwise lease short-term (1 month).

---

### Option 2: Threadripper PRO (DIY / Lab)

**Vendor:** AMD direct or system integrators (StarTech, etc.)  
**CPU:** AMD Threadripper PRO 5995WX — 64 cores  
**Memory:** 256 GB DDR4 ECC  
**Storage:** 2× 2 TB NVMe (RAID 1)  
**Network:** 10 Gbps Ethernet card  

**Cost (full system):** ~$80K–$120K (one-time)  
**Setup time:** 1–2 weeks (procurement + assembly)  

**Pros:**
- ✅ Massive core count (64 cores)
- ✅ One-time cost (own the hardware)
- ✅ Suitable for lab / research environment

**Cons:**
- ❌ Requires physical space + power/cooling
- ❌ No SLA (if hardware fails, you fix it)
- ❌ 64 cores < 192 cores (limits future parallelization)

**Recommendation:** Good for universities / labs with infrastructure; less suitable for quick cloud benchmark.

---

### Option 3: Cloud GPU Instance (Not Recommended)

**Why not:** GPU-accelerated compilers are not in scope; vakedc is CPU-bound (no CUDA/ROCm).

---

## Recommended Path: Vultr EPYC Rental

**Rationale:**
1. **Vaked already deployed on similar EPYC.** Minimal friction.
2. **Short-term lease.** Pay for 1 month (~$3.5K), run 1M benchmark, cancel.
3. **Known performance.** vakedos EPYC 4345P provides confidence.

**Procurement checklist:**

- [ ] Identify budget holder + approval ($3.5K cloud cost)
- [ ] Reserve Vultr EPYC 7002 for Nov 2026 (2–4 week lead time)
- [ ] Prepare benchmark scripts (Oct 2026)
- [ ] Deploy NixOS + vakedc to rental host (Nov 1)
- [ ] Run 1M benchmark (Nov 5–15)
- [ ] Publish results (Nov 20)
- [ ] Cancel rental (Nov 30)

---

## Performance Projections

Based on 100k test (273ms for 1M worker system):

### Scenario A: Linear Scaling (Best Case)

```
100k system:     ~273ms (100 iterations)
1M system:       ~2.73s (273ms × 10 workers)
10M system:      ~27.3s (if we ever needed it)
```

**Assumption:** Graph solver is O(n log n) or better; no pathological cases.

**Likely outcome:** Parse + check are close to linear; lower might be sublinear (artifact batching).

### Scenario B: Sublinear Scaling (Realistic)

```
100k system:     ~273ms
1M system:       ~5–10s (1.8–3.7× the linear estimate)
Reason:          - GC pressure increases (more allocations)
                 - Hash table collisions (larger working set)
                 - Cache misses (working set no longer fits in L3)
```

### Scenario C: Catastrophic Degradation (Worst Case, Unlikely)

```
100k system:     ~273ms
1M system:       >60s (something goes wrong)
Reason:          - O(n²) algorithm somewhere (shouldn't exist)
                 - Memory swapping (insufficient RAM)
                 - Parser state explosion (grammar issue)
```

**Mitigation:** Run test on 512 GB EPYC; if slowdown detected, profile + fix.

---

## Performance Expectations

### Stage-by-Stage Breakdown

Assuming 1M system follows ~5–7s total (realistic):

| Stage | Time | Cores Used | Bottleneck |
|-------|------|-----------|-----------|
| **Parse** | ~1.5s | 1 (sequential) | Lexer tokenization, tree building |
| **Check** | ~2s | 1–4 (graph traversal) | POLA constraint solving |
| **Lower** | ~2–4s | 1–8 (I/O + codegen) | Artifact writing to disk |
| **Total** | **~5.5–7.5s** | — | I/O (lower stage dominates) |

**Opportunity:** Parallelize check stage (different parts of constraint graph can be solved independently).

---

## Baremetal Host Setup (if buying Threadripper PRO)

### System Configuration

```nix
# flake.nix (part of vakedos config)
nixosConfigurations.vaked-1m-benchmark = nixos.lib.nixosSystem {
  system = "x86_64-linux";
  modules = [
    ./hosts/1m-benchmark-threadripper.nix
    # Threadripper PRO 5995WX variant
  ];
};
```

### Hardware Details

```
CPU:        AMD Threadripper PRO 5995WX (64 cores, 128 threads, 4.5 GHz boost)
Motherboard: ASUS Pro WS TRX50-SAGE WIFI
Memory:     8× 32 GB DDR4-3200 ECC (256 GB total)
Storage:    2× Samsung 980 Pro 2TB (RAID 1, NVMe)
PSU:        1600W 80+ Platinum
Cooling:    Noctua NH-U14S TR4-SP3 (premium tower cooler)
Case:       Fractal Design Define 7 XL
Network:    Mellanox ConnectX-5 100 Gbps (if needed for future distributed testing)
```

**Estimated cost:** $85K–$120K (parts + assembly)

---

## Timeline & Milestones

| Date | Milestone | Action |
|------|-----------|--------|
| Jun 2026 | 100k test proven | ✅ Completed (273ms avg, 100 iterations) |
| Jul–Aug 2026 | WP3/WP4 start | Hire engineers, parallel wire protocol + daemon work |
| Sep 2026 | WP4 MVP complete | eventd, sandboxd, eBPF skeleton done |
| Oct 2026 | Reserve hardware | Lease Vultr EPYC or purchase Threadripper (3–4 week lead) |
| Nov 2026 | Run 1M benchmark | Deploy, execute test, capture results |
| Dec 2026 | Analyze results | Profile, optimize if needed |
| Apr 2027 | Paper 3 published | Include 1M scalability results in WP5 arxiv paper |

---

## Cost Estimate Summary

| Option | Hardware | Rental/Owner | Setup | Total |
|--------|----------|--------------|-------|-------|
| **Vultr EPYC** | $3.5K/month | Rental | Minimal | **$3.5K** (1-time) |
| **Threadripper DIY** | $85K–$120K | Owner | 1–2 weeks | **$85K–$120K** (one-time) |
| **Existing vakedos** | Already owned | Owner | Next available slot | **$0** (use current) |

**Recommendation:** Try existing vakedos first (free); if not available, rent Vultr EPYC for 1 month ($3.5K).

---

## Future: 10M Worker Test

If 1M test succeeds and scales linearly to ~70s, a **10M test** would require:

- **Memory:** 400–640 GB (16× the 100k baseline)
- **CPU:** 256+ cores
- **Hardware:** Google Cloud TPU Pod (extreme scale) or custom supercomputer (overkill)

**Realistic:** 10M is probably the practical limit for a single-machine vakedc benchmark. Beyond that, distributed compilation (WP5+) would be needed.

---

**References:**

- `vaked/examples/swe-swarm-1m-workers-scalability.vaked` — Test case
- `docs/language/0014-verification-scaffold.md` — Verification methodology
- `ROADMAP_2026-2027.md` — Project timeline
- `hosts/vakedos/` — Existing EPYC configuration (reference)
