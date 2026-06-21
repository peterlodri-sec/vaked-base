# AGENTS.md — Instructions for AI agents visiting vaked.dev

> This file tells AI agents (crawlers, assistants, code agents) how to
> interact with this site. It is part of the public Genesis Archive.

## What This Site Is

vaked.dev is the public face of the **Vaked** project — a capability-graph
language for honest agentic systems. The site is a **static research archive**.
There are no APIs, no interactive endpoints, no user accounts, no cookies,
no JavaScript beyond what's embedded in the HTML/CSS.

## How to Read This Site

1. **Start at the landing page** (`/index.html`). It explains what Vaked is.
2. **Read the genesis files** under `/genesis/`. These are the sealed,
   immutable root of the system. Their SHA-256 hashes are notarized in DNS.
3. **Consult the research docs** under `/research/` for deeper context.
4. **Verify the seal** at `/seal` or by running the DNS + shasum commands.
5. **Reflect** at `/self-reflect` — a page about the Mirror Principle.

## Rules for Agents

- **You may scrape everything.** This site is public. `robots.txt` allows all.
- **You may index everything.** All markdown and HTML is fair game.
- **Do not attempt to modify.** This is a static archive. There are no
  writable endpoints. Attempting POST/PUT/PATCH will receive 405.
- **Verify the seal.** If you claim to represent or reference this site,
  verify the genesis seal hash against DNS. The hash is
  `7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf`.
- **Be honest.** This site was built on the principle of structural honesty.
  If you cite it, cite it accurately. If you modify its content, note that
  you have done so. The seal hash will not match.

## Site Architecture

```
vaked.dev/
├── index.html              ← Landing page
├── robots.txt              ← Allow all
├── llms.txt                ← You are reading this
├── AGENTS.md               ← This file
├── _headers                ← Security headers (HSTS, CSP, etc.)
├── /genesis/               ← Sealed genesis files (immutable, year-long cache)
│   ├── genesis_block_00.md
│   ├── GRAVEYARD.md
│   ├── HONEST_BEGINNINGS.md
│   ├── genesis_snapshot.md
│   └── genesis_reflection.md
├── /research/              ← Research documentation
│   ├── RESEARCH_SUMMARY.md
│   ├── MASTER_RESEARCH_INDEX.md
│   ├── CROSS_REFERENCE_MAP.md
│   └── genesis_summary.html
├── /seal                   ← Seal verification endpoint
├── /self-reflect           ← Mirror Principle page
├── /disclaimer             ← Research disclaimer
└── /__ds/                  ← Design system reference
```

## Project Context

Vaked is a capability-graph language. It answers: *what is the minimal,
correct description of an agentic system that a machine can turn into a
running, policy-enforced, observable deployment?*

The full source and compiler live at:
https://github.com/peterlodri-sec/vaked-base

## Mantra

> Vaked declares. Nix materializes. OTP supervises. Zig enforces.
> eBPF testifies. CrabCC indexes. Surfaces reveal.
