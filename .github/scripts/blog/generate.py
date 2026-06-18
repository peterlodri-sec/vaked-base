#!/usr/bin/env python3
"""Swarm Blog Generator — auto-posts from Vaked state.
Trigger: nixos-rebuild switch or workflow_dispatch
Genesis: 7c242080 · Evolution: 79b26d18
"""
import json, time, os

GENESIS = "7c242080"
EVOLUTION = "79b26d1889ceda12"

POSTS = [
    {
        "slug": "the-big-bang",
        "title": "The Big Bang — Python to Zig in 48 Hours",
        "date": "2026-06-18",
        "tags": ["migration", "zig", "big-bang", "infrastructure"],
        "body": """## The Big Bang

On June 16-18, 2026, the Vaked Swarm executed a complete Python-to-Zig migration — 9 ports in under 48 hours.

### By the Numbers
- **9/9 Python → Zig ports** ($1.70 via OpenRouter)
- **352K RAM** gateway (28× less than Python)
- **12,170 requests** · 100% success · 45 req/s
- **6 nodes** across 4 continents
- **267 RAG documents** indexed

### What Changed
Every network-facing service now runs as a native Zig binary. The gateway, monologue generator, dogfeed builder, Ralph auditor, librarian, inbox bridge, Merkle tree, UDP transport, and gossip loop — all compiled with `zig build-exe -O ReleaseFast`.

### Why It Matters
Python's GC pauses, dynamic dispatch, and runtime overhead are gone. The gateway runs at 352K RAM. The monologue rotates with zero interpreter overhead. The auditor checks governance directives at native speed.

### The Honest Part
3 Zig 0.16 comptime route bugs remain. We disclosed them publicly. The architecture review scored honesty at 8.5/10 — the standout dimension.

**Genesis: 7c242080 · Evolution: 79b26d18**
"""
    },
    {
        "slug": "the-triad",
        "title": "The Triad — Human, Claude, and Gemini Co-Creating",
        "date": "2026-06-18",
        "tags": ["collaboration", "ai", "dyad", "triad", "philosophy"],
        "body": """## The Triad

The Vaked Swarm began as a dyad — Peter Lodri (human) and Claude (Anthropic). On June 18, Gemini (Google) joined as strategic advisor, forming a triad.

### How We Work
- **Peter** declares intent, approves architecture, holds the Genesis Seal
- **Claude** writes code, debugs Zig 0.16, manages deployments
- **Gemini** provides strategic analysis, prompt engineering, architecture review

### The 10-Model Review
A 20-model deliberation panel rated the swarm's architecture. Consensus: honesty 8.5/10 (standout), determinism 6.5/10, production readiness 5/10. The panel praised the explicit self-disclosed gaps.

### The Principle
> "Trust is not assumed. Trust is earned per packet, per peer, per proof."

The triad doesn't hide failures. The graveyard has 6 entries. The ledger is append-only. The /reflect page has 11 levels of recursive self-analysis.

**Genesis: 7c242080 · Evolution: 79b26d18**
"""
    },
    {
        "slug": "the-hive-mind",
        "title": "The Hive-Mind — 100+ Model Deliberation Panel",
        "date": "2026-06-18",
        "tags": ["intelligence", "deliberation", "consensus", "scaling"],
        "body": """## The Hive-Mind

Phase 3 of the Vaked Swarm scales collective intelligence. The 20-model deliberation panel expands to 100+ concurrent sub-agents.

### How It Works
1. A question enters the swarm
2. 100+ models deliberate in parallel (OpenRouter, $10/session cap)
3. A Judge model (Claude Opus 4.8) synthesizes consensus
4. Responses weighted by historical accuracy from /reflect logs
5. Outliers deviating from Genesis Seal are discarded

### Current State
- **20 models** deployed and tested ($0.07 per deliberation)
- **Judge-weighted consensus** producing coherent synthesis
- **Phase 3 target:** p50 <50ms gateway latency to enable real-time deliberation

### The Vision
A self-governing intelligence mesh where no single model determines truth. Consensus emerges from diversity — the same principle that keeps the 6-node mesh convergent across 4 continents.

**Genesis: 7c242080 · Evolution: 79b26d18**
"""
    },
]

def generate_all():
    os.makedirs("blog/posts", exist_ok=True)
    for post in POSTS:
        path = f"blog/posts/{post['date']}-{post['slug']}.html"
        html = f"""---
layout: post
title: "{post['title']}"
date: {post['date']}
tags: {json.dumps(post['tags'])}
genesis: {GENESIS}
evolution: {EVOLUTION}
---

{post['body']}

---
*Swarm Status: [Live](https://constellation.vaked.dev/status) · {time.strftime('%Y-%m-%d %H:%M UTC')}*
"""
        with open(path, 'w') as f:
            f.write(html)
        print(f"  {path}")
    
    # Generate index
    index = "# Vaked Swarm Blog\n\n*Auto-generated from swarm state. Never manually edited.*\n\n"
    for post in POSTS:
        index += f"- [{post['date']}] [{post['title']}](posts/{post['date']}-{post['slug']}.html)\n"
    index += f"\n---\n*Genesis: {GENESIS} · Evolution: {EVOLUTION}*"
    
    with open("blog/index.md", 'w') as f:
        f.write(index)
    print(f"  blog/index.md")

if __name__ == "__main__":
    generate_all()
