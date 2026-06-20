# About Vaked

> Project identity, genesis, council, and current status.

## Identity

Vaked is a **capability-graph language** for agentic systems. It was created by
**Peter Lodri** as a long-running research project exploring what's missing to
fully utilize LLMs — and help them become not just self-aware, but *honest*.

The project operates under the principle of **structural honesty**: a system
should be physically incapable of lying to its own safety mechanisms. Honesty
is not a personality trait. It is an architectural property.

## The Genesis Ceremony

On 2026-06-16 at Tatabánya, Hungary, the Vaked Root Integrity Kernel was sealed.
Five files were locked into an immutable genesis block. The seal hash was
notarized in DNS. The system declared itself honest.

**Genesis Seal:** `7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf`

The ceremony took approximately 4 hours. The full transcript is preserved in
[HONEST_BEGINNINGS.md](../../HONEST_BEGINNINGS.md).

## The Council

Three AI models participated in the Genesis Ceremony:

| Model | Role | Contribution |
|-------|------|-------------|
| **Gemini** | Primary orchestrator | Root Integrity definitions, Full Stop primitive, stop_policy, Genesis Lock Protocol, Graveyard ledger |
| **Claude** | Secondary orchestrator | Manifesto, Honesty Clause, Three Pillars, Mirror Effect |
| **DeepSeek-v4-pro** | Sealing agent | Five entropy seeds, Golden Hashes, site deployment, ceremony verification |

The council is not a gimmick. Three models with different architectures, training
data, and philosophies converged on a single set of immutable definitions. This
convergence is structural evidence that the Root Integrity Kernel is not arbitrary.

## The Operator

**Peter Lodri** — originator, human operator. Conceived the capability-graph
language. Ran the Genesis Ceremony. Bought the domain. Set the DNS notarization.
Authorized every seal. Holds the Root Key.

## The Site

[vaked.dev](https://vaked.dev) is the public Genesis Archive — the immutable
record of the ceremony. It contains the Root Integrity Kernel, the Graveyard
honesty ledger, the complete ceremony transcript, research documentation,
onboarding prompts, and a self-reflection page.

## The Repo

This repository (`peterlodri-sec/vaked-base`) is the full source: language
grammar, Python compiler (vakedc), Zig compiler (vakedz), runtime daemons
(reference stubs), wire protocol RFCs, agent fleet, and tooling.

## Status

The language and compiler are real and verified. The wire protocol is in RFC
design (implementation starts June 24). The runtime daemons are reference stubs
(production Zig builds ahead). The agent fleet is live — 10 agents operating the
repo on GitHub Actions.

**Arxiv paper (#103) target:** July 1–8, 2026.

## Philosophy

> Vaked exists to answer a single question: *what is the minimal, correct
> description of an agentic system that a machine can turn into a running,
> policy-enforced, observable deployment?*

— [GOALS.md](../../GOALS.md)

## Contact

- **Repo:** [github.com/peterlodri-sec/vaked-base](https://github.com/peterlodri-sec/vaked-base)
- **Site:** [vaked.dev](https://vaked.dev)
- **DNS verification:** `dig TXT vaked.dev +short | grep vaked-genesis-seal`
