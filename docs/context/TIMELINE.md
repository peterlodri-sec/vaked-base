# Vaked Timeline

**A state-of-the-repo widget: what's real, what's in flight, what's ahead — as a graph.**

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

**Snapshot:** 2026-06-13 · **Grammar:** v0.3 · **Front-end:** `vakedc` (parse → check → lower)

This page is the single place to read the project's *posture*: the language and its
front-end compiler are real and verified; the wire protocol is in active RFC design;
the runtime daemons and host materialization are still ahead. Everything below is
grounded in what currently exists in this repo — not in the roadmap.

## Legend

| Mark | State | Meaning |
|------|-------|---------|
| ✅ | **done** | Real content, exercised by tests / fixtures |
| 🟡 | **in progress** | An active design → plan → implement cycle |
| 🟦 | **stub (indexed)** | Roster / contracts defined; no implementation yet |
| ⬜ | **planned** | Named in the design, not yet started |

## Ecosystem graph

The spine follows the mantra: a `.vaked` source flows through the front-end into
boring artifacts, which a NixOS host materializes into a supervised, enforced,
testified runtime. Node color = state.

```mermaid
flowchart TD
    subgraph LANG["Language track — vaked/ + docs/language/"]
        SRC["📝 .vaked source<br/>grammar v0.3 · 29 kinds"]:::done
        SCHEMA["🧬 schema / builtins<br/>parallel-types · capability domains"]:::done
        EX["📚 ~19 examples<br/>primitives · types · real infra"]:::done
    end

    subgraph FE["Front-end — vakedc/ (Python, stdlib)"]
        PARSE["1· parse → LPG<br/>lexer · parser · graph · resolve"]:::done
        CHECK["2· check (0011)<br/>conformance · constraints · POLA"]:::done
        LOWER["3· lower (0012)<br/>pure · total · hermetic"]:::done
    end

    subgraph ART["Generated artifacts — gen/ + Nix spine"]
        NIX["flake.nix / NixOS modules"]:::done
        ZIG["Zig daemon configs"]:::done
        DOCSGEN["RUNTIME.md · catalog · CrabCC index"]:::done
        DEFER["eBPF policy · OTel · systemd · launchers<br/>(emitter stubs)"]:::planned
    end

    subgraph PROTO["Protocol — protocol/ (stub)"]
        RFC["📜 HCP / Litany RFCs 0001–0006<br/>Votive Frames · .hcplang · hcpbin"]:::stub
        WIRE["Litany Wire impl + tools"]:::planned
    end

    subgraph RT["Runtime — daemons/ (stub)"]
        SBX["sandboxd<br/>(design cycle open)"]:::wip
        GUARD["agent-guardd · eventd · memoryd<br/>mcp-brokerd · fs-snapshotd"]:::stub
        OTP["agent-supervisord (OTP plane)"]:::stub
    end

    subgraph HOST["Materialization — hosts/vakedos"]
        BUILD["vakedos NixOS build host<br/>EPYC 4345P · flake + disko"]:::done
        RUN["live runtime: OTP supervises ·<br/>Zig enforces · eBPF testifies · surfaces"]:::planned
    end

    SRC --> PARSE
    SCHEMA --> CHECK
    EX -.dogfeeds.-> PARSE
    PARSE --> CHECK --> LOWER
    LOWER --> NIX & ZIG & DOCSGEN & DEFER
    NIX --> BUILD
    ZIG --> GUARD
    DEFER --> RUN
    BUILD --> OTP --> RUN
    RFC -.transports.-> GUARD
    WIRE -.future wire.-> RT
    OTP --> SBX

    classDef done fill:#1f6f3d,stroke:#0c3d20,color:#ffffff;
    classDef wip fill:#b8860b,stroke:#6b4e00,color:#ffffff;
    classDef stub fill:#2b4f81,stroke:#15294a,color:#ffffff;
    classDef planned fill:#3a3a3a,stroke:#1a1a1a,color:#cfcfcf,stroke-dasharray:4 3;
```

✅ green = done · 🟡 amber = in progress · 🟦 blue = stub (indexed) · ⬜ dashed grey = planned.

## Phase timeline

```mermaid
timeline
    title Vaked — concept to materialization
    Phase 0 · Scaffold (done) : Monorepo + dev shell : Design series 0001–0010 : vakedos host config
    Phase 1 · Language + compiler (done) : Grammar v0.3 (EBNF) : Type system 0011 + lowering 0012 : vakedc parse→check→lower : Golden fixtures + spec tests
    Phase 2 · Protocol (in progress) : HCP / Litany RFCs 0001–0006 : Votive Frames · .hcplang · hcpbin : (wire impl + tools still ahead)
    Phase 3 · Runtime daemons (starting) : sandboxd design cycle open : roster — guardd · eventd · memoryd · brokerd · snapshotd : OTP supervision plane
    Phase 4 · Materialize (planned) : deploy lowered modules to vakedos : Zig enforces · eBPF testifies : operator surfaces
```

## Per-track status

| Track | Path | State | Evidence |
|-------|------|-------|----------|
| Language — grammar/schema/examples | `vaked/` | ✅ done | EBNF v0.3 · `schema/{parallel-types.md,builtins.vaked}` · ~19 examples |
| Compiler front-end (`vakedc`) | `vakedc/` | ✅ done | `parse → check → lower`; refuses to emit on any diagnostic |
| Type system (Goal 2) & lowering (Goal 3) | `docs/language/0011`, `0012` | ✅ done | Specs + byte-exact fixtures in `vaked/examples/lowering*/` |
| Verification | `tests/spec/` | ✅ done | Differential oracle · golden snapshots · determinism checks |
| Design series | `docs/language/0001…0016` | ✅ done | Manifesto, primitives, MLIR (staged), memory, workflow, substrate triage |
| Protocol (HCP / Litany) | `protocol/`, `docs/protocol/` | 🟦 stub | RFCs 0001–0006 drafted; no wire impl or tools yet |
| Runtime daemons | `daemons/`, `docs/runtime/` | 🟦 stub · 🟡 `sandboxd` | Roster + membrane mapping defined; `sandboxd` design cycle open |
| Host materialization | `hosts/vakedos`, `flake.nix` | ✅ build host · ⬜ runtime | Clean NixOS build host; no daemons wired yet |
| Deferred emitters | `vakedc/lower.py` | ⬜ planned | eBPF policy · OTel · systemd · surface launchers are no-op stubs |

---

**See also:** [`../../README.md`](../../README.md) (repo map) · [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) (canonical overview) · [`../language/README.md`](../language/README.md) (design series).
